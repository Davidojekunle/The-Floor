"""Calendar subscription feeds (iCalendar .ics) for Google Calendar, Apple Calendar and Outlook.

Two kinds, both private links owned by one person:
- personal: every unfinished stage that's theirs (assigned, or through a tag) across their active rooms;
- room: every unfinished approved task in a room they're an active member of.
Events are all-day, on the due date in the owner's timezone. Calendar apps poll the link on their own
schedule (Google: every few hours), so this is read-only and eventually up to date.
"""
import secrets
import uuid
from datetime import timedelta
from urllib.parse import quote
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import NotFound
from app.models.calendar import CalendarFeed
from app.models.enums import ApprovalStatus, MembershipStatus, StageStatus
from app.models.room import Membership, Room
from app.models.task import Stage, Task
from app.models.user import User
from app.services import stage_logic
from app.services import task_common as common
from app.utils.time import as_utc, utcnow


# ------------------------------------------------------------------ links

def _feed(db: Session, user: User, room_id) -> CalendarFeed | None:
    q = select(CalendarFeed).where(CalendarFeed.user_id == user.id)
    q = q.where(CalendarFeed.room_id.is_(None)) if room_id is None else q.where(CalendarFeed.room_id == room_id)
    return db.scalar(q)


def get_or_create(db: Session, user: User, room_id=None) -> CalendarFeed:
    feed = _feed(db, user, room_id)
    if feed is None:
        feed = CalendarFeed(id=uuid.uuid4(), token=secrets.token_urlsafe(32), user_id=user.id, room_id=room_id,
                            created_at=utcnow())
        db.add(feed)
        db.commit()
    return feed


def reset(db: Session, user: User, room_id=None) -> CalendarFeed:
    """A new secret; the old link stops working at once."""
    feed = _feed(db, user, room_id)
    if feed is None:
        return get_or_create(db, user, room_id)
    feed.token = secrets.token_urlsafe(32)
    db.commit()
    return feed


def links(feed: CalendarFeed) -> dict:
    https = f"{get_settings().public_api_url.rstrip('/')}{get_settings().api_v1_prefix}/calendar/{feed.token}.ics"
    webcal = "webcal://" + https.split("://", 1)[1]
    return {"url": https, "webcal_url": webcal,
            "google_url": "https://calendar.google.com/calendar/r?cid=" + quote(webcal, safe="")}


# ------------------------------------------------------------------ the feed

def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545: lines over 75 octets continue on the next line after one space."""
    raw = line.encode("utf-8")
    if len(raw) <= 75:
        return line
    parts, cur = [], b""
    for ch in line:
        b = ch.encode("utf-8")
        if len(cur) + len(b) > (75 if not parts else 74):
            parts.append(cur.decode("utf-8"))
            cur = b""
        cur += b
    parts.append(cur.decode("utf-8"))
    return "\r\n ".join(parts)


def _event(uid: str, day, summary: str, description: str, url: str, stamp: str) -> list[str]:
    return [
        "BEGIN:VEVENT",
        f"UID:{uid}@the-floor",
        f"DTSTAMP:{stamp}",
        f"DTSTART;VALUE=DATE:{day.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{(day + timedelta(days=1)).strftime('%Y%m%d')}",
        f"SUMMARY:{_escape(summary)}",
        f"DESCRIPTION:{_escape(description)}",
        f"URL:{url}",
        "TRANSP:TRANSPARENT",  # a due date doesn't make you busy
        "END:VEVENT",
    ]


_STATUS = {StageStatus.TODO: "Ready for you", StageStatus.IN_PROGRESS: "In progress",
           StageStatus.BLOCKED: "Blocked", StageStatus.LOCKED: "Waiting on an earlier stage"}


def render(db: Session, token: str) -> str:
    feed = db.scalar(select(CalendarFeed).where(CalendarFeed.token == token))
    user = db.get(User, feed.user_id) if feed else None
    if feed is None or user is None:
        raise NotFound("Calendar not found.")
    tz = _zone(user.timezone)
    base = get_settings().frontend_url.rstrip("/")
    stamp = utcnow().strftime("%Y%m%dT%H%M%SZ")
    events: list[str] = []

    if feed.room_id is None:
        name = "The Floor · My work"
        rows = db.execute(
            select(Stage, Task, Room)
            .join(Task, Task.id == Stage.task_id)
            .join(Room, Room.id == Task.room_id)
            .join(Membership, (Membership.room_id == Room.id) & (Membership.user_id == user.id))
            .where(Membership.status == MembershipStatus.ACTIVE, Task.approval_status == ApprovalStatus.APPROVED,
                   Stage.status != StageStatus.DONE, common.participant_clause_any_room(user.id))
        ).all()
        for stage, task, room in rows:
            due = as_utc(stage.due_date or task.due_date).astimezone(tz).date()
            events += _event(f"stage-{stage.id}", due, f"{stage.title} · {task.title}",
                             f"{_STATUS.get(stage.status, stage.status)} · {room.name}",
                             f"{base}/rooms/{room.id}/tasks/{task.id}", stamp)
    else:
        room = db.get(Room, feed.room_id)
        member = db.scalar(select(Membership).where(Membership.room_id == feed.room_id, Membership.user_id == user.id,
                                                    Membership.status == MembershipStatus.ACTIVE))
        if room is None or member is None:
            raise NotFound("Calendar not found.")  # left or removed: the room's feed dies with the membership
        name = f"The Floor · {room.name}"
        tasks = db.scalars(select(Task).where(Task.room_id == room.id,
                                              Task.approval_status == ApprovalStatus.APPROVED)).all()
        for task in tasks:
            summary = stage_logic.summarize(common.load_stages(db, task.id))
            if summary.status == "done":
                continue
            now_line = f"Now: {summary.current_title}" if summary.current_title else "Not started"
            events += _event(f"task-{task.id}", as_utc(task.due_date).astimezone(tz).date(), task.title,
                             f"{summary.done} of {summary.total} stages done · {now_line}",
                             f"{base}/rooms/{room.id}/tasks/{task.id}", stamp)

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//The Floor//Calendar//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", f"X-WR-CALNAME:{_escape(name)}", "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
             "X-PUBLISHED-TTL:PT1H", *events, "END:VCALENDAR"]
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"
