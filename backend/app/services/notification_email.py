"""L4 emails: grouped notification emails, the daily digest, unsubscribe links, and the 90-day clean-up.

All of it runs from the background loop (email_service.run_sender) in the one app process.
"""
import time as _time
import uuid
from datetime import datetime, timedelta
from itertools import groupby
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import jwt
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import ALGORITHM
from app.models.enums import ApprovalStatus, MembershipStatus, Role
from app.models.notification import Notification
from app.models.room import Membership, Room
from app.models.task import Task
from app.models.user import User
from app.schemas.common import PageParams
from app.services import email_service, my_task_service
from app.services import notification_service as notes
from app.utils.time import as_utc, utcnow

CATEGORIES = ("requests", "decisions", "assignments", "mentions", "daily_digest")
LABEL = {
    "requests": "requests and approvals",
    "decisions": "decisions about you",
    "assignments": "stages assigned to you",
    "mentions": "mentions in chat",
    "daily_digest": "the daily digest",
}
_GONE = ("removed_from_room", "room_deleted")  # the room can't be opened any more


# ================================================================== unsubscribe tokens

def unsubscribe_token(user_id, category: str) -> str:
    return jwt.encode({"sub": str(user_id), "cat": category, "purpose": "unsubscribe"},
                      get_settings().secret_key, algorithm=ALGORITHM)


def read_unsubscribe_token(token: str) -> tuple[uuid.UUID, str] | None:
    try:
        claims = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
        if claims.get("purpose") != "unsubscribe" or claims.get("cat") not in CATEGORIES:
            return None
        return uuid.UUID(claims["sub"]), claims["cat"]
    except (jwt.PyJWTError, KeyError, ValueError):
        return None


def unsubscribe_url(user_id, category: str) -> str:
    s = get_settings()
    return f"{s.public_api_url.rstrip('/')}{s.api_v1_prefix}/unsubscribe?token={unsubscribe_token(user_id, category)}"


def _send(db: Session, user: User, category: str, subject: str, title: str, paragraphs: list[str],
          button: tuple[str, str]) -> None:
    url = unsubscribe_url(user.id, category)
    text, html_body = email_service.render(
        title, paragraphs, button=button,
        footer=f"You get these emails for {LABEL[category]}.", footer_link=("Turn them off", url),
    )
    email_service.queue(
        db, to=user.email, subject=subject, text=text, html_body=html_body, category=category, user_id=user.id,
        headers={"List-Unsubscribe": f"<{url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"},
    )


# ================================================================== grouped notification emails

def link(n: Notification) -> str:
    base = get_settings().frontend_url.rstrip("/")
    if n.room_id and n.type not in _GONE:
        if n.type == "mentioned":
            return f"{base}/rooms/{n.room_id}/chat"
        if n.task_id:
            return f"{base}/rooms/{n.room_id}/tasks/{n.task_id}"
        return f"{base}/rooms/{n.room_id}"
    return f"{base}/"


GROUP_SUBJECT = {
    "requests": "{n} new requests in Taskroom",
    "decisions": "{n} updates about you in Taskroom",
    "assignments": "{n} stages need you in Taskroom",
    "mentions": "{n} mentions in Taskroom",
}


def _detail(n: Notification) -> list[str]:
    if n.type == "mentioned" and n.data and n.data.get("preview"):
        return [f"“{n.data['preview']}”"]
    if n.type == "proposal_rejected" and n.data and n.data.get("reason"):
        return [f"Reason: {n.data['reason']}"]
    if n.type == "stages_unassigned" and n.data:
        return [f"• {s['stage_title']} on “{s['task_title']}”" for s in n.data.get("stages", [])]
    return []


def flush_due(db: Session, now: datetime | None = None) -> int:
    """Sends every group whose window has closed. Returns how many emails were queued."""
    now = now or utcnow()
    rows = list(db.scalars(
        select(Notification)
        .where(Notification.email_due_at.is_not(None), Notification.email_due_at <= now,
               Notification.emailed_at.is_(None))
        .order_by(Notification.user_id, Notification.category, Notification.created_at)
    ))
    sent = 0
    for (user_id, category), group in groupby(rows, key=lambda n: (n.user_id, n.category)):
        group = list(group)
        for n in group:
            n.emailed_at = now
        user = db.get(User, user_id)
        s = notes.settings_for(db, user_id)
        if user is None or not (s.email_enabled and getattr(s, category)):
            continue  # switched off during the window
        muted = set(notes.muted_room_ids(db, user_id))
        # already seen in the bell, or muted since: no need to email it
        keep = [n for n in group if n.read_at is None and n.room_id not in muted]
        if not keep:
            continue
        hi = f"Hi {user.name},"
        if len(keep) == 1:
            n = keep[0]
            _send(db, user, category, n.title, n.title, [hi, *_detail(n)], ("Open in Taskroom", link(n)))
        else:
            base = get_settings().frontend_url.rstrip("/")
            one_room = {n.room_id for n in keep} == {keep[0].room_id} and all(n.type not in _GONE for n in keep)
            target = f"{base}/rooms/{keep[0].room_id}" if one_room and keep[0].room_id else f"{base}/"
            subject = GROUP_SUBJECT[category].format(n=len(keep))
            _send(db, user, category, subject, subject, [hi, *[f"• {n.title}" for n in keep]],
                  ("Open Taskroom", target))
        sent += 1
    db.commit()
    return sent


# ================================================================== the daily digest

def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _task_lines(items, muted) -> list[str]:
    out = []
    for t in items:
        if t.room.id in muted:
            continue
        due = as_utc(t.due_date).strftime("%a %d %b")
        out.append(f"• {t.title} ({t.room.name}), due {due}")
    return out


def build_digest(db: Session, user: User, now: datetime) -> list[str]:
    """The digest's paragraphs, or [] when there's nothing worth sending."""
    muted = set(notes.muted_room_ids(db, user.id))
    page = PageParams(page=1, limit=20)
    common = dict(scope="mine", from_=None, to=None, status=None, room=None, blocked=None, overdue=None)

    def mine(**kw):
        items, _ = my_task_service.list_my_tasks(db, user, page, **{**common, **kw})
        return items

    overdue = _task_lines(mine(actionable=True, overdue=True), muted)
    seen = set(overdue)
    soon = [x for x in _task_lines(mine(actionable=True, overdue=False, from_=now, to=now + timedelta(days=2)), muted)
            if x not in seen]
    blocked = _task_lines(mine(actionable=None, blocked=True), muted)

    # pending requests where this person decides
    requests = []
    head_rooms = db.execute(
        select(Room.id, Room.name).join(Membership, Membership.room_id == Room.id).where(
            Membership.user_id == user.id, Membership.role == Role.HEAD, Membership.status == MembershipStatus.ACTIVE)
    ).all()
    for room_id, name in head_rooms:
        if room_id in muted:
            continue
        joins = db.scalar(select(func.count()).select_from(Membership).where(
            Membership.room_id == room_id, Membership.status == MembershipStatus.PENDING))
        if joins:
            requests.append(f"• {joins} join request{'s' if joins != 1 else ''} in {name}")
    approver_rooms = {rid for rid, _ in head_rooms}
    approver_rooms |= {rid for rid in db.scalars(select(Membership.room_id).where(
        Membership.user_id == user.id, Membership.status == MembershipStatus.ACTIVE))
        if user.id in notes.approver_ids(db, rid)}
    for room_id in approver_rooms - muted:
        props = db.scalar(select(func.count()).select_from(Task).where(
            Task.room_id == room_id, Task.approval_status == ApprovalStatus.PENDING, Task.created_by != user.id))
        if props:
            name = db.get(Room, room_id).name
            requests.append(f"• {props} proposal{'s' if props != 1 else ''} waiting in {name}")

    paragraphs = []
    for heading, lines in (("Overdue", overdue), ("Due in the next two days", soon),
                           ("Blocked", blocked), ("Waiting for your decision", requests)):
        if lines:
            paragraphs += [heading, *lines]
    return paragraphs


def send_digests(db: Session, now: datetime | None = None) -> int:
    """Once a day per person, at the digest hour in their timezone (or later that day, if the server was down)."""
    now = now or utcnow()
    hour = get_settings().digest_hour
    sent = 0
    for user in db.scalars(select(User)):
        local = now.astimezone(_zone(user.timezone))
        if local.hour < hour:
            continue
        s = notes.settings_for(db, user.id)
        if s.last_digest_on == local.date():
            continue
        row = notes._stored_settings(db, user.id)
        row.last_digest_on = local.date()
        if not (row.email_enabled and row.daily_digest):
            continue
        paragraphs = build_digest(db, user, now)
        if not paragraphs:
            continue  # nothing to say: no email
        base = get_settings().frontend_url.rstrip("/")
        subject = f"Your Taskroom day: {local.strftime('%A %d %B')}"
        _send(db, user, "daily_digest", subject, "Your day in Taskroom", [f"Good morning {user.name},", *paragraphs],
              ("Open My Tasks", f"{base}/my-tasks"))
        sent += 1
    db.commit()
    return sent


# ================================================================== clean-up

def purge_old(db: Session, now: datetime | None = None) -> int:
    now = now or utcnow()
    cutoff = now - timedelta(days=get_settings().notification_retention_days)
    n = db.execute(delete(Notification).where(Notification.created_at < cutoff)).rowcount
    db.commit()
    return n


# ================================================================== the loop

_last = {"digest": 0.0, "purge": 0.0}


def tick(db: Session) -> None:
    """Called every few seconds by the sender loop. Digests are checked once a minute, clean-up once an hour."""
    flush_due(db)
    mono = _time.monotonic()
    if mono - _last["digest"] >= 60:
        _last["digest"] = mono
        send_digests(db)
    if mono - _last["purge"] >= 3600:
        _last["purge"] = mono
        purge_old(db)
