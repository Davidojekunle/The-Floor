import secrets
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.models.enums import MembershipStatus, Role
from app.models.room import Membership, Room, TempHead
from app.models.user import User
from app.permissions.rules import RoomContext, can, permissions_for_role, require, resolve_role
from app.schemas.common import PageParams
from app.schemas.room import InviteOut, JoinPreview, JoinRequestItem, MembershipOut, RoomOut, RoomSummary, UserBrief
from app.utils.time import as_utc, utcnow


# ---------------------------------------------------------------- helpers

def _new_invite_code(db: Session) -> str:
    for _ in range(5):
        code = secrets.token_urlsafe(9)
        if not db.scalar(select(Room.id).where(Room.invite_code == code)):
            return code
    raise RuntimeError("Could not generate a unique invite code")


def _active_temp_head(db: Session, room_id: uuid.UUID, user_id: uuid.UUID) -> TempHead | None:
    return db.scalar(
        select(TempHead)
        .where(
            TempHead.room_id == room_id,
            TempHead.user_id == user_id,
            TempHead.revoked_at.is_(None),
            TempHead.expires_at > utcnow(),
        )
        .order_by(TempHead.expires_at.desc())
        .limit(1)
    )


def _member_count(db: Session, room_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count()).select_from(Membership).where(
            Membership.room_id == room_id, Membership.status == MembershipStatus.ACTIVE
        )
    )


def _membership_out(m: Membership) -> MembershipOut:
    return MembershipOut(membership_id=m.id, room_id=m.room_id, status=m.status)


# ---------------------------------------------------------------- room context (tenant isolation)

def get_room_context(db: Session, room_id: uuid.UUID, user: User) -> RoomContext:
    """Load the room + the caller's role in it.

    Non-members AND pending/rejected/removed members get 404, so a room's existence is never leaked.
    """
    row = db.execute(
        select(Membership, Room)
        .join(Room, Room.id == Membership.room_id)
        .where(
            Membership.room_id == room_id,
            Membership.user_id == user.id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    ).first()
    if row is None:
        raise NotFound("Room not found.")
    membership, room = row

    temp_head = _active_temp_head(db, room.id, user.id)
    role = resolve_role(membership, temp_head)
    return RoomContext(
        room=room,
        membership=membership,
        role=role,
        permissions=permissions_for_role(role),
        temp_head_expires_at=as_utc(temp_head.expires_at) if temp_head and role == Role.TEMP_HEAD else None,
    )


def room_out(db: Session, ctx: RoomContext) -> RoomOut:
    room = ctx.room
    return RoomOut(
        id=room.id,
        name=room.name,
        my_role=ctx.role,
        temp_head_expires_at=ctx.temp_head_expires_at,
        permissions=sorted(ctx.permissions),
        member_count=_member_count(db, room.id),
        invite_code=room.invite_code if can(ctx, "invite.manage") else None,
        created_at=as_utc(room.created_at),
    )


# ---------------------------------------------------------------- rooms

def create_room(db: Session, user: User, name: str) -> RoomContext:
    now = utcnow()
    room = Room(name=name, invite_code=_new_invite_code(db), created_by=user.id)
    db.add(room)
    db.flush()  # assigns room.id
    db.add(
        Membership(
            user_id=user.id,
            room_id=room.id,
            role=Role.HEAD,
            status=MembershipStatus.ACTIVE,
            joined_at=now,
        )
    )
    db.commit()
    return get_room_context(db, room.id, user)


def list_rooms_for_user(db: Session, user: User) -> list[RoomSummary]:
    rows = db.execute(
        select(Membership, Room)
        .join(Room, Room.id == Membership.room_id)
        .where(Membership.user_id == user.id, Membership.status == MembershipStatus.ACTIVE)
        .order_by(Room.name, Room.created_at)
    ).all()
    if not rows:
        return []

    room_ids = [room.id for _, room in rows]
    temp_head_rooms = set(
        db.scalars(
            select(TempHead.room_id).where(
                TempHead.user_id == user.id,
                TempHead.room_id.in_(room_ids),
                TempHead.revoked_at.is_(None),
                TempHead.expires_at > utcnow(),
            )
        )
    )

    roles = {
        room.id: resolve_role(m, True if room.id in temp_head_rooms else None) for m, room in rows
    }

    # pending join requests only matter where the caller can act on them (join.manage)
    manage_ids = [rid for rid, role in roles.items() if "join.manage" in permissions_for_role(role)]
    counts: dict[uuid.UUID, int] = {}
    if manage_ids:
        counts = dict(
            db.execute(
                select(Membership.room_id, func.count())
                .where(Membership.room_id.in_(manage_ids), Membership.status == MembershipStatus.PENDING)
                .group_by(Membership.room_id)
            ).all()
        )

    return [
        RoomSummary(id=room.id, name=room.name, my_role=roles[room.id], pending_count=counts.get(room.id, 0))
        for _, room in rows
    ]


def regenerate_invite(db: Session, ctx: RoomContext) -> InviteOut:
    require(ctx, "invite.manage")
    ctx.room.invite_code = _new_invite_code(db)
    db.commit()
    return InviteOut(invite_code=ctx.room.invite_code)


# ---------------------------------------------------------------- joining via invite link

def _room_by_invite(db: Session, invite_code: str) -> Room:
    room = db.scalar(select(Room).where(Room.invite_code == invite_code))
    if room is None:
        raise NotFound("This invite link is invalid or has been replaced.")
    return room


def _existing_membership(db: Session, room_id: uuid.UUID, user_id: uuid.UUID) -> Membership | None:
    return db.scalar(select(Membership).where(Membership.room_id == room_id, Membership.user_id == user_id))


def join_preview(db: Session, user: User, invite_code: str) -> JoinPreview:
    room = _room_by_invite(db, invite_code)
    m = _existing_membership(db, room.id, user.id)
    return JoinPreview(
        room_name=room.name,
        member_count=_member_count(db, room.id),
        already_requested=bool(m and m.status == MembershipStatus.PENDING),
        already_member=bool(m and m.status == MembershipStatus.ACTIVE),
    )


def request_join(db: Session, user: User, invite_code: str) -> MembershipOut:
    room = _room_by_invite(db, invite_code)
    m = _existing_membership(db, room.id, user.id)

    if m is None:
        m = Membership(user_id=user.id, room_id=room.id, role=Role.MEMBER, status=MembershipStatus.PENDING)
        db.add(m)
    elif m.status == MembershipStatus.ACTIVE:
        raise Conflict("You're already a member of this room.")
    elif m.status == MembershipStatus.PENDING:
        raise Conflict("You've already requested to join this room.")
    else:
        # rejected or removed earlier: allowed to ask again, still needs approval
        m.status = MembershipStatus.PENDING
        m.role = Role.MEMBER
        m.created_at = utcnow()
        m.joined_at = None

    try:
        db.commit()
    except IntegrityError:  # two simultaneous requests
        db.rollback()
        raise Conflict("You've already requested to join this room.")
    return _membership_out(m)


# ---------------------------------------------------------------- join request management (head)

def list_join_requests(db: Session, ctx: RoomContext, params: PageParams) -> tuple[list[JoinRequestItem], int]:
    require(ctx, "join.manage")
    where = (Membership.room_id == ctx.room.id, Membership.status == MembershipStatus.PENDING)

    total = db.scalar(select(func.count()).select_from(Membership).where(*where))
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(*where)
        .order_by(Membership.created_at, Membership.id)
        .offset(params.offset)
        .limit(params.limit)
    ).all()

    items = [
        JoinRequestItem(
            membership_id=m.id,
            user=UserBrief(id=u.id, name=u.name),
            requested_at=as_utc(m.created_at),
        )
        for m, u in rows
    ]
    return items, total


def decide_join_request(db: Session, ctx: RoomContext, membership_id: uuid.UUID, *, approve: bool) -> MembershipOut:
    require(ctx, "join.manage")

    # scoped to THIS room: a membership id from another room is simply "not found"
    m = db.scalar(
        select(Membership).where(Membership.id == membership_id, Membership.room_id == ctx.room.id)
    )
    if m is None:
        raise NotFound("Join request not found.")

    target = MembershipStatus.ACTIVE if approve else MembershipStatus.REJECTED
    if m.status == target:
        return _membership_out(m)  # repeating the same decision is safe
    if m.status != MembershipStatus.PENDING:
        raise Conflict("This request is no longer pending.")

    m.status = target
    if approve:
        m.joined_at = utcnow()
    db.commit()
    return _membership_out(m)
