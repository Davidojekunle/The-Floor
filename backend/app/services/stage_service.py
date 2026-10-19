import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import (
    Forbidden,
    InvalidTransition,
    LastStage,
    LaterStagesStarted,
    NotFound,
    TaskNotApproved,
    ValidationFailed,
)
from app.models.enums import StageStatus
from app.models.task import Stage, StageAssignee
from app.permissions.rules import RoomContext, can
from app.schemas.task import StageCreate, StageUpdate, StatusUpdate, TaskDetail
from app.services import chat_service
from app.services import notification_service as notes
from app.realtime import events as live
from app.services import stage_logic as logic
from app.services import task_common as common
from app.utils.time import as_utc, utcnow

INVALID = "Some fields are invalid."
MAX_STAGES = 30
FIRST_PARALLEL = "The first stage can't run in parallel with a previous stage."


def _finish(db: Session, ctx: RoomContext, task, stages: list[Stage], before: dict) -> TaskDetail:
    """After any change: positions, flags and locks are made consistent, then the task is returned.

    before: notes.snapshot() taken when the stages were loaded, so the right people hear about
    stages that just became ready, or that they were just assigned to."""
    logic.renumber(stages)
    logic.recompute_locks(stages)
    notes.stage_changes(db, ctx, task, stages, before)
    common.touch(task)
    live.task_changed(db, task)
    db.commit()
    return common.build_detail(db, ctx, task, stages)


def _find(stages: list[Stage], stage_id: uuid.UUID) -> int:
    for i, s in enumerate(stages):
        if s.id == stage_id:
            return i
    raise NotFound("Stage not found.")


def _load_for_edit(db: Session, ctx: RoomContext, task_id: uuid.UUID):
    """Structure edits: stage.edit, or the proposer while their proposal isn't approved yet."""
    task = common.load_task(db, ctx, task_id)
    if not common.can_edit_stages(ctx, task):
        raise Forbidden("You can't edit the stages of this task.")
    stages = common.load_stages(db, task.id)
    return task, stages, notes.snapshot(db, stages)


def _set_assignees(db: Session, stage: Stage, user_ids) -> None:
    db.execute(delete(StageAssignee).where(StageAssignee.stage_id == stage.id))
    for uid in set(user_ids):
        db.add(StageAssignee(stage_id=stage.id, user_id=uid))


# ------------------------------------------------------------------ add

def add_stage(db: Session, ctx: RoomContext, task_id: uuid.UUID, body: StageCreate) -> TaskDetail:
    task, stages, before = _load_for_edit(db, ctx, task_id)
    n = len(stages)

    errors: dict[str, str] = {}
    if n >= MAX_STAGES:
        errors["stages"] = f"A task can have at most {MAX_STAGES} stages."
    position = body.position if body.position is not None else n + 1
    if position > n + 1:
        errors["position"] = f"Position must be between 1 and {n + 1}."
    if position == 1 and body.parallel_with_previous:
        errors["parallel_with_previous"] = FIRST_PARALLEL
    if body.due_date is not None and body.due_date > as_utc(task.due_date):
        errors["due_date"] = "Stage due date can't be after the task's due date."
    common.check_stage_refs(
        errors, "", body.tag_id, body.assignee_ids,
        common.valid_tag_ids(db, ctx, {body.tag_id} if body.tag_id else set()),
        common.valid_member_ids(db, ctx, set(body.assignee_ids)),
    )
    if errors:
        raise ValidationFailed(INVALID, fields=errors)

    stage = Stage(
        task_id=task.id,
        title=body.title,
        position=position,  # required at flush time; renumbering makes the final order consistent
        parallel_with_previous=body.parallel_with_previous,
        status=StageStatus.LOCKED,
        tag_id=body.tag_id,
        due_date=body.due_date,
    )
    db.add(stage)
    db.flush()
    _set_assignees(db, stage, body.assignee_ids)
    stages.insert(position - 1, stage)
    return _finish(db, ctx, task, stages, before)


# ------------------------------------------------------------------ update (structure)

def update_stage(db: Session, ctx: RoomContext, task_id: uuid.UUID, stage_id: uuid.UUID, body: StageUpdate) -> TaskDetail:
    task, stages, before = _load_for_edit(db, ctx, task_id)
    idx = _find(stages, stage_id)
    stage = stages[idx]
    n = len(stages)
    sent = body.model_fields_set

    errors: dict[str, str] = {}
    if "title" in sent and body.title is None:
        errors["title"] = "Title can't be cleared."

    new_position = body.position if body.position is not None else idx + 1
    if new_position > n:
        errors["position"] = f"Position must be between 1 and {n}."

    # An explicit request for parallel on the first stage is a mistake (422).
    # Merely MOVING a parallel stage to the front is allowed; the flag is cleared silently.
    if body.parallel_with_previous is True and new_position == 1:
        errors["parallel_with_previous"] = FIRST_PARALLEL

    if "due_date" in sent and body.due_date is not None and body.due_date > as_utc(task.due_date):
        errors["due_date"] = "Stage due date can't be after the task's due date."

    tag_ids = {body.tag_id} if ("tag_id" in sent and body.tag_id) else set()
    assignee_ids = set(body.assignee_ids) if body.assignee_ids is not None else set()
    common.check_stage_refs(
        errors, "",
        body.tag_id if "tag_id" in sent else None,
        body.assignee_ids or [],
        common.valid_tag_ids(db, ctx, tag_ids),
        common.valid_member_ids(db, ctx, assignee_ids),
    )
    if errors:
        raise ValidationFailed(INVALID, fields=errors)

    if body.title is not None:
        stage.title = body.title
    if "tag_id" in sent:
        stage.tag_id = body.tag_id
    if "due_date" in sent:
        stage.due_date = body.due_date
    if body.parallel_with_previous is not None:
        stage.parallel_with_previous = body.parallel_with_previous
    if body.assignee_ids is not None:
        _set_assignees(db, stage, body.assignee_ids)
    if new_position != idx + 1:
        stages.pop(idx)
        stages.insert(new_position - 1, stage)
    return _finish(db, ctx, task, stages, before)


# ------------------------------------------------------------------ status

def set_status(db: Session, ctx: RoomContext, task_id: uuid.UUID, stage_id: uuid.UUID, body: StatusUpdate) -> TaskDetail:
    task = common.load_task(db, ctx, task_id)
    stages = common.load_stages(db, task.id)
    before = notes.snapshot(db, stages)
    idx = _find(stages, stage_id)
    stage = stages[idx]
    if not common.is_approved(task):
        raise TaskNotApproved("Work can't start until this task is approved.")

    participant = stage.id in common.my_stage_ids(db, ctx, stages)
    can_edit, can_override = can(ctx, "stage.edit"), can(ctx, "stage.override_lock")
    if not (participant or can_edit):
        raise Forbidden("You're not assigned to this stage.")

    new = body.status
    if new == StageStatus.BLOCKED and not (body.blocked_reason or "").strip():
        raise ValidationFailed(INVALID, fields={"blocked_reason": "A reason is required when blocking a stage."})

    if new == stage.status:
        return common.build_detail(db, ctx, task, stages)  # repeating the same status is safe

    allowed = logic.allowed_statuses(
        stages, idx, participant=participant, can_edit=can_edit, can_override=can_override
    )
    if new not in allowed:
        # say WHY, so the UI (and the person) knows whether it's permissions or state
        if stage.status == StageStatus.DONE and new == StageStatus.IN_PROGRESS:
            if not can_override:
                raise Forbidden("Only a head or temp head can reopen a stage.")
            raise LaterStagesStarted("Later stages have already started. Reopen those first.")
        if stage.status == StageStatus.LOCKED and new in (StageStatus.TODO, StageStatus.IN_PROGRESS):
            raise Forbidden("This stage is locked. Only a head or temp head can unlock it early.")
        raise InvalidTransition(f"A stage can't go from '{stage.status}' to '{new}'.")

    old = stage.status
    logic.apply_status(stage, new, body.blocked_reason, ctx.membership.user_id, utcnow())

    # room chat: one system message per milestone
    post = lambda event, **kw: chat_service.post_system(  # noqa: E731
        db, room_id=ctx.room.id, event=event, actor_id=ctx.membership.user_id, task=task, **kw
    )
    if new == StageStatus.DONE:
        post("stage_done", stage=stage)
        if logic.summarize(stages).status == "done":
            post("task_completed")
    elif new == StageStatus.BLOCKED:
        post("stage_blocked", stage=stage, detail={"reason": stage.blocked_reason})
    elif old == StageStatus.DONE and new == StageStatus.IN_PROGRESS:
        post("stage_reopened", stage=stage)
    return _finish(db, ctx, task, stages, before)


# ------------------------------------------------------------------ delete

def delete_stage(db: Session, ctx: RoomContext, task_id: uuid.UUID, stage_id: uuid.UUID) -> TaskDetail:
    task, stages, before = _load_for_edit(db, ctx, task_id)
    idx = _find(stages, stage_id)
    if len(stages) == 1:
        raise LastStage("A task needs at least one stage.")

    stage = stages.pop(idx)
    db.execute(delete(StageAssignee).where(StageAssignee.stage_id == stage.id))
    from app.services import progress_service

    progress_service.delete_for_stage(db, stage.id)
    db.delete(stage)
    return _finish(db, ctx, task, stages, before)  # renumber also clears a parallel flag that landed on the new first stage
