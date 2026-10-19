import uuid

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound
from app.permissions.rules import RoomContext, require
from app.schemas.common import PageParams
from app.schemas.member import TagOut
from app.models.tag import MembershipTag, Tag
from app.models.task import Stage
from app.models.template import TemplateStage


def _get_tag(db: Session, ctx: RoomContext, tag_id: uuid.UUID) -> Tag:
    # scoped to THIS room: a tag id from another room is just "not found"
    tag = db.scalar(select(Tag).where(Tag.id == tag_id, Tag.room_id == ctx.room.id))
    if tag is None:
        raise NotFound("Tag not found.")
    return tag


def _name_taken(db: Session, room_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None) -> bool:
    q = select(Tag.id).where(Tag.room_id == room_id, func.lower(Tag.name) == name.lower())
    if exclude_id is not None:
        q = q.where(Tag.id != exclude_id)
    return db.scalar(q) is not None


def _taken_error(name: str) -> Conflict:
    return Conflict(f"A tag named '{name}' already exists in this room.")


def _count(db: Session, tag_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(MembershipTag).where(MembershipTag.tag_id == tag_id))


def list_tags(db: Session, ctx: RoomContext, params: PageParams) -> tuple[list[TagOut], int]:
    total = db.scalar(select(func.count()).select_from(Tag).where(Tag.room_id == ctx.room.id))
    rows = db.execute(
        select(Tag, func.count(MembershipTag.membership_id))
        .outerjoin(MembershipTag, MembershipTag.tag_id == Tag.id)
        .where(Tag.room_id == ctx.room.id)
        .group_by(Tag.id)
        .order_by(func.lower(Tag.name), Tag.id)
        .offset(params.offset)
        .limit(params.limit)
    ).all()
    return [TagOut(id=t.id, name=t.name, member_count=n) for t, n in rows], total


def create_tag(db: Session, ctx: RoomContext, name: str) -> TagOut:
    require(ctx, "tag.manage")
    if _name_taken(db, ctx.room.id, name):
        raise _taken_error(name)
    tag = Tag(room_id=ctx.room.id, name=name)
    db.add(tag)
    try:
        db.commit()
    except IntegrityError:  # two simultaneous creates
        db.rollback()
        raise _taken_error(name)
    return TagOut(id=tag.id, name=tag.name, member_count=0)


def rename_tag(db: Session, ctx: RoomContext, tag_id: uuid.UUID, name: str) -> TagOut:
    require(ctx, "tag.manage")
    tag = _get_tag(db, ctx, tag_id)
    if _name_taken(db, ctx.room.id, name, exclude_id=tag.id):
        raise _taken_error(name)
    tag.name = name
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise _taken_error(name)
    return TagOut(id=tag.id, name=tag.name, member_count=_count(db, tag.id))


def delete_tag(db: Session, ctx: RoomContext, tag_id: uuid.UUID) -> None:
    require(ctx, "tag.manage")
    tag = _get_tag(db, ctx, tag_id)
    # explicit, so it doesn't depend on the database's cascade settings
    db.execute(delete(MembershipTag).where(MembershipTag.tag_id == tag.id))
    db.delete(tag)
    # stages that used this tag simply become tag-less (nothing is deleted)
    db.execute(update(Stage).where(Stage.tag_id == tag.id).values(tag_id=None))
    db.execute(update(TemplateStage).where(TemplateStage.tag_id == tag.id).values(tag_id=None))
    db.commit()
