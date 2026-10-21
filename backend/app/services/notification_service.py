"""L4: notifications. One system, two channels: the bell (always, instantly) and email
(by settings, grouped within a short window per person and category).

Never sent: your own actions, chat messages, anything from a room you muted.
Every function here adds to the caller's transaction; nothing exists unless it commits.
"""
import uuid
from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.models.enums import ApprovalStatus, MembershipStatus, Role, StageStatus
from app.models.notification import MutedRoom, Notification, NotificationSettings
from app.models.room import Membership, TempHead
from app.models.tag import MembershipTag
from app.models.task import Stage, StageAssignee, Task
from app.models.user import User
from app.permissions.rules import RoomContext
from app.realtime import events as live
from app.services import push_service
from app.utils.time import as_utc, utcnow

CATEGORY = {
    "join_requested": "requests",
    "proposal_submitted": "requests",
    "stages_unassigned": "requests",
    "join_approved": "decisions",
    "proposal_approved": "decisions",
    "proposal_rejected": "decisions",
    "temp_head_granted": "decisions",
    "head_transferred": "decisions",
    "removed_from_room": "decisions",
    "room_deleted": "decisions",
    "stage_ready": "assignments",
    "stage_assigned": "assignments",
    "mentioned": "mentions",
    "replied": "mentions",  # a reply is a way of addressing you, so it shares the Mentions switch
    "nudged": "assignments",  # a head asked for an update on your stage
    "stage_due_soon": "assignments",  # automatic reminders
    "stage_overdue": "assignments",
    "nudge_answered": "decisions",  # someone answered the nudge you sent
}
TYPES = tuple(CATEGORY)
SWITCHES = ("email_enabled", "requests", "decisions", "assignments", "daily_digest", "mentions", "all_messages")
_DUE = "_notification_email_due"  # per-transaction: (user, category) -> due time, for rows not yet flushed


# ================================================================== settings and mutes

def settings_for(db: Session, user_id) -> NotificationSettings:
    """The stored row, or an unsaved one with every switch on."""
    row = db.get(NotificationSettings, user_id)
    if row is None:
        row = NotificationSettings(user_id=user_id, email_enabled=True, requests=True, decisions=True,
                                   assignments=True, daily_digest=True, mentions=True, all_messages=False)
    return row


def _stored_settings(db: Session, user_id) -> NotificationSettings:
    row = db.get(NotificationSettings, user_id)
    if row is None:
        row = settings_for(db, user_id)
        db.add(row)
    return row


def muted_room_ids(db: Session, user_id) -> list[uuid.UUID]:
    return list(db.scalars(select(MutedRoom.room_id).where(MutedRoom.user_id == user_id).order_by(MutedRoom.created_at)))


def is_muted(db: Session, user_id, room_id) -> bool:
    return db.get(MutedRoom, (user_id, room_id)) is not None


def update_settings(db: Session, user: User, changes: dict) -> NotificationSettings:
    row = _stored_settings(db, user.id)
    for key, value in changes.items():
        setattr(row, key, value)
    db.commit()
    return row


def mute(db: Session, user: User, room_id) -> None:
    """Safe to repeat. The caller has already checked the user is an active member."""
    if not is_muted(db, user.id, room_id):
        db.add(MutedRoom(user_id=user.id, room_id=room_id, created_at=utcnow()))
        db.commit()


def unmute(db: Session, user: User, room_id) -> None:
    row = db.get(MutedRoom, (user.id, room_id))
    if row is not None:
        db.delete(row)
        db.commit()


# ================================================================== the core

def _email_due(db: Session, user_id, category: str, now):
    """When this notification's email goes out, or None for no email. Joins an open group if there is one."""
    s = settings_for(db, user_id)
    if not (s.email_enabled and getattr(s, category)):
        return None
    cache = db.info.setdefault(_DUE, {})
    if (user_id, category) in cache:
        return cache[(user_id, category)]
    due = db.scalar(
        select(func.min(Notification.email_due_at)).where(
            Notification.user_id == user_id, Notification.category == category,
            Notification.emailed_at.is_(None), Notification.email_due_at.is_not(None),
        )
    )
    due = as_utc(due) if due is not None else now + timedelta(seconds=get_settings().notification_email_delay_seconds)
    cache[(user_id, category)] = due
    return due


def notify(db: Session, user_id, type_: str, title: str, *, room=None, task=None, stage=None,
           actor: User | None = None, data: dict | None = None) -> Notification | None:
    if actor is not None and actor.id == user_id:
        return None  # never for your own actions
    if room is not None and is_muted(db, user_id, room.id):
        return None  # a muted room is silent on both channels
    category = CATEGORY[type_]
    now = utcnow()
    n = Notification(
        id=uuid.uuid4(), user_id=user_id, type=type_, category=category, title=title[:400],
        room_id=room.id if room else None, room_name=room.name if room else None,
        task_id=task.id if task else None, task_title=task.title if task else None,
        stage_id=stage.id if stage else None, stage_title=stage.title if stage else None,
        actor_id=actor.id if actor else None, actor_name=actor.name if actor else None,
        data=data, created_at=now, email_due_at=_email_due(db, user_id, category, now),
    )
    db.add(n)
    live.notification_created(db, user_id, n.room_id, n.id)
    if getattr(settings_for(db, user_id), category):  # push follows the category switches, like email
        if data and data.get("preview"):
            body = data["preview"]  # a mention: show what was said
        elif data and data.get("note"):
            body = data["note"]  # a nudge with a note
        elif data and data.get("result_stage"):
            body = f"The result of “{data['result_stage']}” is attached."
        else:
            body = n.room_name if n.room_name and n.room_name not in n.title else None  # titles usually name the room
        push_service.queue(db, user_id, title=n.title, body=body, url=target_path(n), tag=str(n.id))
    return n


def target_path(n: Notification) -> str:
    """Where opening it goes in the app. Same rules as targetOf() in NotificationsPage.tsx."""
    if not n.room_id or n.type in ("room_deleted", "removed_from_room"):
        return "/notifications"
    room = f"/rooms/{n.room_id}"
    if n.type in ("mentioned", "replied"):
        return f"{room}/chat"
    if n.type in ("join_requested", "proposal_submitted"):
        return f"{room}/requests"
    if n.type == "stages_unassigned":
        stages = (n.data or {}).get("stages") or []
        return f"{room}/tasks/{stages[0]['task_id']}" if stages and stages[0].get("task_id") else room
    if n.task_id:
        return f"{room}/tasks/{n.task_id}"
    return room


PREVIEW = 140  # characters of a message shown in a notification


def preview(text: str) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= PREVIEW else flat[: PREVIEW - 1].rstrip() + "…"


def chat_message(db: Session, room, sender: User, message_id, body: str, mentioned: set, replied_to=None) -> None:
    """A new chat message. The person replied to and the people mentioned get a notification (bell, email and
    push by their Mentions switch), one each; everyone else who chose "every message" gets a push only.
    Never the sender, never a muted room."""
    short = preview(body)
    data = {"message_id": str(message_id), "preview": short}
    if replied_to is not None and replied_to != sender.id:
        notify(db, replied_to, "replied", f"{sender.name} replied to you in {room.name}", room=room, actor=sender, data=data)
    for user_id in mentioned - {replied_to}:
        notify(db, user_id, "mentioned", f"{sender.name} mentioned you in {room.name}", room=room, actor=sender, data=data)
    mentioned = mentioned | ({replied_to} if replied_to else set())
    if not get_settings().push_enabled:
        return
    others = set(db.scalars(
        select(NotificationSettings.user_id)
        .join(Membership, (Membership.user_id == NotificationSettings.user_id) & (Membership.room_id == room.id))
        .where(NotificationSettings.all_messages.is_(True), Membership.status == MembershipStatus.ACTIVE)
    )) - mentioned - {sender.id}
    for user_id in others:
        if not is_muted(db, user_id, room.id):
            # one pop-up per room: each new message replaces the last (same tag) and alerts again
            push_service.queue(db, user_id, title=f"{sender.name} in {room.name}", body=short,
                               url=f"/rooms/{room.id}/chat", tag=f"chat:{room.id}")


def _clear_cache(session) -> None:
    session.info.pop(_DUE, None)


from sqlalchemy import event  # noqa: E402

event.listen(Session, "after_commit", _clear_cache)
event.listen(Session, "after_rollback", _clear_cache)


# ================================================================== who

def _actor(db: Session, ctx: RoomContext) -> User:
    return db.get(User, ctx.membership.user_id)


def head_id(db: Session, room_id):
    return db.scalar(select(Membership.user_id).where(
        Membership.room_id == room_id, Membership.role == Role.HEAD, Membership.status == MembershipStatus.ACTIVE))


def approver_ids(db: Session, room_id) -> set:
    """Everyone who can approve proposals: the head and active temp heads."""
    temps = set(db.scalars(
        select(TempHead.user_id)
        .join(Membership, (Membership.user_id == TempHead.user_id) & (Membership.room_id == TempHead.room_id))
        .where(TempHead.room_id == room_id, TempHead.revoked_at.is_(None), TempHead.expires_at > utcnow(),
               Membership.status == MembershipStatus.ACTIVE)
    ))
    head = head_id(db, room_id)
    return temps | ({head} if head else set())


def _assignees(db: Session, stage_ids) -> dict:
    out = defaultdict(set)
    if stage_ids:
        for sid, uid in db.execute(select(StageAssignee.stage_id, StageAssignee.user_id)
                                   .where(StageAssignee.stage_id.in_(stage_ids))):
            out[sid].add(uid)
    return out


def _participants(db: Session, room_id, stages) -> dict:
    """Per stage: its assignees plus active members holding its tag."""
    ids = [s.id for s in stages]
    out = _assignees(db, ids)
    tag_ids = {s.tag_id for s in stages if s.tag_id}
    if tag_ids:
        holders = defaultdict(set)
        for tag_id, uid in db.execute(
            select(MembershipTag.tag_id, Membership.user_id)
            .join(Membership, Membership.id == MembershipTag.membership_id)
            .where(MembershipTag.tag_id.in_(tag_ids), Membership.room_id == room_id,
                   Membership.status == MembershipStatus.ACTIVE)
        ):
            holders[tag_id].add(uid)
        for s in stages:
            if s.tag_id:
                out[s.id] |= holders[s.tag_id]
    return out


# ================================================================== triggers

def join_requested(db: Session, room, requester: User) -> None:
    head = head_id(db, room.id)
    if head:
        notify(db, head, "join_requested", f"{requester.name} asked to join {room.name}", room=room, actor=requester)


def join_request_handled(db: Session, room_id, requester_id) -> None:
    """Approved or rejected: "X asked to join" has nothing left to act on, for any head who got it.
    Read ones don't go out by email either. The caller commits (and its room_changed refreshes the bell)."""
    db.execute(
        update(Notification)
        .where(Notification.type == "join_requested", Notification.room_id == room_id,
               Notification.actor_id == requester_id, Notification.read_at.is_(None))
        .values(read_at=utcnow())
    )


def join_approved(db: Session, ctx: RoomContext, user_id) -> None:
    actor = _actor(db, ctx)
    notify(db, user_id, "join_approved", f"You're in. {actor.name} approved your request to join {ctx.room.name}",
           room=ctx.room, actor=actor)


def proposal_submitted(db: Session, ctx: RoomContext, task: Task) -> None:
    actor = _actor(db, ctx)
    for uid in approver_ids(db, ctx.room.id):
        notify(db, uid, "proposal_submitted", f"{actor.name} proposed “{task.title}” in {ctx.room.name}",
               room=ctx.room, task=task, actor=actor)


def proposal_decided(db: Session, ctx: RoomContext, task: Task, *, approved: bool) -> None:
    actor = _actor(db, ctx)
    if approved:
        notify(db, task.created_by, "proposal_approved", f"{actor.name} approved your proposal “{task.title}”",
               room=ctx.room, task=task, actor=actor)
    else:
        notify(db, task.created_by, "proposal_rejected", f"{actor.name} rejected your proposal “{task.title}”",
               room=ctx.room, task=task, actor=actor,
               data={"reason": task.rejection_reason} if task.rejection_reason else None)


def temp_head_granted(db: Session, ctx: RoomContext, user_id, expires_at) -> None:
    actor = _actor(db, ctx)
    notify(db, user_id, "temp_head_granted", f"{actor.name} made you a temporary head of {ctx.room.name}",
           room=ctx.room, actor=actor, data={"expires_at": as_utc(expires_at).isoformat()})


def head_transferred(db: Session, ctx: RoomContext, user_id) -> None:
    actor = _actor(db, ctx)
    notify(db, user_id, "head_transferred", f"{actor.name} made you the head of {ctx.room.name}",
           room=ctx.room, actor=actor)


def removed_from_room(db: Session, ctx: RoomContext, user_id) -> None:
    actor = _actor(db, ctx)
    notify(db, user_id, "removed_from_room", f"You were removed from {ctx.room.name}", room=ctx.room, actor=actor)


def room_deleted(db: Session, ctx: RoomContext, member_ids) -> None:
    actor = _actor(db, ctx)
    for uid in member_ids:
        notify(db, uid, "room_deleted", f"{actor.name} deleted the room {ctx.room.name}", room=ctx.room, actor=actor)


def stages_unassigned(db: Session, ctx: RoomContext, leaver: User, stages: list[Stage]) -> None:
    """A member left, and these unfinished stages have nobody on them now."""
    head = head_id(db, ctx.room.id)
    if not stages or not head:
        return
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_({s.task_id for s in stages})))}
    n = len(stages)
    title = (f"{leaver.name} left {ctx.room.name}. "
             f"{n} unfinished stage{'s have' if n != 1 else ' has'} nobody on {'them' if n != 1 else 'it'}")
    only_task = tasks[stages[0].task_id] if len(tasks) == 1 else None
    notify(db, head, "stages_unassigned", title, room=ctx.room, task=only_task,
           stage=stages[0] if n == 1 else None, actor=leaver,
           data={"stages": [{"task_id": str(s.task_id), "task_title": tasks[s.task_id].title,
                             "stage_id": str(s.id), "stage_title": s.title} for s in stages]})


# ------------------------------------------------------------------ stages

def snapshot(db: Session, stages: list[Stage]) -> dict:
    """Taken when stages are loaded, before a change: status and assignees per stage."""
    assignees = _assignees(db, [s.id for s in stages])
    return {s.id: (s.status, frozenset(assignees[s.id])) for s in stages}


def _handed_over(stages: list[Stage], ready: Stage) -> dict | None:
    """The latest finished result from the stages before this one: what the next person picks up."""
    earlier = [s for s in stages if s.position < ready.position and s.status == StageStatus.DONE and s.result_url]
    if not earlier:
        return None
    last = max(earlier, key=lambda s: s.position)
    return {"result_url": last.result_url, "result_stage": last.title}


def stage_changes(db: Session, ctx: RoomContext, task: Task, stages: list[Stage], before: dict) -> None:
    """After a change: stage_ready to everyone on a stage that just became todo, otherwise stage_assigned
    to people newly assigned. One per person per stage. Nothing while the task is still a proposal."""
    if task.approval_status != ApprovalStatus.APPROVED or not stages:
        return
    db.flush()
    actor = _actor(db, ctx)
    now_assigned = _assignees(db, [s.id for s in stages])
    participants = None
    for s in stages:
        prev_status, prev_assigned = before.get(s.id, (None, frozenset()))
        if s.status == StageStatus.TODO and prev_status != StageStatus.TODO:
            if participants is None:
                participants = _participants(db, ctx.room.id, stages)
            handed = _handed_over(stages, s)
            for uid in participants[s.id]:
                notify(db, uid, "stage_ready", f"“{s.title}” on “{task.title}” is ready for you",
                       room=ctx.room, task=task, stage=s, actor=actor, data=handed)
        elif s.status != StageStatus.DONE:
            for uid in now_assigned[s.id] - prev_assigned:
                notify(db, uid, "stage_assigned", f"{actor.name} assigned you to “{s.title}” on “{task.title}”",
                       room=ctx.room, task=task, stage=s, actor=actor)


# ================================================================== the bell

def unread_count(db: Session, user: User) -> int:
    return db.scalar(select(func.count()).select_from(Notification).where(
        Notification.user_id == user.id, Notification.read_at.is_(None)))


def _owned(db: Session, user: User, notification_id) -> Notification | None:
    n = db.get(Notification, notification_id)
    return n if n is not None and n.user_id == user.id else None


def _older_or_equal(n: Notification):
    created = n.created_at
    return (Notification.created_at < created) | ((Notification.created_at == created) & (Notification.id <= n.id))


def list_notifications(db: Session, user: User, *, unread: bool, before, limit: int) -> tuple[list[Notification], bool]:
    q = select(Notification).where(Notification.user_id == user.id)
    if unread:
        q = q.where(Notification.read_at.is_(None))
    if before is not None:
        cursor = _owned(db, user, before)
        if cursor is None:
            raise ValidationFailed("Some fields are invalid.", fields={"before": "Unknown notification."})
        q = q.where(_older_or_equal(cursor), Notification.id != cursor.id)
    rows = list(db.scalars(q.order_by(Notification.created_at.desc(), Notification.id.desc()).limit(limit + 1)))
    return rows[:limit], len(rows) > limit


def mark_read(db: Session, user: User, up_to=None) -> None:
    """up_to: that notification and everything older. None: everything."""
    q = update(Notification).where(Notification.user_id == user.id, Notification.read_at.is_(None))
    if up_to is not None:
        cursor = _owned(db, user, up_to)
        if cursor is None:
            raise ValidationFailed("Some fields are invalid.", fields={"up_to": "Unknown notification."})
        q = q.where(_older_or_equal(cursor))
    db.execute(q.values(read_at=utcnow()))
    db.commit()


def mark_one_read(db: Session, user: User, notification_id) -> bool:
    n = _owned(db, user, notification_id)
    if n is None:
        return False
    if n.read_at is None:
        n.read_at = utcnow()
        db.commit()
    return True
