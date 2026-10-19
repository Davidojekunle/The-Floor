"""Room lifecycle: leave, transfer headship, delete."""
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import HeadMustTransfer, ValidationFailed
from app.models.enums import MembershipStatus, Role
from app.models.message import Message
from app.models.progress import ProgressUpdate
from app.models.room import Membership, Room, TempHead
from app.models.tag import MembershipTag, Tag
from app.models.task import Stage, StageAssignee, Task
from app.models.template import TaskTemplate, TemplateStage
from app.permissions.rules import RoomContext, require
from app.realtime import events as live
from app.models.notification import MutedRoom
from app.models.user import User
from app.services import chat_service, member_service
from app.services import notification_service as notes
from app.utils.time import utcnow

INVALID = "Some fields are invalid."


def leave_room(db: Session, ctx: RoomContext) -> list:
    """Returns the stages left with nobody on them. The head is notified about them."""
    m = ctx.membership
    if m.role == Role.HEAD:
        raise HeadMustTransfer("Hand headship to someone else before leaving the room.")

    theirs = member_service.stages_of(db, ctx.room.id, m)
    m.status = MembershipStatus.LEFT
    member_service.release_membership(db, ctx.room.id, m)
    chat_service.post_system(db, room_id=ctx.room.id, event="member_left", actor_id=m.user_id)
    orphaned = member_service.unstaffed(db, ctx.room.id, theirs)
    notes.stages_unassigned(db, ctx, db.get(User, m.user_id), orphaned)
    live.to_user(db, "room_access_lost", ctx.room.id, m.user_id, reason="left")  # their other tabs
    live.room_changed(db, ctx.room.id)
    db.commit()
    return orphaned


def transfer_head(db: Session, ctx: RoomContext, membership_id: uuid.UUID) -> None:
    require(ctx, "head.transfer")
    target = db.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.room_id == ctx.room.id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )
    if target is None or target.id == ctx.membership.id:
        raise ValidationFailed(INVALID, fields={"membership_id": "Pick another active member of this room."})

    ctx.membership.role = Role.MEMBER
    target.role = Role.HEAD
    # the new head already has everything, so any temp head grant simply ends
    db.execute(
        TempHead.__table__.update()
        .where(TempHead.room_id == ctx.room.id, TempHead.user_id == target.user_id, TempHead.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    chat_service.post_system(
        db, room_id=ctx.room.id, event="head_transferred", actor_id=ctx.membership.user_id, subject_id=target.user_id
    )
    notes.head_transferred(db, ctx, target.user_id)
    live.room_changed(db, ctx.room.id)
    db.commit()


def delete_room(db: Session, ctx: RoomContext, confirm_name: str) -> None:
    require(ctx, "room.delete")
    if " ".join(confirm_name.split()).casefold() != " ".join(ctx.room.name.split()).casefold():
        raise ValidationFailed(INVALID, fields={"confirm_name": "Type the room's name exactly to confirm."})

    room_id = ctx.room.id
    members = live.room_members(db, room_id)
    for user_id in members:  # everyone loses it, including the head's other tabs
        live.to_user(db, "room_access_lost", room_id, user_id, reason="room_deleted")
    notes.room_deleted(db, ctx, members)  # before the mutes are deleted: a muted room stays silent
    db.flush()

    # explicit order, so it doesn't depend on database cascade settings
    task_ids = select(Task.id).where(Task.room_id == room_id)
    stage_ids = select(Stage.id).where(Stage.task_id.in_(task_ids))
    membership_ids = select(Membership.id).where(Membership.room_id == room_id)
    template_ids = select(TaskTemplate.id).where(TaskTemplate.room_id == room_id)
    for statement in (
        delete(ProgressUpdate).where(ProgressUpdate.task_id.in_(task_ids)),
        delete(StageAssignee).where(StageAssignee.stage_id.in_(stage_ids)),
        delete(MembershipTag).where(MembershipTag.membership_id.in_(membership_ids)),
        delete(TempHead).where(TempHead.room_id == room_id),
        delete(MutedRoom).where(MutedRoom.room_id == room_id),
        delete(Membership).where(Membership.room_id == room_id),  # before messages: read positions point at them
        delete(Message).where(Message.room_id == room_id),
        delete(Stage).where(Stage.task_id.in_(task_ids)),
        delete(Task).where(Task.room_id == room_id),
        delete(TemplateStage).where(TemplateStage.template_id.in_(template_ids)),
        delete(TaskTemplate).where(TaskTemplate.room_id == room_id),
        delete(Tag).where(Tag.room_id == room_id),
        delete(Room).where(Room.id == room_id),
    ):
        db.execute(statement)
    db.commit()
