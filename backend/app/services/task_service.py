import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import AlreadyApproved, Forbidden, NotFound, ValidationFailed
from app.models.enums import ApprovalStatus, MembershipStatus, StageStatus
from app.models.room import Membership
from app.models.tag import MembershipTag, Tag
from app.models.task import Stage, StageAssignee, Task
from app.permissions.rules import RoomContext, can, require
from app.schemas.common import PageParams
from app.schemas.task import TaskCreate, TaskDetail, TaskListItem, TaskUpdate
from app.services import chat_service
from app.services import notification_service as notes
from app.realtime import events as live
from app.services import stage_logic as logic
from app.services import task_common as common
from app.utils.time import as_utc, utcnow

INVALID = "Some fields are invalid."


# ------------------------------------------------------------------ create

def create_task(db: Session, ctx: RoomContext, body: TaskCreate) -> TaskDetail:
    # task.create -> approved at once. Only task.propose -> a pending proposal. Same form, same rules.
    if can(ctx, "task.create"):
        approval = ApprovalStatus.APPROVED
    else:
        require(ctx, "task.propose")
        approval = ApprovalStatus.PENDING

    errors: dict[str, str] = {}
    if body.start_date is not None and body.start_date > body.due_date:
        errors["start_date"] = "Start date can't be after the due date."

    ok_tags = common.valid_tag_ids(db, ctx, {s.tag_id for s in body.stages if s.tag_id})
    ok_members = common.valid_member_ids(db, ctx, {uid for s in body.stages for uid in s.assignee_ids})

    for i, s in enumerate(body.stages):
        prefix = f"stages.{i}."
        if i == 0 and s.parallel_with_previous:
            errors[f"{prefix}parallel_with_previous"] = "The first stage can't run in parallel with a previous stage."
        if s.due_date is not None and s.due_date > body.due_date:
            errors[f"{prefix}due_date"] = "Stage due date can't be after the task's due date."
        common.check_stage_refs(errors, prefix, s.tag_id, s.assignee_ids, ok_tags, ok_members)
    if errors:
        raise ValidationFailed(INVALID, fields=errors)

    now = utcnow()
    task = Task(
        room_id=ctx.room.id,
        title=body.title,
        description=(body.description or "").strip() or None,
        start_date=body.start_date,
        due_date=body.due_date,
        approval_status=approval,
        created_by=ctx.membership.user_id,
        approved_by=ctx.membership.user_id if approval == ApprovalStatus.APPROVED else None,
        created_at=now,
        updated_at=now,
        submitted_at=now,
    )
    db.add(task)
    db.flush()

    stages = []
    for i, s in enumerate(body.stages):
        stage = Stage(
            task_id=task.id,
            title=s.title,
            position=i + 1,
            parallel_with_previous=s.parallel_with_previous if i > 0 else False,
            status=StageStatus.LOCKED,
            tag_id=s.tag_id,
            due_date=s.due_date,
        )
        db.add(stage)
        stages.append(stage)
    db.flush()

    for stage, s in zip(stages, body.stages):
        for uid in set(s.assignee_ids):
            db.add(StageAssignee(stage_id=stage.id, user_id=uid))

    logic.recompute_locks(stages)
    live.task_changed(db, task)
    if approval == ApprovalStatus.APPROVED:  # proposals stay private: nothing posts until approval
        chat_service.post_system(db, room_id=ctx.room.id, event="task_created", actor_id=ctx.membership.user_id, task=task)
        notes.stage_changes(db, ctx, task, stages, before={})
    else:
        notes.proposal_submitted(db, ctx, task)
    db.commit()
    return common.build_detail(db, ctx, task, stages)


# ------------------------------------------------------------------ read

def get_task(db: Session, ctx: RoomContext, task_id: uuid.UUID) -> TaskDetail:
    task = common.load_task(db, ctx, task_id)
    return common.build_detail(db, ctx, task, common.load_stages(db, task.id))


def list_tasks(
    db: Session,
    ctx: RoomContext,
    params: PageParams,
    *,
    from_: datetime | None,
    to: datetime | None,
    status: str | None,
    assignee: str | None,
    tag: uuid.UUID | None,
    overdue: bool | None,
    blocked: bool | None = None,
    approval_status: str | None = None,
    sort: str | None = None,
) -> tuple[list[TaskListItem], int]:
    now = utcnow()
    agg = common.stage_counts()
    statuses = common.parse_approval_statuses(approval_status)
    conds = [Task.room_id == ctx.room.id, Task.approval_status.in_(statuses)]
    if not can(ctx, "task.approve"):
        # members only ever see approved tasks plus their OWN proposals
        conds.append(or_(Task.approval_status == ApprovalStatus.APPROVED, Task.created_by == ctx.membership.user_id))
    conds += common.task_filters(agg, from_=from_, to=to, status=status, overdue=overdue, blocked=blocked, now=now)

    if tag is not None:
        if db.scalar(select(Tag.id).where(Tag.id == tag, Tag.room_id == ctx.room.id)) is None:
            raise NotFound("Tag not found.")
        conds.append(select(Stage.id).where(Stage.task_id == Task.id, Stage.tag_id == tag).exists())

    if assignee is not None:
        if assignee == "me":
            target_user = ctx.membership.user_id
        else:
            try:
                target_user = uuid.UUID(assignee)
            except ValueError:
                raise ValidationFailed(INVALID, fields={"assignee": "Use a user id or 'me'."})
        target_membership = db.scalar(
            select(Membership.id).where(
                Membership.room_id == ctx.room.id,
                Membership.user_id == target_user,
                Membership.status == MembershipStatus.ACTIVE,
            )
        )
        if target_membership is None:
            return [], 0
        conds.append(_participates(Stage.task_id == Task.id, target_user, target_membership))

    base = select(Task).join(agg, agg.c.task_id == Task.id).where(*conds)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    tasks = list(
        db.scalars(base.order_by(*common.task_order(sort)).offset(params.offset).limit(params.limit))
    )
    if not tasks:
        return [], total
    people = common.creators(db, tasks)

    task_ids = [t.id for t in tasks]
    stages_by_task: dict[uuid.UUID, list[Stage]] = {tid: [] for tid in task_ids}
    for stage in db.scalars(
        select(Stage).where(Stage.task_id.in_(task_ids)).order_by(Stage.task_id, Stage.position, Stage.id)
    ):
        stages_by_task[stage.task_id].append(stage)

    involved = set(
        db.scalars(
            select(Stage.task_id)
            .where(Stage.task_id.in_(task_ids), _participation_clause(ctx.membership.user_id, ctx.membership.id))
            .distinct()
        )
    )
    items = [common.build_list_item(t, stages_by_task[t.id], t.id in involved, now, people[t.created_by]) for t in tasks]
    return items, total


def _participation_clause(user_id: uuid.UUID, membership_id: uuid.UUID):
    """A stage involves a person if they're an assignee OR hold the stage's tag."""
    return or_(
        Stage.id.in_(select(StageAssignee.stage_id).where(StageAssignee.user_id == user_id)),
        Stage.tag_id.in_(select(MembershipTag.tag_id).where(MembershipTag.membership_id == membership_id)),
    )


def _participates(task_match, user_id: uuid.UUID, membership_id: uuid.UUID):
    return select(Stage.id).where(task_match, _participation_clause(user_id, membership_id)).exists()


# ------------------------------------------------------------------ update / delete

def update_task(db: Session, ctx: RoomContext, task_id: uuid.UUID, body: TaskUpdate) -> TaskDetail:
    task = common.load_task(db, ctx, task_id)
    if not common.can_edit_task(ctx, task):
        raise Forbidden("You can't edit this task.")
    stages = common.load_stages(db, task.id, lock=True)
    sent = body.model_fields_set

    errors: dict[str, str] = {}
    if "title" in sent and body.title is None:
        errors["title"] = "Title can't be cleared."
    if "due_date" in sent and body.due_date is None:
        errors["due_date"] = "Due date can't be cleared."

    new_due = body.due_date if ("due_date" in sent and body.due_date is not None) else as_utc(task.due_date)
    new_start = body.start_date if "start_date" in sent else as_utc(task.start_date)

    if new_start is not None and new_start > new_due:
        errors["start_date"] = "Start date can't be after the due date."
    if "due_date" not in errors and any(s.due_date and as_utc(s.due_date) > new_due for s in stages):
        errors["due_date"] = "Due date can't be earlier than a stage's due date."
    if errors:
        raise ValidationFailed(INVALID, fields=errors)

    if "title" in sent:
        task.title = body.title
    if "description" in sent:
        task.description = (body.description or "").strip() or None
    if "start_date" in sent:
        task.start_date = body.start_date
    if "due_date" in sent:
        task.due_date = new_due
    common.touch(task)
    live.task_changed(db, task)
    db.commit()
    return common.build_detail(db, ctx, task, stages)


def delete_task(db: Session, ctx: RoomContext, task_id: uuid.UUID) -> None:
    task = common.load_task(db, ctx, task_id)
    if not common.can_delete_task(ctx, task):
        raise Forbidden("You can't delete this task.")
    from app.services import progress_service

    live.task_deleted(db, task)
    progress_service.delete_for_task(db, task.id)
    stage_ids = select(Stage.id).where(Stage.task_id == task.id)
    db.execute(StageAssignee.__table__.delete().where(StageAssignee.stage_id.in_(stage_ids)))
    db.execute(Stage.__table__.delete().where(Stage.task_id == task.id))
    db.delete(task)
    db.commit()


# ------------------------------------------------------------------ proposals: approve / reject / resubmit

def approve_task(db: Session, ctx: RoomContext, task_id: uuid.UUID) -> TaskDetail:
    require(ctx, "task.approve")
    task = common.load_task(db, ctx, task_id)
    if not common.is_approved(task):  # approving twice is a safe no-op
        now = utcnow()
        task.approval_status = ApprovalStatus.APPROVED
        task.approved_by = task.decided_by = ctx.membership.user_id
        task.decided_at = now
        task.rejection_reason = None
        common.touch(task)
        live.task_changed(db, task)
        chat_service.post_system(
            db, room_id=ctx.room.id, event="task_approved",
            actor_id=ctx.membership.user_id, subject_id=task.created_by, task=task,
        )
        notes.proposal_decided(db, ctx, task, approved=True)
        notes.stage_changes(db, ctx, task, common.load_stages(db, task.id), before={})  # work can start now
        db.commit()
    return common.build_detail(db, ctx, task, common.load_stages(db, task.id))


def reject_task(db: Session, ctx: RoomContext, task_id: uuid.UUID, reason: str | None) -> TaskDetail:
    require(ctx, "task.approve")
    task = common.load_task(db, ctx, task_id)
    if common.is_approved(task):
        raise AlreadyApproved("This task is already approved. Delete it instead of rejecting it.")
    if task.approval_status == ApprovalStatus.PENDING:  # rejecting twice is a safe no-op
        task.approval_status = ApprovalStatus.REJECTED
        task.decided_by = ctx.membership.user_id
        task.decided_at = utcnow()
        task.rejection_reason = (reason or "").strip() or None
        common.touch(task)
        live.task_changed(db, task)
        notes.proposal_decided(db, ctx, task, approved=False)
        db.commit()
    return common.build_detail(db, ctx, task, common.load_stages(db, task.id))


def resubmit_task(db: Session, ctx: RoomContext, task_id: uuid.UUID) -> TaskDetail:
    task = common.load_task(db, ctx, task_id)
    if not common.is_proposer(ctx, task):
        raise Forbidden("Only the person who proposed this task can resubmit it.")
    if common.is_approved(task):
        raise AlreadyApproved("This task is already approved.")
    if task.approval_status == ApprovalStatus.REJECTED:  # resubmitting a pending one is a safe no-op
        task.approval_status = ApprovalStatus.PENDING
        task.submitted_at = utcnow()  # back in the queue as new
        task.rejection_reason = None
        common.touch(task)
        live.task_changed(db, task)
        notes.proposal_submitted(db, ctx, task)
        db.commit()
    return common.build_detail(db, ctx, task, common.load_stages(db, task.id))
