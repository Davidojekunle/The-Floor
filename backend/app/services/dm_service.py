"""Private DMs. Rules:

- The admin switch decides who has them: off, staff only (both people must be staff), or everyone.
- You can start a conversation only with someone you share an active room with. Once started it stays
  open, even if one of you later leaves the room (David's choice), until either of you blocks the other.
- Blocking stops new messages both ways and hides nothing that was already said; unblocking reopens it.
- New messages reach the other person live and as a push (no bell item, like room chat), never if blocked.
"""
import uuid
from datetime import datetime

from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.orm import Session, aliased

from app.core.errors import Forbidden, NotFound
from app.core.ratelimit import MINUTE, limiter
from app.models.direct import DirectMessage, DirectThread, UserBlock
from app.models.enums import MembershipStatus
from app.models.room import Membership
from app.models.user import User
from app.realtime import events as live
from app.services import push_service, site_service
from app.services.notification_service import preview
from app.utils.time import as_utc, utcnow

PAGE = 50


# ---- who may use them

def _mode(db: Session) -> str:
    return site_service.get(db).get("direct_messages", "staff")


def enabled_for(db: Session, user: User | None) -> bool:
    if user is None:
        return False
    mode = _mode(db)
    return mode == "everyone" or (mode == "staff" and bool(user.is_staff))


def _require(db: Session, user: User) -> None:
    if not enabled_for(db, user):
        raise NotFound("Not found.")


def shares_room(db: Session, a: uuid.UUID, b: uuid.UUID) -> bool:
    m1, m2 = aliased(Membership), aliased(Membership)
    return bool(db.scalar(select(exists().where(
        m1.user_id == a, m2.user_id == b, m1.room_id == m2.room_id,
        m1.status == MembershipStatus.ACTIVE, m2.status == MembershipStatus.ACTIVE,
    ))))


def _blocked(db: Session, blocker: uuid.UUID, blocked: uuid.UUID) -> bool:
    return db.get(UserBlock, (blocker, blocked)) is not None


def _either_blocked(db: Session, a: uuid.UUID, b: uuid.UUID) -> bool:
    return _blocked(db, a, b) or _blocked(db, b, a)


# ---- threads

def _pair(a: uuid.UUID, b: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    return (a, b) if str(a) < str(b) else (b, a)


def _other_id(t: DirectThread, me: uuid.UUID) -> uuid.UUID:
    return t.user_high_id if t.user_low_id == me else t.user_low_id


def _my_read_at(t: DirectThread, me: uuid.UUID) -> datetime | None:
    return as_utc(t.low_read_at if t.user_low_id == me else t.high_read_at)


def _mine(db: Session, user: User, thread_id: uuid.UUID) -> DirectThread:
    t = db.get(DirectThread, thread_id)
    if t is None or user.id not in (t.user_low_id, t.user_high_id):
        raise NotFound("Conversation not found.")
    return t


def _message_out(m: DirectMessage) -> dict:
    return {"id": m.id, "sender_id": m.sender_id, "body": None if m.deleted_at else m.body,
            "deleted": m.deleted_at is not None, "created_at": as_utc(m.created_at)}


def _unread(db: Session, t: DirectThread, me: uuid.UUID) -> int:
    q = select(func.count()).select_from(DirectMessage).where(
        DirectMessage.thread_id == t.id, DirectMessage.sender_id != me, DirectMessage.deleted_at.is_(None))
    read_at = _my_read_at(t, me)
    if read_at is not None:
        q = q.where(DirectMessage.created_at > read_at)
    return db.scalar(q) or 0


def _thread_out(db: Session, t: DirectThread, me: User) -> dict:
    other = db.get(User, _other_id(t, me.id))
    last = db.scalar(select(DirectMessage).where(DirectMessage.thread_id == t.id)
                     .order_by(DirectMessage.created_at.desc(), DirectMessage.id.desc()).limit(1))
    you_blocked = _blocked(db, me.id, other.id)
    return {
        "id": t.id,
        "other": {"id": other.id, "name": other.name},
        "last_message": _message_out(last) if last else None,
        "last_message_at": as_utc(t.last_message_at),
        "unread": _unread(db, t, me.id),
        "you_blocked": you_blocked,
        "can_send": not you_blocked and not _blocked(db, other.id, me.id),
    }


def start(db: Session, user: User, other_id: uuid.UUID) -> dict:
    """Open (or find) the conversation with someone. New ones need a shared room."""
    _require(db, user)
    other = db.get(User, other_id)
    if other is None or other.id == user.id or not enabled_for(db, other):
        raise NotFound("You can't message that person.")
    low, high = _pair(user.id, other.id)
    t = db.scalar(select(DirectThread).where(DirectThread.user_low_id == low, DirectThread.user_high_id == high))
    if t is None:
        if not shares_room(db, user.id, other.id):
            raise Forbidden("You can only start a conversation with someone in one of your rooms.")
        if _either_blocked(db, user.id, other.id):
            raise Forbidden("You can't message this person.")
        t = DirectThread(user_low_id=low, user_high_id=high, created_at=utcnow())
        db.add(t)
        db.commit()
    return _thread_out(db, t, user)


def list_threads(db: Session, user: User) -> list[dict]:
    _require(db, user)
    threads = db.scalars(
        select(DirectThread).where(or_(DirectThread.user_low_id == user.id, DirectThread.user_high_id == user.id))
        .order_by(func.coalesce(DirectThread.last_message_at, DirectThread.created_at).desc())
    ).all()
    return [_thread_out(db, t, user) for t in threads]


def get_thread(db: Session, user: User, thread_id: uuid.UUID) -> dict:
    _require(db, user)
    return _thread_out(db, _mine(db, user, thread_id), user)


def messages(db: Session, user: User, thread_id: uuid.UUID, before: datetime | None) -> dict:
    _require(db, user)
    t = _mine(db, user, thread_id)
    q = select(DirectMessage).where(DirectMessage.thread_id == t.id)
    if before is not None:
        q = q.where(DirectMessage.created_at < before)
    rows = db.scalars(q.order_by(DirectMessage.created_at.desc(), DirectMessage.id.desc()).limit(PAGE + 1)).all()
    has_more = len(rows) > PAGE
    return {"items": [_message_out(m) for m in reversed(rows[:PAGE])], "has_more": has_more}


def send(db: Session, user: User, thread_id: uuid.UUID, body: str) -> dict:
    _require(db, user)
    limiter.hit(f"dm:{user.id}", 60, MINUTE)
    t = _mine(db, user, thread_id)
    other_id = _other_id(t, user.id)
    if _either_blocked(db, user.id, other_id):
        raise Forbidden("You can't message this person.")
    now = utcnow()
    m = DirectMessage(thread_id=t.id, sender_id=user.id, body=body, created_at=now)
    db.add(m)
    t.last_message_at = now
    if t.user_low_id == user.id:
        t.low_read_at = now
    else:
        t.high_read_at = now
    db.flush()
    live.dm_event(db, "dm_created", t.id, {user.id, other_id}, message_id=m.id)
    push_service.queue(db, other_id, title=user.name, body=preview(body), url=f"/messages/{t.id}", tag=f"dm:{t.id}")
    db.commit()
    return _message_out(m)


def delete_message(db: Session, user: User, thread_id: uuid.UUID, message_id: uuid.UUID) -> None:
    _require(db, user)
    t = _mine(db, user, thread_id)
    m = db.get(DirectMessage, message_id)
    if m is None or m.thread_id != t.id or m.sender_id != user.id:
        raise NotFound("Message not found.")
    if m.deleted_at is None:
        m.deleted_at, m.body = utcnow(), None
        live.dm_event(db, "dm_deleted", t.id, {t.user_low_id, t.user_high_id}, message_id=m.id)
        db.commit()


def mark_read(db: Session, user: User, thread_id: uuid.UUID) -> None:
    _require(db, user)
    t = _mine(db, user, thread_id)
    now = utcnow()
    if t.user_low_id == user.id:
        t.low_read_at = now
    else:
        t.high_read_at = now
    live.dm_event(db, "dm_read", t.id, {user.id})  # your other tabs update their badge
    db.commit()


def unread_total(db: Session, user: User) -> int:
    if not enabled_for(db, user):
        return 0
    t = DirectThread
    rows = db.execute(
        select(func.count())
        .select_from(DirectMessage)
        .join(t, t.id == DirectMessage.thread_id)
        .where(
            DirectMessage.sender_id != user.id,
            DirectMessage.deleted_at.is_(None),
            or_(
                and_(t.user_low_id == user.id, or_(t.low_read_at.is_(None), DirectMessage.created_at > t.low_read_at)),
                and_(t.user_high_id == user.id, or_(t.high_read_at.is_(None), DirectMessage.created_at > t.high_read_at)),
            ),
        )
    ).scalar()
    return rows or 0


# ---- blocks

def blocks(db: Session, user: User) -> list[dict]:
    rows = db.execute(select(User.id, User.name).join(UserBlock, UserBlock.blocked_id == User.id)
                      .where(UserBlock.blocker_id == user.id).order_by(User.name)).all()
    return [{"id": r[0], "name": r[1]} for r in rows]


def block(db: Session, user: User, other_id: uuid.UUID) -> None:
    if other_id == user.id or db.get(User, other_id) is None:
        raise NotFound("No such person.")
    if not _blocked(db, user.id, other_id):
        db.add(UserBlock(blocker_id=user.id, blocked_id=other_id, created_at=utcnow()))
        _tell_both(db, user.id, other_id)
        db.commit()


def unblock(db: Session, user: User, other_id: uuid.UUID) -> None:
    b = db.get(UserBlock, (user.id, other_id))
    if b is not None:
        db.delete(b)
        _tell_both(db, user.id, other_id)
        db.commit()


def _tell_both(db: Session, a: uuid.UUID, b: uuid.UUID) -> None:
    low, high = _pair(a, b)
    t = db.scalar(select(DirectThread).where(DirectThread.user_low_id == low, DirectThread.user_high_id == high))
    if t is not None:
        live.dm_event(db, "dm_changed", t.id, {a, b})
