"""Shared helpers for task and stage services: loading, validation of references, and building responses."""
import uuid

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound, ValidationFailed
from app.models.enums import ApprovalStatus, StageStatus, TaskStatus
from app.models.room import Membership
from app.models.enums import MembershipStatus
from app.models.tag import MembershipTag, Tag
from app.models.task import Stage, StageAssignee, Task
from app.models.user import User
from app.permissions.rules import RoomContext, can
from app.schemas.member import TagBrief
from app.schemas.room import UserBrief
from app.schemas.task import NudgeOut, ResultOut, StageOut, TaskDetail, TaskListItem
from app.services import stage_logic as logic
from app.utils.time import as_utc, utcnow


# ------------------------------------------------------------------ loading

def load_task(db: Session, ctx: RoomContext, task_id: uuid.UUID) -> Task:
    """Scoped to THIS room, and to what the caller may see.

    A task from another room, or someone else's pending/rejected proposal, is just 'not found'.
    """
    task = db.scalar(select(Task).where(Task.id == task_id, Task.room_id == ctx.room.id))
    if task is None or not can_see(ctx, task):
        raise NotFound("Task not found.")
    return task


# ------------------------------------------------------------------ proposal rules (phase 4)

def is_proposer(ctx: RoomContext, task: Task) -> bool:
    return task.created_by == ctx.membership.user_id


def is_approved(task: Task) -> bool:
    return task.approval_status == ApprovalStatus.APPROVED


def can_see(ctx: RoomContext, task: Task) -> bool:
    return is_approved(task) or can(ctx, "task.approve") or is_proposer(ctx, task)


def can_edit_task(ctx: RoomContext, task: Task) -> bool:
    """Task fields. A proposer may edit their own proposal until it's approved."""
    return can(ctx, "task.create") or (not is_approved(task) and is_proposer(ctx, task))


def can_edit_stages(ctx: RoomContext, task: Task) -> bool:
    return can(ctx, "stage.edit") or (not is_approved(task) and is_proposer(ctx, task))


def can_delete_task(ctx: RoomContext, task: Task) -> bool:
    """Approvers delete anything; a proposer may withdraw their own proposal until it's approved."""
    return can(ctx, "task.create") or (not is_approved(task) and is_proposer(ctx, task))


def can_resubmit(ctx: RoomContext, task: Task) -> bool:
    return task.approval_status == ApprovalStatus.REJECTED and is_proposer(ctx, task)


def can_decide(ctx: RoomContext, task: Task) -> bool:
    return can(ctx, "task.approve") and not is_approved(task)


APPROVAL_VALUES = (ApprovalStatus.APPROVED, ApprovalStatus.PENDING, ApprovalStatus.REJECTED)


def parse_approval_statuses(raw: str | None) -> list[str]:
    """'pending,rejected' -> ['pending', 'rejected']. Default: approved only."""
    if raw is None or not raw.strip():
        return [ApprovalStatus.APPROVED]
    values = [v.strip() for v in raw.split(",") if v.strip()]
    bad = [v for v in values if v not in APPROVAL_VALUES]
    if bad or not values:
        raise ValidationFailed(
            "Some fields are invalid.",
            fields={"approval_status": "Use one or more of approved, pending, rejected (comma-separated)."},
        )
    return list(dict.fromkeys(values))  # de-duplicate, keep order


def task_order(sort: str | None):
    if sort == "submitted_at":
        return (Task.submitted_at, Task.created_at, Task.id)  # oldest first: an approvals queue
    return (Task.due_date, Task.created_at, Task.id)


def creators(db: Session, tasks: list[Task]) -> dict[uuid.UUID, UserBrief]:
    ids = {t.created_by for t in tasks}
    return {u.id: UserBrief(id=u.id, name=u.name) for u in db.scalars(select(User).where(User.id.in_(ids)))} if ids else {}


def load_stages(db: Session, task_id: uuid.UUID, *, lock: bool = False) -> list[Stage]:
    """lock=True for anything that changes stages: the rows are locked (in order, so two writers can't
    deadlock) until the transaction ends. Two "done" taps at the same moment then run one after the other,
    and the second sees the stage already done instead of announcing it twice. SQLite ignores the lock."""
    stmt = select(Stage).where(Stage.task_id == task_id).order_by(Stage.position, Stage.id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)  # fresh values, not the cached ones
    return list(db.scalars(stmt))


def touch(task: Task) -> None:
    task.updated_at = utcnow()


# ------------------------------------------------------------------ references (tags, assignees)

def valid_tag_ids(db: Session, ctx: RoomContext, tag_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    if not tag_ids:
        return set()
    return set(db.scalars(select(Tag.id).where(Tag.room_id == ctx.room.id, Tag.id.in_(tag_ids))))


def valid_member_ids(db: Session, ctx: RoomContext, user_ids: set[uuid.UUID]) -> set[uuid.UUID]:
    """Only ACTIVE members of this room can be assigned."""
    if not user_ids:
        return set()
    return set(
        db.scalars(
            select(Membership.user_id).where(
                Membership.room_id == ctx.room.id,
                Membership.status == MembershipStatus.ACTIVE,
                Membership.user_id.in_(user_ids),
            )
        )
    )


def check_stage_refs(errors: dict, prefix: str, tag_id, assignee_ids, ok_tags: set, ok_members: set) -> None:
    if tag_id is not None and tag_id not in ok_tags:
        errors[f"{prefix}tag_id"] = "This tag doesn't exist in this room."
    if any(uid not in ok_members for uid in assignee_ids):
        errors[f"{prefix}assignee_ids"] = "One or more people aren't active members of this room."


# ------------------------------------------------------------------ who is a participant

def my_stage_ids(db: Session, ctx: RoomContext, stages: list[Stage]) -> set[uuid.UUID]:
    """Stages where the caller is an assignee OR holds the stage's tag."""
    if not stages:
        return set()
    my_tags = set(db.scalars(select(MembershipTag.tag_id).where(MembershipTag.membership_id == ctx.membership.id)))
    assigned = set(
        db.scalars(
            select(StageAssignee.stage_id).where(
                StageAssignee.user_id == ctx.membership.user_id,
                StageAssignee.stage_id.in_([s.id for s in stages]),
            )
        )
    )
    return {s.id for s in stages if s.id in assigned or (s.tag_id is not None and s.tag_id in my_tags)}


# ------------------------------------------------------------------ list filters (shared by room list and My Tasks)

def stage_counts():
    """Per-task stage counts, used only to FILTER. Displayed numbers come from stage_logic."""
    return (
        select(
            Stage.task_id.label("task_id"),
            func.count().label("total"),
            func.sum(case((Stage.status == StageStatus.DONE, 1), else_=0)).label("done"),
            func.sum(case((Stage.status.in_([StageStatus.IN_PROGRESS, StageStatus.BLOCKED]), 1), else_=0)).label("active"),
        )
        .group_by(Stage.task_id)
        .subquery()
    )


def task_filters(agg, *, from_, to, status, overdue, blocked, now) -> list:
    conds = []
    # calendar window [from, to): a task matches if its span overlaps it
    if from_ is not None:
        conds.append(Task.due_date >= from_)
    if to is not None:
        conds.append(func.coalesce(Task.start_date, Task.due_date) < to)
    if status == TaskStatus.DONE:
        conds.append(agg.c.done == agg.c.total)
    elif status == TaskStatus.IN_PROGRESS:
        conds.append(and_(agg.c.done < agg.c.total, agg.c.done + agg.c.active > 0))
    elif status == TaskStatus.NOT_STARTED:
        conds.append(agg.c.done + agg.c.active == 0)
    if overdue:
        conds.append(and_(Task.due_date < now, agg.c.done < agg.c.total))
    if blocked:
        conds.append(select(Stage.id).where(Stage.task_id == Task.id, Stage.status == StageStatus.BLOCKED).exists())
    return conds


def participant_clause_any_room(user_id: uuid.UUID):
    """A stage involves this user if they're an assignee, OR hold the stage's tag through an
    ACTIVE membership in the task's own room. Correlates to the outer Task row."""
    my_tags_in_that_room = (
        select(MembershipTag.tag_id)
        .join(Membership, Membership.id == MembershipTag.membership_id)
        .where(
            Membership.user_id == user_id,
            Membership.room_id == Task.room_id,
            Membership.status == MembershipStatus.ACTIVE,
        )
    )
    return or_(
        Stage.id.in_(select(StageAssignee.stage_id).where(StageAssignee.user_id == user_id)),
        Stage.tag_id.in_(my_tags_in_that_room),
    )


def stage_is_overdue(stage: Stage, now) -> bool:
    return bool(stage.due_date and stage.status != StageStatus.DONE and as_utc(stage.due_date) < now)


# ------------------------------------------------------------------ responses

def is_task_overdue(task: Task, status: str, now) -> bool:
    return task.approval_status == ApprovalStatus.APPROVED and status != TaskStatus.DONE and as_utc(task.due_date) < now


def build_detail(db: Session, ctx: RoomContext, task: Task, stages: list[Stage]) -> TaskDetail:
    now = utcnow()
    stage_ids = [s.id for s in stages]

    tag_ids = {s.tag_id for s in stages if s.tag_id}
    tags = {t.id: t for t in db.scalars(select(Tag).where(Tag.id.in_(tag_ids)))} if tag_ids else {}

    assignees: dict[uuid.UUID, list[UserBrief]] = {sid: [] for sid in stage_ids}
    for stage_id, user in db.execute(
        select(StageAssignee.stage_id, User)
        .join(User, User.id == StageAssignee.user_id)
        .where(StageAssignee.stage_id.in_(stage_ids))
        .order_by(func.lower(User.name), User.id)
    ):
        assignees[stage_id].append(UserBrief(id=user.id, name=user.name))

    user_ids = {task.created_by} | {s.completed_by for s in stages if s.completed_by}
    user_ids |= {s.last_nudged_by for s in stages if s.last_nudged_by}
    user_ids |= {s.result_by for s in stages if s.result_by}
    user_ids |= {uid for uid in (task.approved_by, task.decided_by) if uid}
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_(user_ids)))}

    def brief(uid):
        u = users.get(uid) if uid else None
        return UserBrief(id=u.id, name=u.name) if u else None

    from app.models.progress import ProgressUpdate  # local: keeps imports one-directional

    update_counts = dict(
        db.execute(
            select(ProgressUpdate.stage_id, func.count())
            .where(ProgressUpdate.stage_id.in_(stage_ids))
            .group_by(ProgressUpdate.stage_id)
        ).all()
    ) if stage_ids else {}

    mine = my_stage_ids(db, ctx, stages)
    can_edit, can_override = can(ctx, "stage.edit"), can(ctx, "stage.override_lock")
    step_of = logic.steps(stages)
    summary = logic.summarize(stages)

    stage_out = []
    approved = is_approved(task)
    for i, s in enumerate(stages):
        # nobody works on a task until it's approved
        allowed = logic.allowed_statuses(
            stages, i, participant=s.id in mine, can_edit=can_edit, can_override=can_override
        ) if approved else []
        completed_by = users.get(s.completed_by) if s.completed_by else None
        from app.services import nudge_service  # local: nudge_service builds on this module

        nudge = None
        if s.last_nudged_at is not None and s.nudge_kind and (s.id in mine or can_edit):
            nudger = users.get(s.last_nudged_by) if s.last_nudged_by else None
            nudge = NudgeOut(at=as_utc(s.last_nudged_at), by=UserBrief(id=nudger.id, name=nudger.name) if nudger else None,
                             kind=s.nudge_kind, note=s.nudge_note, open=s.nudge_open)
        nudge_kind = nudge_service.kind_for(s, task, now) if (approved and can_edit) else None
        stage_out.append(
            StageOut(
                id=s.id,
                title=s.title,
                position=s.position,
                step=step_of[i],
                parallel_with_previous=s.parallel_with_previous,
                status=s.status,
                blocked_reason=s.blocked_reason,
                unlocked_early=s.unlocked_early,
                tag=TagBrief(id=tags[s.tag_id].id, name=tags[s.tag_id].name) if s.tag_id in tags else None,
                assignees=assignees[s.id],
                due_date=as_utc(s.due_date),
                is_overdue=stage_is_overdue(s, now),
                completed_at=as_utc(s.completed_at),
                completed_by=UserBrief(id=completed_by.id, name=completed_by.name) if completed_by else None,
                involves_me=s.id in mine,
                allowed_statuses=allowed,
                can_update_status=bool(allowed),
                update_count=update_counts.get(s.id, 0),
                result=ResultOut(url=s.result_url, note=s.result_note, by=brief(s.result_by), at=as_utc(s.result_at))
                if s.result_url else None,
                can_set_result=approved and s.status == StageStatus.DONE and (s.id in mine or can_edit),
                nudge=nudge,
                nudge_kind=nudge_kind,
                can_nudge=nudge_kind is not None and not nudge_service.nudged_recently(s, now),
            )
        )

    creator = users[task.created_by]
    return TaskDetail(
        id=task.id,
        room_id=task.room_id,
        title=task.title,
        description=task.description,
        start_date=as_utc(task.start_date),
        due_date=as_utc(task.due_date),
        approval_status=task.approval_status,
        status=summary.status,
        progress=summary.progress,
        stages_done=summary.done,
        stages_total=summary.total,
        current_stage_ids=summary.current_ids,
        current_stage_title=summary.current_title,
        is_overdue=is_task_overdue(task, summary.status, now),
        is_blocked=summary.is_blocked,
        created_by=UserBrief(id=creator.id, name=creator.name),
        created_at=as_utc(task.created_at),
        updated_at=as_utc(task.updated_at),
        completed_at=as_utc(summary.completed_at),
        approved_by=brief(task.approved_by),
        submitted_at=as_utc(task.submitted_at),
        decided_at=as_utc(task.decided_at),
        decided_by=brief(task.decided_by),
        rejection_reason=task.rejection_reason,
        can_edit=can_edit_task(ctx, task) and can_edit_stages(ctx, task),
        can_delete=can_delete_task(ctx, task),
        can_resubmit=can_resubmit(ctx, task),
        can_decide=can_decide(ctx, task),
        stages=stage_out,
    )


def build_list_item(task: Task, stages: list[Stage], involves_me: bool, now, creator: UserBrief) -> TaskListItem:
    summary = logic.summarize(stages)
    return TaskListItem(
        id=task.id,
        title=task.title,
        start_date=as_utc(task.start_date),
        due_date=as_utc(task.due_date),
        approval_status=task.approval_status,
        status=summary.status,
        progress=summary.progress,
        stages_done=summary.done,
        stages_total=summary.total,
        current_stage_title=summary.current_title,
        is_overdue=is_task_overdue(task, summary.status, now),
        is_blocked=summary.is_blocked,
        involves_me=involves_me,
        created_by=creator,
        submitted_at=as_utc(task.submitted_at),
        decided_at=as_utc(task.decided_at),
        rejection_reason=task.rejection_reason,
    )
