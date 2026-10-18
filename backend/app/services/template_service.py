import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.models.tag import Tag
from app.models.template import TaskTemplate, TemplateStage
from app.permissions.rules import RoomContext, require
from app.schemas.common import PageParams
from app.schemas.member import TagBrief
from app.schemas.task import StageIn, TaskCreate, TaskDetail
from app.schemas.template import TemplateApply, TemplateCreate, TemplateOut, TemplateStageIn, TemplateStageOut, TemplateUpdate
from app.services import task_common as common
from app.services import task_service
from app.utils.time import utcnow

INVALID = "Some fields are invalid."


# ------------------------------------------------------------------ helpers

def _get(db: Session, ctx: RoomContext, template_id: uuid.UUID) -> TaskTemplate:
    # scoped to THIS room: a template id from another room is just "not found"
    t = db.scalar(select(TaskTemplate).where(TaskTemplate.id == template_id, TaskTemplate.room_id == ctx.room.id))
    if t is None:
        raise NotFound("Template not found.")
    return t


def _name_taken(db: Session, room_id, name: str, exclude_id=None) -> bool:
    q = select(TaskTemplate.id).where(TaskTemplate.room_id == room_id, func.lower(TaskTemplate.name) == name.lower())
    if exclude_id is not None:
        q = q.where(TaskTemplate.id != exclude_id)
    return db.scalar(q) is not None


def _taken(name: str) -> Conflict:
    message = f"A template named '{name}' already exists in this room."
    return Conflict(message, fields={"name": message})


def _check_stages(db: Session, ctx: RoomContext, stages: list[TemplateStageIn], errors: dict) -> None:
    ok_tags = common.valid_tag_ids(db, ctx, {s.tag_id for s in stages if s.tag_id})
    for i, s in enumerate(stages):
        if i == 0 and s.parallel_with_previous:
            errors[f"stages.{i}.parallel_with_previous"] = "The first stage can't run in parallel with a previous stage."
        if s.tag_id is not None and s.tag_id not in ok_tags:
            errors[f"stages.{i}.tag_id"] = "This tag doesn't exist in this room."


def _replace_stages(db: Session, template: TaskTemplate, stages: list[TemplateStageIn]) -> None:
    db.execute(delete(TemplateStage).where(TemplateStage.template_id == template.id))
    for i, s in enumerate(stages, start=1):
        db.add(
            TemplateStage(
                template_id=template.id,
                position=i,
                title=s.title,
                tag_id=s.tag_id,
                parallel_with_previous=s.parallel_with_previous if i > 1 else False,
            )
        )


def _outs(db: Session, templates: list[TaskTemplate]) -> list[TemplateOut]:
    if not templates:
        return []
    ids = [t.id for t in templates]
    stages = list(
        db.scalars(
            select(TemplateStage)
            .where(TemplateStage.template_id.in_(ids))
            .order_by(TemplateStage.template_id, TemplateStage.position)
        )
    )
    tag_ids = {s.tag_id for s in stages if s.tag_id}
    tags = {t.id: t for t in db.scalars(select(Tag).where(Tag.id.in_(tag_ids)))} if tag_ids else {}
    by_template: dict[uuid.UUID, list[TemplateStageOut]] = {tid: [] for tid in ids}
    for s in stages:
        tag = tags.get(s.tag_id)
        by_template[s.template_id].append(
            TemplateStageOut(
                position=s.position,
                title=s.title,
                tag=TagBrief(id=tag.id, name=tag.name) if tag else None,
                parallel_with_previous=s.parallel_with_previous,
            )
        )
    return [TemplateOut(id=t.id, name=t.name, stages=by_template[t.id]) for t in templates]


def _commit_or_taken(db: Session, name: str) -> None:
    try:
        db.commit()
    except IntegrityError:  # two simultaneous saves with the same name
        db.rollback()
        raise _taken(name)


# ------------------------------------------------------------------ CRUD

def list_templates(db: Session, ctx: RoomContext, params: PageParams) -> tuple[list[TemplateOut], int]:
    where = TaskTemplate.room_id == ctx.room.id
    total = db.scalar(select(func.count()).select_from(TaskTemplate).where(where))
    templates = list(
        db.scalars(
            select(TaskTemplate)
            .where(where)
            .order_by(func.lower(TaskTemplate.name), TaskTemplate.id)
            .offset(params.offset)
            .limit(params.limit)
        )
    )
    return _outs(db, templates), total


def get_template(db: Session, ctx: RoomContext, template_id: uuid.UUID) -> TemplateOut:
    return _outs(db, [_get(db, ctx, template_id)])[0]


def create_template(db: Session, ctx: RoomContext, body: TemplateCreate) -> TemplateOut:
    require(ctx, "task.create")
    errors: dict[str, str] = {}
    _check_stages(db, ctx, body.stages, errors)
    if errors:
        raise ValidationFailed(INVALID, fields=errors)
    if _name_taken(db, ctx.room.id, body.name):
        raise _taken(body.name)

    now = utcnow()
    template = TaskTemplate(
        room_id=ctx.room.id, name=body.name, created_by=ctx.membership.user_id, created_at=now, updated_at=now
    )
    db.add(template)
    db.flush()
    _replace_stages(db, template, body.stages)
    _commit_or_taken(db, body.name)
    return _outs(db, [template])[0]


def update_template(db: Session, ctx: RoomContext, template_id: uuid.UUID, body: TemplateUpdate) -> TemplateOut:
    require(ctx, "task.create")
    template = _get(db, ctx, template_id)
    sent = body.model_fields_set

    errors: dict[str, str] = {}
    if "name" in sent and body.name is None:
        errors["name"] = "Name can't be cleared."
    if "stages" in sent and body.stages is None:
        errors["stages"] = "A template needs at least one stage."
    if body.stages is not None:
        _check_stages(db, ctx, body.stages, errors)
    if errors:
        raise ValidationFailed(INVALID, fields=errors)

    if body.name is not None:
        if _name_taken(db, ctx.room.id, body.name, exclude_id=template.id):
            raise _taken(body.name)
        template.name = body.name
    if body.stages is not None:
        _replace_stages(db, template, body.stages)
    template.updated_at = utcnow()
    _commit_or_taken(db, template.name)
    return _outs(db, [template])[0]


def delete_template(db: Session, ctx: RoomContext, template_id: uuid.UUID) -> None:
    require(ctx, "task.create")
    template = _get(db, ctx, template_id)
    db.execute(delete(TemplateStage).where(TemplateStage.template_id == template.id))
    db.delete(template)
    db.commit()


# ------------------------------------------------------------------ apply

def apply_template(db: Session, ctx: RoomContext, template_id: uuid.UUID, body: TemplateApply) -> TaskDetail:
    """Copies the template's stages into a brand-new task. Later template edits never touch that task."""
    require(ctx, "task.create")
    template = _get(db, ctx, template_id)
    stages = list(
        db.scalars(select(TemplateStage).where(TemplateStage.template_id == template.id).order_by(TemplateStage.position))
    )
    task_body = TaskCreate(
        title=body.title,
        description=body.description,
        start_date=body.start_date,
        due_date=body.due_date,
        stages=[StageIn(title=s.title, tag_id=s.tag_id, parallel_with_previous=s.parallel_with_previous) for s in stages],
    )
    # the normal create path: same validation, same rules, same response
    return task_service.create_task(db, ctx, task_body)
