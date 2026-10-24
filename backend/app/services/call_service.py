"""Calls, C1: instant calls in a room or about a task (contract v4).

A call is live from the moment it starts. The provider (services/video.py) reports joins and leaves through a
signed webhook; a check every minute also asks it directly, so a lost message (or a laptop with no webhook)
can't leave a call open. A call ends 2 minutes after the last person leaves, when someone with the right
presses "End for everyone", or at the 3-hour hard stop.
"""
import logging
import secrets
import uuid
from datetime import timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import CallEnded, CallFull, Forbidden, NotFound, TaskNotApproved
from app.models.call import Call, CallKind, CallParticipant, CallStatus
from app.models.enums import ApprovalStatus
from app.models.task import Task
from app.models.user import User
from app.permissions.rules import RoomContext, can, require
from app.realtime import events as live
from app.schemas.call import CallOut, JoinPass, LiveCall
from app.schemas.room import UserBrief
from app.services import chat_service, video
from app.utils.time import as_utc, utcnow

logger = logging.getLogger("taskroom.calls")


# ================================================================== reading

def _open_participants(db: Session, call_id) -> list[CallParticipant]:
    return list(db.scalars(select(CallParticipant).where(CallParticipant.call_id == call_id,
                                                         CallParticipant.left_at.is_(None))))


def _in_call(db: Session, call: Call) -> list[UserBrief]:
    """Who's in right now: one entry per person, however many tabs they joined from."""
    if call.status != CallStatus.LIVE:
        return []
    ids = list(dict.fromkeys(p.user_id for p in _open_participants(db, call.id) if p.user_id))
    names = dict(db.execute(select(User.id, User.name).where(User.id.in_(ids))).all()) if ids else {}
    return [UserBrief(id=i, name=names[i]) for i in ids if i in names]


def _can_end(ctx: RoomContext, call: Call) -> bool:
    return call.created_by == ctx.membership.user_id or can(ctx, "call.manage_any")


def call_out(db: Session, ctx: RoomContext, call: Call) -> CallOut:
    task = db.get(Task, call.task_id) if call.task_id else None
    creator = db.get(User, call.created_by) if call.created_by else None
    return CallOut(
        id=call.id, room_id=call.room_id, task={"id": task.id, "title": task.title} if task else None,
        kind=call.kind, status=call.status, missed=call.missed, title=call.title, description=call.description,
        starts_at=as_utc(call.starts_at) if call.starts_at else None,
        ends_at_planned=as_utc(call.ends_at_planned) if call.ends_at_planned else None,
        started_at=as_utc(call.started_at) if call.started_at else None,
        ended_at=as_utc(call.ended_at) if call.ended_at else None,
        joinable_from=as_utc(call.started_at or call.created_at),
        created_by=UserBrief(id=creator.id, name=creator.name) if creator else None,
        participants=_in_call(db, call), external_url=call.external_url,
        can_end=call.status == CallStatus.LIVE and _can_end(ctx, call), can_edit=False,
    )


def _visible(db: Session, ctx: RoomContext, call_id) -> Call:
    """A call in this room; one about a task only while the task is approved (what members can see)."""
    call = db.scalar(select(Call).where(Call.id == call_id, Call.room_id == ctx.room.id))
    if call is None:
        raise NotFound("Call not found.")
    if call.task_id:
        task = db.get(Task, call.task_id)
        if task is not None and task.approval_status != ApprovalStatus.APPROVED and not can(ctx, "task.approve") \
                and task.created_by != ctx.membership.user_id:
            raise NotFound("Call not found.")
    return call


def get_call(db: Session, ctx: RoomContext, call_id) -> CallOut:
    return call_out(db, ctx, _visible(db, ctx, call_id))


def list_calls(db: Session, ctx: RoomContext, *, status: str | None, task_id, offset: int, limit: int):
    q = select(Call).where(Call.room_id == ctx.room.id)
    if status:
        q = q.where(Call.status == status)
    if task_id:
        q = q.where(Call.task_id == task_id)
    total = db.scalar(select(func.count()).select_from(q.subquery()))
    rows = db.scalars(q.order_by(Call.created_at.desc(), Call.id).offset(offset).limit(limit)).all()
    return [call_out(db, ctx, c) for c in rows], total


def _live(db: Session, room_id, task_id) -> Call | None:
    q = select(Call).where(Call.room_id == room_id, Call.status == CallStatus.LIVE)
    q = q.where(Call.task_id == task_id) if task_id else q.where(Call.task_id.is_(None))
    return db.scalar(q)


def live_calls_by_room(db: Session, room_ids) -> dict:
    """For the room switcher's "live" dot: each room's live room call (not task calls) and how many are in."""
    if not get_settings().calls_enabled or not room_ids:
        return {}
    calls = db.scalars(select(Call).where(Call.room_id.in_(room_ids), Call.status == CallStatus.LIVE,
                                          Call.task_id.is_(None))).all()
    return {c.room_id: LiveCall(id=c.id, participant_count=len(_in_call_ids(db, c.id))) for c in calls}


def live_call_for_task(db: Session, task_id) -> LiveCall | None:
    if not get_settings().calls_enabled:
        return None
    c = db.scalar(select(Call).where(Call.task_id == task_id, Call.status == CallStatus.LIVE))
    return LiveCall(id=c.id, participant_count=len(_in_call_ids(db, c.id))) if c else None


def _in_call_ids(db: Session, call_id) -> set:
    return {p.user_id for p in _open_participants(db, call_id) if p.user_id}


# ================================================================== starting, joining, ending

def start_call(db: Session, ctx: RoomContext, task_id) -> tuple[CallOut, bool]:
    """Start one, or return the call already live in the room (or on the task). (call, created)."""
    require(ctx, "call.start")
    task = None
    if task_id:
        task = db.scalar(select(Task).where(Task.id == task_id, Task.room_id == ctx.room.id))
        if task is None:
            raise NotFound("Task not found.")
        if task.approval_status != ApprovalStatus.APPROVED:
            raise TaskNotApproved("A call about a task can start once the task is approved.")
    existing = _live(db, ctx.room.id, task_id)
    if existing is not None:
        return call_out(db, ctx, existing), False

    s, now = get_settings(), utcnow()
    name = f"floor-{secrets.token_hex(10)}"
    hard_stop = now + timedelta(minutes=s.call_max_minutes)
    video.provider().create_room(name, hard_stop, s.call_max_participants)  # before saving: a failure saves nothing
    starter = db.get(User, ctx.membership.user_id)
    call = Call(
        room_id=ctx.room.id, task_id=task.id if task else None, kind=CallKind.INSTANT, status=CallStatus.LIVE,
        title=f"Call about {task.title}" if task else f"Call in {ctx.room.name}",
        started_at=now, hard_stop_at=hard_stop, empty_since=now, created_by=starter.id, provider_room=name,
    )
    db.add(call)
    try:
        db.flush()
    except IntegrityError:  # someone started one at the same moment: use theirs
        db.rollback()
        video.provider().delete_room(name)
        existing = _live(db, ctx.room.id, task_id)
        if existing is None:
            raise
        return call_out(db, ctx, existing), False

    chat_service.post_system(db, room_id=ctx.room.id, event="call_started", actor_id=starter.id, task=task,
                             detail={"call_id": str(call.id)})
    from app.services import notification_service as notes
    notes.call_started(db, ctx, call, task)
    live.call_changed(db, call)
    db.commit()
    return call_out(db, ctx, call), True


def join_call(db: Session, ctx: RoomContext, call_id) -> JoinPass:
    """This person's own pass into the call, carrying their name. Good until the hard stop."""
    call = _visible(db, ctx, call_id)
    if call.status != CallStatus.LIVE:
        raise CallEnded("This call has ended.")
    s = get_settings()
    me = ctx.membership.user_id
    if me not in _in_call_ids(db, call.id) and len(_in_call_ids(db, call.id)) >= s.call_max_participants:
        raise CallFull(f"This call is full ({s.call_max_participants} people).")
    user = db.get(User, me)
    expires = as_utc(call.hard_stop_at)
    token = video.provider().token(call.provider_room, user_id=str(me), user_name=user.name, expires_at=expires,
                                   owner=_can_end(ctx, call))
    return JoinPass(provider="livekit", server_url=video.server_url(), token=token, expires_at=expires)


def end_call(db: Session, ctx: RoomContext, call_id) -> None:
    call = _visible(db, ctx, call_id)
    if call.status != CallStatus.LIVE:
        raise CallEnded("This call has already ended.")
    if not _can_end(ctx, call):
        raise Forbidden("Only whoever started the call, the head or a temp head can end it for everyone.")
    _finish(db, call)
    db.commit()


def _finish(db: Session, call: Call) -> None:
    """End a live call: close who's in, close the provider room, and post "Call ended" in the chat."""
    now = utcnow()
    people = {p.user_id for p in db.scalars(select(CallParticipant).where(CallParticipant.call_id == call.id))
              if p.user_id}
    db.execute(update(CallParticipant).where(CallParticipant.call_id == call.id, CallParticipant.left_at.is_(None))
               .values(left_at=now))
    call.status, call.ended_at, call.empty_since = CallStatus.ENDED, now, None
    if call.provider_room:
        video.provider().delete_room(call.provider_room)
    minutes = max(1, round((now - as_utc(call.started_at or call.created_at)).total_seconds() / 60)) if people else 0
    task = db.get(Task, call.task_id) if call.task_id else None
    chat_service.post_system(db, room_id=call.room_id, event="call_ended", task=task,
                             detail={"call_id": str(call.id), "minutes": minutes, "people": len(people)})
    live.call_changed(db, call)


# ================================================================== who's in (webhook and the minute check)

def _joined(db: Session, call: Call, user_id, session_id: str, joined_at) -> None:
    if db.scalar(select(CallParticipant.id).where(CallParticipant.session_id == session_id)):
        return  # the webhook can deliver the same join twice
    db.add(CallParticipant(call_id=call.id, user_id=user_id, session_id=session_id, joined_at=joined_at))
    call.empty_since = None
    live.call_changed(db, call)


def _left(db: Session, call: Call, p: CallParticipant, left_at) -> None:
    if p.left_at is not None:
        return
    p.left_at = left_at
    db.flush()
    if not _open_participants(db, call.id):
        call.empty_since = left_at
    live.call_changed(db, call)


def _user_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def handle_webhook(db: Session, event: dict) -> None:
    """LiveKit's events: participant_joined, participant_left (and room_finished, which the check covers)."""
    kind, room, who = event.get("event"), (event.get("room") or {}).get("name"), event.get("participant") or {}
    call = db.scalar(select(Call).where(Call.provider_room == room, Call.status == CallStatus.LIVE))
    if call is None:
        return  # a call we've already ended, or not ours
    session = who.get("sid")
    if kind == "participant_joined" and session:
        at = who.get("joined_at")
        _joined(db, call, _user_uuid(who.get("identity")), session, video.epoch(at) if at else utcnow())
    elif kind == "participant_left" and session:
        p = db.scalar(select(CallParticipant).where(CallParticipant.session_id == session))
        if p is not None:
            _left(db, call, p, utcnow())
    db.commit()


def check_calls(db: Session) -> int:
    """Every minute: match "who's in" to the provider, end empty and overdue calls. Returns how many ended."""
    s, now, ended = get_settings(), utcnow(), 0
    for call in db.scalars(select(Call).where(Call.status == CallStatus.LIVE)).all():
        if call.hard_stop_at and now >= as_utc(call.hard_stop_at):
            _finish(db, call)
            ended += 1
            continue
        try:
            present = video.provider().presence(call.provider_room) if call.provider_room else []
        except Exception:  # provider down: keep what we know, try again next minute
            logger.warning("presence check failed for call %s", call.id)
            present = None
        if present is not None:
            here = {p.session_id: p for p in present}
            for p in _open_participants(db, call.id):
                if p.session_id not in here:
                    _left(db, call, p, now)  # left without the webhook telling us
            known = set(db.scalars(select(CallParticipant.session_id).where(CallParticipant.call_id == call.id)))
            for sid, p in here.items():
                if sid not in known:
                    _joined(db, call, _user_uuid(p.user_id), sid, p.joined_at)
        db.flush()
        if not _open_participants(db, call.id):
            call.empty_since = call.empty_since or now
            if (now - as_utc(call.empty_since)).total_seconds() >= s.call_empty_grace_seconds:
                _finish(db, call)
                ended += 1
    db.commit()
    return ended


async def run_checker(session_factory, interval: float) -> None:
    """Background loop started with the app (one process), like the email sender."""
    import asyncio

    from starlette.concurrency import run_in_threadpool

    while True:
        try:
            await run_in_threadpool(_check_once, session_factory)
        except Exception:
            logger.exception("call check failed")
        await asyncio.sleep(interval)


def _check_once(session_factory) -> None:
    gen = session_factory()
    db = next(gen)
    try:
        check_calls(db)
    finally:
        gen.close()


# ================================================================== people leaving, tasks and rooms going

def drop_from_calls(db: Session, room_id, user_id) -> None:
    """They left the room or were removed: out of its live calls straight away. The caller commits."""
    now = utcnow()
    for call in db.scalars(select(Call).where(Call.room_id == room_id, Call.status == CallStatus.LIVE)).all():
        mine = [p for p in _open_participants(db, call.id) if p.user_id == user_id]
        video.provider().eject(call.provider_room, [str(user_id)]) if call.provider_room else None
        for p in mine:
            _left(db, call, p, now)


def end_for_task(db: Session, task_id) -> None:
    """The task is being deleted: its live call ends first, and past calls keep with the task link cleared.
    The caller commits."""
    call = db.scalar(select(Call).where(Call.task_id == task_id, Call.status == CallStatus.LIVE))
    if call is not None:
        _finish(db, call)
    db.flush()
    db.execute(update(Call).where(Call.task_id == task_id).values(task_id=None))


def close_provider_rooms(db: Session, room_id) -> None:
    """The room is being deleted (its calls go with it): close any live provider rooms first."""
    for name in db.scalars(select(Call.provider_room).where(Call.room_id == room_id, Call.status == CallStatus.LIVE)):
        if name:
            video.provider().delete_room(name)
