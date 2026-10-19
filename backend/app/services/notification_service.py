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
}
TYPES = tuple(CATEGORY)
SWITCHES = ("email_enabled", "requests", "decisions", "assignments", "daily_digest")
_DUE = "_notification_email_due"  # per-transaction: (user, category) -> due time, for rows not yet flushed


# ================================================================== settings and mutes

def settings_for(db: Session, user_id) -> NotificationSettings:
    """The stored row, or an unsaved one with every switch on."""
    row = db.get(NotificationSettings, user_id)
    if row is None:
        row = NotificationSettings(user_id=user_id, email_enabled=True, requests=True, decisions=True,
                                   assignments=True, daily_digest=True)
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
    return n


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
            for uid in participants[s.id]:
                notify(db, uid, "stage_ready", f"“{s.title}” on “{task.title}” is ready for you",
                       room=ctx.room, task=task, stage=s, actor=actor)
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
