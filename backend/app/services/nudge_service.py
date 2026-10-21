"""Nudges: a head (or temp head) privately asks the people on a late or stuck stage for an update.

Rules: only on an approved task's stage that is overdue, or has sat in To do / In progress for 3+ days
("update"), or is blocked ("block": asking about the block, never "hurry up"). Once per stage per 24h.
Never posted in chat. The nudge stays open until someone on the stage answers (starts it, finishes it,
blocks it, posts an update or says "I'm on it"), and the person who nudged is told.
"""
import uuid
from datetime import timedelta

from app.core.errors import AlreadyNudged, Forbidden, NobodyOnStage, NotNudgeable, TaskNotApproved
from app.models.enums import StageStatus
from app.models.task import Stage, Task
from app.models.user import User
from app.permissions.rules import RoomContext, can
from app.schemas.task import TaskDetail
from app.services import notification_service as notes
from app.services import task_common as common
from app.utils.time import as_utc, utcnow

STUCK_AFTER = timedelta(days=3)
ONCE_EVERY = timedelta(hours=24)


def effective_due(stage: Stage, task: Task):
    return as_utc(stage.due_date or task.due_date)


def kind_for(stage: Stage, task: Task, now) -> str | None:
    """What a nudge on this stage would be right now, or None when it isn't late or stuck."""
    if stage.status == StageStatus.BLOCKED:
        return "block"
    if stage.status in (StageStatus.TODO, StageStatus.IN_PROGRESS):
        if effective_due(stage, task) < now or now - as_utc(stage.status_since) >= STUCK_AFTER:
            return "update"
    return None


def nudged_recently(stage: Stage, now) -> bool:
    return stage.last_nudged_at is not None and now - as_utc(stage.last_nudged_at) < ONCE_EVERY


def can_nudge(ctx: RoomContext, task: Task, stage: Stage, now) -> bool:
    return (common.is_approved(task) and can(ctx, "stage.edit") and kind_for(stage, task, now) is not None
            and not nudged_recently(stage, now))


def nudge(db, ctx: RoomContext, task_id: uuid.UUID, stage_id: uuid.UUID, note: str | None) -> TaskDetail:
    task = common.load_task(db, ctx, task_id)
    stages = common.load_stages(db, task.id, lock=True)
    stage = next((s for s in stages if s.id == stage_id), None)
    if stage is None:
        from app.core.errors import NotFound
        raise NotFound("Stage not found.")
    if not common.is_approved(task):
        raise TaskNotApproved("Nobody works on this task until it's approved.")
    if not can(ctx, "stage.edit"):
        raise Forbidden("Only a head or temp head can nudge.")
    now = utcnow()
    kind = kind_for(stage, task, now)
    if kind is None:
        raise NotNudgeable("This stage isn't late or stuck. You can nudge once it's overdue or has waited 3 days.")
    if nudged_recently(stage, now):
        raise AlreadyNudged("This stage was nudged in the last day. You can nudge it again tomorrow.")

    me = ctx.membership.user_id
    people = notes._participants(db, ctx.room.id, [stage])[stage.id] - {me}
    if not people:
        raise NobodyOnStage("Nobody is on this stage yet. Assign someone first.")

    note = (note or "").strip() or None
    stage.last_nudged_at, stage.last_nudged_by = now, me
    stage.nudge_kind, stage.nudge_note, stage.nudge_open = kind, note, True
    actor = db.get(User, me)
    title = (f"{actor.name} asked about the block on “{stage.title}” on “{task.title}”" if kind == "block"
             else f"{actor.name} asked for an update on “{stage.title}” on “{task.title}”")
    for uid in people:
        notes.notify(db, uid, "nudged", title, room=ctx.room, task=task, stage=stage, actor=actor,
                     data={"kind": kind, "note": note})
    common.touch(task)
    from app.realtime import events as live
    live.task_changed(db, task)
    db.commit()
    return common.build_detail(db, ctx, task, stages)


_ANSWER = {
    "on_it": "{name} is on it: “{stage}” on “{task}”",
    "update": "{name} posted an update on “{stage}” on “{task}”",
    StageStatus.IN_PROGRESS: "{name} started “{stage}” on “{task}”",
    StageStatus.DONE: "{name} finished “{stage}” on “{task}”",
    StageStatus.BLOCKED: "{name} marked “{stage}” on “{task}” as blocked",
}


def answered(db, ctx: RoomContext, task: Task, stage: Stage, how: str) -> None:
    """Someone on the stage responded to an open nudge: close it and tell whoever nudged.
    Called by status changes and progress updates; a no-op when there's no open nudge."""
    if not stage.nudge_open or how not in _ANSWER:
        return
    me = ctx.membership.user_id
    stage.nudge_open = False
    if stage.last_nudged_by is None or stage.last_nudged_by == me:
        return
    actor = db.get(User, me)
    notes.notify(db, stage.last_nudged_by, "nudge_answered",
                 _ANSWER[how].format(name=actor.name, stage=stage.title, task=task.title),
                 room=ctx.room, task=task, stage=stage, actor=actor)


def acknowledge(db, ctx: RoomContext, task_id: uuid.UUID, stage_id: uuid.UUID) -> TaskDetail:
    """“I'm on it”: a stage still To do starts; one already in progress just answers the nudge."""
    from app.schemas.task import StatusUpdate
    from app.services import stage_service

    task = common.load_task(db, ctx, task_id)
    stages = common.load_stages(db, task.id, lock=True)
    stage = next((s for s in stages if s.id == stage_id), None)
    if stage is None:
        from app.core.errors import NotFound
        raise NotFound("Stage not found.")
    if stage.id not in common.my_stage_ids(db, ctx, stages):
        raise Forbidden("You're not on this stage.")
    if stage.status == StageStatus.TODO:
        return stage_service.set_status(db, ctx, task_id, stage_id, StatusUpdate(status="in_progress"))
    answered(db, ctx, task, stage, "on_it")
    db.commit()
    return common.build_detail(db, ctx, task, stages)
