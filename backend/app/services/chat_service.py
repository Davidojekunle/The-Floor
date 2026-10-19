"""Room chat: messages, system events, and per-person read positions."""
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import Forbidden, NotFound, ValidationFailed
from app.models.enums import ApprovalStatus, MembershipStatus
from app.models.message import Message, MessageType
from app.models.room import Membership
from app.models.task import Stage, Task
from app.models.user import User
from app.permissions.rules import RoomContext, can, require
from app.schemas.message import EVENT_MODELS, MessageCreate, MessageOut, MessagePage, Ref, ReplyQuote
from app.schemas.room import UserBrief
from app.services import notification_service as notes
from app.services import task_common
from app.realtime import events as live
from app.utils.time import as_utc, utcnow

INVALID = "Some fields are invalid."


def _now(db: Session) -> datetime:
    """Strictly increasing within one request, so two events in one action keep their order."""
    now = utcnow()
    last = db.info.get("last_message_at")
    if last is not None and now <= last:
        now = last + timedelta(microseconds=1)
    db.info["last_message_at"] = now
    return now


# ------------------------------------------------------------------ system messages

def _user(db: Session, user_id) -> User | None:
    return db.get(User, user_id) if user_id else None


def _render(event: str, actor: str, subject: str, task: str, stage: str, detail: dict, until: str) -> str:
    return {
        "member_joined": f"{subject} joined the room",
        "task_created": f"{actor} created {task}",
        "task_approved": f"{actor} approved {subject}'s proposal {task}",
        "stage_done": f"{actor} finished {stage} on {task}",
        "task_completed": f"{task} is complete",
        "stage_blocked": f"{actor} blocked {stage} on {task}: {detail.get('reason', '')}",
        "stage_reopened": f"{actor} reopened {stage} on {task}",
        "temp_head_granted": f"{actor} made {subject} temporary head until {until}",
        "temp_head_revoked": f"{actor} ended {subject}'s temporary head role",
        "member_left": f"{actor} left the room",
        "head_transferred": f"{actor} made {subject} the head",
    }[event]


def post_system(
    db: Session,
    *,
    room_id: uuid.UUID,
    event: str,
    actor_id=None,
    subject_id=None,
    task: Task | None = None,
    stage: Stage | None = None,
    detail: dict | None = None,
) -> Message:
    """Adds a system message to the caller's transaction (the caller commits with its own change)."""
    actor, subject = _user(db, actor_id), _user(db, subject_id)
    until = ""
    if event == "temp_head_granted" and detail and actor:
        try:
            tz = ZoneInfo(actor.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            tz = ZoneInfo("UTC")
        until = datetime.fromisoformat(detail["expires_at"]).astimezone(tz).strftime("%d %b %Y").lstrip("0")
    body = _render(
        event,
        actor.name if actor else "Someone",
        subject.name if subject else "Someone",
        task.title if task else "",
        stage.title if stage else "",
        detail or {},
        until,
    )
    message = Message(
        id=uuid.uuid4(),
        room_id=room_id,
        type=MessageType.SYSTEM,
        body=body,
        task_id=task.id if task else None,
        stage_id=stage.id if stage else None,
        event_type=event,
        event_actor_id=actor_id,
        event_subject_id=subject_id,
        event_detail=detail,
        created_at=_now(db),
    )
    db.add(message)
    db.flush()
    live.message_created(db, room_id, message.id)
    return message


# ------------------------------------------------------------------ reading

def _cursor(db: Session, ctx: RoomContext, message_id: uuid.UUID, field: str) -> Message:
    m = db.scalar(select(Message).where(Message.id == message_id, Message.room_id == ctx.room.id))
    if m is None:
        raise ValidationFailed(INVALID, fields={field: "Unknown message in this room."})
    return m


def _newer_than(m: Message):
    return or_(Message.created_at > m.created_at, and_(Message.created_at == m.created_at, Message.id > m.id))


def _older_than(m: Message):
    return or_(Message.created_at < m.created_at, and_(Message.created_at == m.created_at, Message.id < m.id))


def _mention_ids(m: Message) -> list[uuid.UUID]:
    out = []
    for raw in m.mentions or []:
        try:
            out.append(uuid.UUID(str(raw)))
        except ValueError:
            continue
    return out


def _quote(original: Message | None, users: dict) -> ReplyQuote | None:
    if original is None:
        return None
    gone = original.deleted_at is not None
    return ReplyQuote(
        id=original.id, type=original.type, sender=users.get(original.sender_id), deleted=gone,
        preview=None if gone or not original.body else notes.preview(original.body),
    )


def build(db: Session, ctx: RoomContext, messages: list[Message]) -> list[MessageOut]:
    user_ids = {uid for m in messages for uid in (m.sender_id, m.event_actor_id, m.event_subject_id) if uid}
    user_ids |= {uid for m in messages if m.deleted_at is None for uid in _mention_ids(m)}
    reply_ids = {m.reply_to_id for m in messages if m.reply_to_id and m.deleted_at is None}
    originals = {o.id: o for o in db.scalars(select(Message).where(Message.id.in_(reply_ids)))} if reply_ids else {}
    user_ids |= {o.sender_id for o in originals.values() if o.sender_id}
    users = {u.id: UserBrief(id=u.id, name=u.name) for u in db.scalars(select(User).where(User.id.in_(user_ids)))} if user_ids else {}
    task_ids = {m.task_id for m in messages if m.task_id}
    tasks = {
        t.id: t for t in db.scalars(
            select(Task).where(Task.id.in_(task_ids), Task.approval_status == ApprovalStatus.APPROVED)
        )
    } if task_ids else {}
    stage_ids = {m.stage_id for m in messages if m.stage_id}
    stages = {s.id: s for s in db.scalars(select(Stage).where(Stage.id.in_(stage_ids)))} if stage_ids else {}

    can_moderate = can(ctx, "chat.delete_any")
    me = ctx.membership.user_id
    out = []
    for m in messages:
        deleted = m.deleted_at is not None
        task = tasks.get(m.task_id) if not deleted else None
        stage = stages.get(m.stage_id) if (not deleted and task and m.stage_id in stages) else None
        event = None
        if not deleted and m.type == MessageType.SYSTEM and m.event_type in EVENT_MODELS:
            event = EVENT_MODELS[m.event_type](
                type=m.event_type,
                actor=users.get(m.event_actor_id),
                subject=users.get(m.event_subject_id),
                detail=m.event_detail or None,
            )
        out.append(
            MessageOut(
                id=m.id,
                type=m.type,
                sender=users.get(m.sender_id),
                body=None if deleted else m.body,
                task=Ref(id=task.id, title=task.title) if task else None,
                stage=Ref(id=stage.id, title=stage.title) if stage else None,
                mentions=[] if deleted else [users[u] for u in _mention_ids(m) if u in users],
                reply_to=_quote(originals.get(m.reply_to_id), users) if not deleted else None,
                event=event,
                created_at=as_utc(m.created_at),
                deleted=deleted,
                can_delete=not deleted and (can_moderate or (m.type == MessageType.USER and m.sender_id == me)),
            )
        )
    return out


def list_messages(
    db: Session,
    ctx: RoomContext,
    *,
    before: uuid.UUID | None,
    after: uuid.UUID | None,
    limit: int,
    task_id: uuid.UUID | None,
) -> MessagePage:
    if before is not None and after is not None:
        raise ValidationFailed(INVALID, fields={"before": "Use before or after, not both."})

    q = select(Message).where(Message.room_id == ctx.room.id)
    if task_id is not None:
        task = task_common.load_task(db, ctx, task_id)
        if not task_common.is_approved(task):
            raise NotFound("Task not found.")  # proposals are never referenced from chat
        q = q.where(Message.task_id == task.id)

    if after is not None:
        # the `limit` messages IMMEDIATELY after the cursor, so polling never skips any
        cursor = _cursor(db, ctx, after, "after")
        rows = list(db.scalars(q.where(_newer_than(cursor)).order_by(Message.created_at, Message.id).limit(limit + 1)))
        has_more = len(rows) > limit
        rows = rows[:limit][::-1]  # newest first, like every page
    else:
        if before is not None:
            q = q.where(_older_than(_cursor(db, ctx, before, "before")))
        rows = list(db.scalars(q.order_by(Message.created_at.desc(), Message.id.desc()).limit(limit + 1)))
        has_more = len(rows) > limit
        rows = rows[:limit]

    return MessagePage(
        items=build(db, ctx, rows), has_more=has_more, last_read_message_id=ctx.membership.last_read_message_id
    )


# ------------------------------------------------------------------ writing

def _resolve_mentions(db: Session, ctx: RoomContext, body: MessageCreate) -> list[User]:
    """The picked people who are active members, aren't the sender, and whose @Name is still in the text
    (deleting "@Femi" before sending un-mentions Femi). Unknown ids are dropped quietly: someone may have left."""
    wanted = set(body.mention_ids) - {ctx.membership.user_id}
    if not wanted:
        return []
    people = db.scalars(
        select(User).join(Membership, Membership.user_id == User.id).where(
            User.id.in_(wanted), Membership.room_id == ctx.room.id, Membership.status == MembershipStatus.ACTIVE)
    ).all()
    return [u for u in people if f"@{u.name}" in body.body]


def send_message(db: Session, ctx: RoomContext, body: MessageCreate) -> MessageOut:
    require(ctx, "chat.send")
    task = stage = None
    errors: dict[str, str] = {}

    if body.stage_id is not None:
        stage = db.get(Stage, body.stage_id)
        owner = db.get(Task, stage.task_id) if stage else None
        if owner is None or owner.room_id != ctx.room.id or owner.approval_status != ApprovalStatus.APPROVED:
            errors["stage_id"] = "Unknown stage in this room."
            stage = None
        elif body.task_id is not None and body.task_id != owner.id:
            errors["stage_id"] = "This stage belongs to a different task."
            stage = None
        else:
            task = owner
    if body.task_id is not None and task is None and "stage_id" not in errors:
        candidate = db.get(Task, body.task_id)
        if candidate is None or candidate.room_id != ctx.room.id or candidate.approval_status != ApprovalStatus.APPROVED:
            errors["task_id"] = "Unknown task in this room."
        else:
            task = candidate
    if errors:
        raise ValidationFailed(INVALID, fields=errors)
    mentioned = _resolve_mentions(db, ctx, body)
    original = None
    if body.reply_to_id is not None:
        original = db.get(Message, body.reply_to_id)
        if original is None or original.room_id != ctx.room.id:
            raise ValidationFailed(INVALID, fields={"reply_to_id": "Unknown message in this room."})
        if original.deleted_at is not None:
            raise ValidationFailed(INVALID, fields={"reply_to_id": "That message was deleted."})

    message = Message(
        room_id=ctx.room.id,
        type=MessageType.USER,
        sender_id=ctx.membership.user_id,
        body=body.body,
        task_id=task.id if task else None,
        stage_id=stage.id if stage else None,
        mentions=[str(u.id) for u in mentioned] or None,
        reply_to_id=original.id if original else None,
        created_at=_now(db),
    )
    db.add(message)
    db.flush()
    live.message_created(db, ctx.room.id, message.id)
    replied_to = original.sender_id if original is not None and original.type == MessageType.USER else None
    notes.chat_message(db, ctx.room, _user(db, ctx.membership.user_id), message.id, body.body,
                       {u.id for u in mentioned}, replied_to=replied_to)
    db.commit()
    return build(db, ctx, [message])[0]


def delete_message(db: Session, ctx: RoomContext, message_id: uuid.UUID) -> None:
    m = db.scalar(select(Message).where(Message.id == message_id, Message.room_id == ctx.room.id))
    if m is None:
        raise NotFound("Message not found.")
    if m.deleted_at is not None:
        return  # safe to repeat
    mine = m.type == MessageType.USER and m.sender_id == ctx.membership.user_id
    if not (mine or can(ctx, "chat.delete_any")):
        raise Forbidden("You can only delete your own messages.")
    m.deleted_at, m.deleted_by = utcnow(), ctx.membership.user_id
    m.body, m.event_detail = None, None  # the content is really gone, not just hidden
    live.message_deleted(db, ctx.room.id, m.id)
    db.commit()


def mark_read(db: Session, ctx: RoomContext, up_to: uuid.UUID | None) -> None:
    if up_to is not None:
        target = _cursor(db, ctx, up_to, "up_to")
    else:
        target = db.scalar(
            select(Message).where(Message.room_id == ctx.room.id).order_by(Message.created_at.desc(), Message.id.desc()).limit(1)
        )
        if target is None:
            return
    current = db.get(Message, ctx.membership.last_read_message_id) if ctx.membership.last_read_message_id else None
    if current is not None and (as_utc(current.created_at), current.id) >= (as_utc(target.created_at), target.id):
        return  # the read position only moves forward
    ctx.membership.last_read_message_id = target.id
    db.commit()


def unread_counts(db: Session, user_id: uuid.UUID, room_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
    """Per room: messages after my read position, not deleted, not mine, not about my own actions."""
    if not room_ids:
        return {}
    pointer = aliased(Message)
    return dict(
        db.execute(
            select(Membership.room_id, func.count(Message.id))
            .select_from(Membership)
            .join(Message, Message.room_id == Membership.room_id)
            .outerjoin(pointer, pointer.id == Membership.last_read_message_id)
            .where(
                Membership.user_id == user_id,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.room_id.in_(room_ids),
                Message.deleted_at.is_(None),
                or_(Message.sender_id.is_(None), Message.sender_id != user_id),
                or_(Message.event_actor_id.is_(None), Message.event_actor_id != user_id),
                or_(
                    pointer.id.is_(None),
                    Message.created_at > pointer.created_at,
                    and_(Message.created_at == pointer.created_at, Message.id > pointer.id),
                ),
            )
            .group_by(Membership.room_id)
        ).all()
    )
