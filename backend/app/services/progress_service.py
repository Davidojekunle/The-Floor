"""Progress updates: short notes on stages, plus a task-wide feed."""
import uuid

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session

from app.core.errors import Forbidden, NotFound, TaskNotApproved, ValidationFailed
from app.models.message import Message, MessageType
from app.models.progress import ProgressUpdate
from app.models.task import Stage
from app.models.user import User
from app.permissions.rules import RoomContext, can
from app.schemas.message import Ref
from app.schemas.progress import UpdateCreate, UpdateOut, UpdatePage
from app.schemas.room import UserBrief
from app.services import chat_service
from app.realtime import events as live
from app.services import task_common as common
from app.utils.time import as_utc, utcnow


def _stage(db: Session, task, stage_id: uuid.UUID) -> Stage:
    stage = db.scalar(select(Stage).where(Stage.id == stage_id, Stage.task_id == task.id))
    if stage is None:
        raise NotFound("Stage not found.")
    return stage


def _build(db: Session, ctx: RoomContext, updates: list[ProgressUpdate]) -> list[UpdateOut]:
    if not updates:
        return []
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({u.author_id for u in updates})))}
    stages = {s.id: s for s in db.scalars(select(Stage).where(Stage.id.in_({u.stage_id for u in updates})))}
    moderator = can(ctx, "stage.edit")
    me = ctx.membership.user_id
    return [
        UpdateOut(
            id=u.id,
            stage=Ref(id=u.stage_id, title=stages[u.stage_id].title),
            author=UserBrief(id=u.author_id, name=users[u.author_id].name),
            note=u.note,
            link_url=u.link_url,
            created_at=as_utc(u.created_at),
            can_delete=moderator or u.author_id == me,
        )
        for u in updates
    ]


def _page(db: Session, ctx: RoomContext, scope, before: uuid.UUID | None, limit: int) -> UpdatePage:
    q = select(ProgressUpdate).where(scope)
    if before is not None:
        cursor = db.scalar(select(ProgressUpdate).where(ProgressUpdate.id == before, scope))
        if cursor is None:
            raise ValidationFailed("Some fields are invalid.", fields={"before": "Unknown update here."})
        q = q.where(
            or_(
                ProgressUpdate.created_at < cursor.created_at,
                and_(ProgressUpdate.created_at == cursor.created_at, ProgressUpdate.id < cursor.id),
            )
        )
    rows = list(db.scalars(q.order_by(ProgressUpdate.created_at.desc(), ProgressUpdate.id.desc()).limit(limit + 1)))
    return UpdatePage(items=_build(db, ctx, rows[:limit]), has_more=len(rows) > limit)


def list_stage_updates(db, ctx, task_id, stage_id, before, limit) -> UpdatePage:
    task = common.load_task(db, ctx, task_id)
    stage = _stage(db, task, stage_id)
    return _page(db, ctx, ProgressUpdate.stage_id == stage.id, before, limit)


def list_task_updates(db, ctx, task_id, before, limit) -> UpdatePage:
    task = common.load_task(db, ctx, task_id)
    return _page(db, ctx, ProgressUpdate.task_id == task.id, before, limit)


def post_update(db: Session, ctx: RoomContext, task_id: uuid.UUID, stage_id: uuid.UUID, body: UpdateCreate) -> UpdateOut:
    task = common.load_task(db, ctx, task_id)
    stages = common.load_stages(db, task.id)
    stage = _stage(db, task, stage_id)
    if not common.is_approved(task):
        raise TaskNotApproved("Updates can be posted once this task is approved.")
    if not (stage.id in common.my_stage_ids(db, ctx, stages) or can(ctx, "stage.edit")):
        raise Forbidden("You're not part of this stage.")

    update = ProgressUpdate(
        task_id=task.id, stage_id=stage.id, author_id=ctx.membership.user_id,
        note=body.note, link_url=body.link_url, created_at=utcnow(),
    )
    db.add(update)
    live.task_updates_changed(db, task, stage.id)
    if body.share_to_chat:
        shared = Message(
                room_id=ctx.room.id,
                type=MessageType.USER,
                sender_id=ctx.membership.user_id,
                body=body.note if not body.link_url else f"{body.note}\n{body.link_url}",
                task_id=task.id,
                stage_id=stage.id,
                created_at=chat_service._now(db),
            )
        db.add(shared)
        db.flush()
        live.message_created(db, ctx.room.id, shared.id)
    db.commit()
    return _build(db, ctx, [update])[0]


def delete_update(db: Session, ctx: RoomContext, task_id: uuid.UUID, stage_id: uuid.UUID, update_id: uuid.UUID) -> None:
    task = common.load_task(db, ctx, task_id)
    stage = _stage(db, task, stage_id)
    update = db.scalar(select(ProgressUpdate).where(ProgressUpdate.id == update_id, ProgressUpdate.stage_id == stage.id))
    if update is None:
        return  # already gone: safe to repeat
    if not (update.author_id == ctx.membership.user_id or can(ctx, "stage.edit")):
        raise Forbidden("You can only delete your own updates.")
    live.task_updates_changed(db, task, stage.id)
    db.delete(update)
    db.commit()


def delete_for_stage(db: Session, stage_id) -> None:
    db.execute(delete(ProgressUpdate).where(ProgressUpdate.stage_id == stage_id))


def delete_for_task(db: Session, task_id) -> None:
    db.execute(delete(ProgressUpdate).where(ProgressUpdate.task_id == task_id))
