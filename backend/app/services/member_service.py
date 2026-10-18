import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import case, delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import AlreadyHead, Forbidden, MemberNotActive, NotFound, ValidationFailed
from app.models.enums import MembershipStatus, Role
from app.models.room import Membership, TempHead
from app.models.tag import MembershipTag, Tag
from app.models.task import Stage, StageAssignee, Task
from app.models.user import User
from app.permissions.rules import RoomContext, require
from app.schemas.common import PageParams
from app.schemas.member import MemberOut, TagBrief
from app.schemas.room import UserBrief
from app.services import chat_service
from app.utils.time import as_utc, utcnow


def _build_members(db: Session, room_id: uuid.UUID, rows: list[tuple[Membership, User]]) -> list[MemberOut]:
    """Turn (Membership, User) rows into MemberOut, loading tags and temp-head status in two queries."""
    if not rows:
        return []

    membership_ids = [m.id for m, _ in rows]
    tags_by_member: dict[uuid.UUID, list[TagBrief]] = {mid: [] for mid in membership_ids}
    for membership_id, tag in db.execute(
        select(MembershipTag.membership_id, Tag)
        .join(Tag, Tag.id == MembershipTag.tag_id)
        .where(MembershipTag.membership_id.in_(membership_ids))
        .order_by(func.lower(Tag.name))
    ):
        tags_by_member[membership_id].append(TagBrief(id=tag.id, name=tag.name))

    temp_head_until = dict(
        db.execute(
            select(TempHead.user_id, func.max(TempHead.expires_at))
            .where(
                TempHead.room_id == room_id,
                TempHead.revoked_at.is_(None),
                TempHead.expires_at > utcnow(),
            )
            .group_by(TempHead.user_id)
        ).all()
    )

    out = []
    for m, u in rows:
        if m.role == Role.HEAD:
            role = Role.HEAD
        elif u.id in temp_head_until:
            role = Role.TEMP_HEAD
        else:
            role = Role.MEMBER
        out.append(
            MemberOut(
                membership_id=m.id,
                user=UserBrief(id=u.id, name=u.name),
                role=role,
                temp_head_expires_at=as_utc(temp_head_until[u.id]) if role == Role.TEMP_HEAD else None,
                tags=tags_by_member[m.id],
                joined_at=as_utc(m.joined_at),
            )
        )
    return out


def _active_member_row(db: Session, ctx: RoomContext, membership_id: uuid.UUID) -> tuple[Membership, User]:
    """Scoped to THIS room and to active members only."""
    row = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(
            Membership.id == membership_id,
            Membership.room_id == ctx.room.id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    ).first()
    if row is None:
        raise NotFound("Member not found.")
    return row


def _active_temp_head_users(room_id):
    return select(TempHead.user_id).where(
        TempHead.room_id == room_id, TempHead.revoked_at.is_(None), TempHead.expires_at > utcnow()
    )


def list_members(
    db: Session, ctx: RoomContext, params: PageParams, tag_id: uuid.UUID | None = None, role: str | None = None
) -> tuple[list[MemberOut], int]:
    where = [Membership.room_id == ctx.room.id, Membership.status == MembershipStatus.ACTIVE]

    if role == Role.HEAD:
        where.append(Membership.role == Role.HEAD)
    elif role == Role.TEMP_HEAD:
        where += [Membership.role != Role.HEAD, Membership.user_id.in_(_active_temp_head_users(ctx.room.id))]
    elif role == Role.MEMBER:
        where += [Membership.role != Role.HEAD, Membership.user_id.not_in(_active_temp_head_users(ctx.room.id))]

    if tag_id is not None:
        if db.scalar(select(Tag.id).where(Tag.id == tag_id, Tag.room_id == ctx.room.id)) is None:
            raise NotFound("Tag not found.")
        where.append(Membership.id.in_(select(MembershipTag.membership_id).where(MembershipTag.tag_id == tag_id)))

    total = db.scalar(select(func.count()).select_from(Membership).where(*where))
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(*where)
        .order_by(case((Membership.role == Role.HEAD, 0), else_=1), func.lower(User.name), Membership.id)
        .offset(params.offset)
        .limit(params.limit)
    ).all()
    return _build_members(db, ctx.room.id, rows), total


def set_member_tags(db: Session, ctx: RoomContext, membership_id: uuid.UUID, tag_ids: list[uuid.UUID]) -> MemberOut:
    require(ctx, "tag.manage")
    m, u = _active_member_row(db, ctx, membership_id)

    wanted = set(tag_ids)
    if wanted:
        found = set(db.scalars(select(Tag.id).where(Tag.room_id == ctx.room.id, Tag.id.in_(wanted))))
        if found != wanted:
            raise ValidationFailed(
                "Some fields are invalid.", fields={"tag_ids": "One or more tags don't exist in this room."}
            )

    db.execute(delete(MembershipTag).where(MembershipTag.membership_id == m.id))
    for tag_id in wanted:
        db.add(MembershipTag(membership_id=m.id, tag_id=tag_id))
    db.commit()
    return _build_members(db, ctx.room.id, [(m, u)])[0]


def remove_member(db: Session, ctx: RoomContext, membership_id: uuid.UUID) -> None:
    require(ctx, "member.remove")

    m = db.scalar(
        select(Membership).where(Membership.id == membership_id, Membership.room_id == ctx.room.id)
    )
    if m is None:
        raise NotFound("Member not found.")
    if m.role == Role.HEAD:
        raise Forbidden("The head of a room can't be removed.")
    if m.status == MembershipStatus.REMOVED:
        return  # already removed: repeating is safe
    if m.status != MembershipStatus.ACTIVE:
        raise MemberNotActive("Only active members can be removed. Use reject for pending requests.")

    m.status = MembershipStatus.REMOVED
    db.execute(delete(MembershipTag).where(MembershipTag.membership_id == m.id))
    # a temp-head grant must not come back to life if this person is later re-approved
    db.execute(
        TempHead.__table__.update()
        .where(TempHead.room_id == ctx.room.id, TempHead.user_id == m.user_id, TempHead.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    # release this person's stage assignments in this room (their tag-based stages are already covered by the tag clear)
    db.execute(
        delete(StageAssignee).where(
            StageAssignee.user_id == m.user_id,
            StageAssignee.stage_id.in_(
                select(Stage.id).join(Task, Task.id == Stage.task_id).where(Task.room_id == ctx.room.id)
            ),
        )
    )
    db.commit()


# ------------------------------------------------------------------ temporary head (phase 5)

MAX_TEMP_HEAD_DAYS = 90


def _latest_allowed_expiry(db: Session, ctx: RoomContext) -> datetime:
    """End of the 90th day after today, in the GRANTING head's profile timezone.

    Measured by day, not 90 x 24h, so every day a date picker offers is accepted
    (the UI sends 23:59:59 local for a picked day).
    """
    head = db.get(User, ctx.membership.user_id)
    try:
        tz = ZoneInfo(head.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        tz = ZoneInfo("UTC")
    today = utcnow().astimezone(tz).date()
    return datetime.combine(today + timedelta(days=MAX_TEMP_HEAD_DAYS), time.max, tzinfo=tz)


def set_temp_head(db: Session, ctx: RoomContext, membership_id: uuid.UUID, expires_at: datetime) -> MemberOut:
    """Grant, extend, or shorten: the new expiry replaces any current grant."""
    require(ctx, "tempHead.manage")
    m, u = _active_member_row(db, ctx, membership_id)
    if m.role == Role.HEAD:
        raise AlreadyHead("The head already has every permission in this room.")

    now = utcnow()
    latest = _latest_allowed_expiry(db, ctx)
    if expires_at <= now:
        raise ValidationFailed("Some fields are invalid.", fields={"expires_at": "Pick a moment in the future."})
    if expires_at > latest:
        raise ValidationFailed(
            "Some fields are invalid.",
            fields={"expires_at": f"Temporary head can last at most {MAX_TEMP_HEAD_DAYS} days (until the end of {latest.date().isoformat()})."},
        )

    # end any current grant (rows are kept as history), then record the new one
    _end_grants(db, ctx.room.id, m.user_id, now)
    db.add(TempHead(room_id=ctx.room.id, user_id=m.user_id, granted_by=ctx.membership.user_id, expires_at=expires_at))
    chat_service.post_system(
        db, room_id=ctx.room.id, event="temp_head_granted", actor_id=ctx.membership.user_id,
        subject_id=m.user_id, detail={"expires_at": expires_at.isoformat()},
    )
    db.commit()
    return _build_members(db, ctx.room.id, [(m, u)])[0]


def revoke_temp_head(db: Session, ctx: RoomContext, membership_id: uuid.UUID) -> None:
    """Safe to repeat: revoking someone who isn't temp head is a no-op."""
    require(ctx, "tempHead.manage")
    m, _ = _active_member_row(db, ctx, membership_id)
    if _end_grants(db, ctx.room.id, m.user_id, utcnow()):  # only announce if something actually ended
        chat_service.post_system(
            db, room_id=ctx.room.id, event="temp_head_revoked", actor_id=ctx.membership.user_id, subject_id=m.user_id
        )
    db.commit()


def _end_grants(db: Session, room_id: uuid.UUID, user_id: uuid.UUID, now: datetime) -> int:
    """Ends any active grant; returns how many were ended."""
    return db.execute(
        TempHead.__table__.update()
        .where(TempHead.room_id == room_id, TempHead.user_id == user_id, TempHead.revoked_at.is_(None))
        .values(revoked_at=now)
    ).rowcount
