"""My Tasks / My Calendar: tasks across every room the caller is an ACTIVE member of."""
import uuid
from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFound
from app.models.enums import ApprovalStatus, MembershipStatus
from app.models.room import Membership, Room
from app.models.tag import MembershipTag, Tag
from app.models.task import Stage, StageAssignee, Task
from app.models.user import User
from app.permissions.rules import can
from app.schemas.common import PageParams
from app.schemas.member import TagBrief
from app.schemas.task import MyStageOut, MyTaskItem, RoomBrief
from app.services import room_service, stage_logic
from app.services import task_common as common
from app.utils.time import as_utc, utcnow


def list_my_tasks(
    db: Session,
    user: User,
    params: PageParams,
    *,
    scope: str,
    actionable: bool | None,
    from_: datetime | None,
    to: datetime | None,
    status: str | None,
    overdue: bool | None,
    blocked: bool | None,
    room: uuid.UUID | None,
    approval_status: str | None = None,
    sort: str | None = None,
) -> tuple[list[MyTaskItem], int]:
    now = utcnow()

    rooms = {
        r.id: r
        for r in db.scalars(
            select(Room)
            .join(Membership, Membership.room_id == Room.id)
            .where(Membership.user_id == user.id, Membership.status == MembershipStatus.ACTIVE)
        )
    }
    if room is not None:
        if room not in rooms:
            raise NotFound("Room not found.")  # same answer as a room that doesn't exist
        room_ids = [room]
    else:
        room_ids = list(rooms)
    if not room_ids:
        return [], 0

    statuses = common.parse_approval_statuses(approval_status)
    agg = common.stage_counts()
    conds = [Task.room_id.in_(room_ids)]
    conds += common.task_filters(agg, from_=from_, to=to, status=status, overdue=overdue, blocked=blocked, now=now)

    involves_me = common.participant_clause_any_room(user.id)
    parts = []
    if ApprovalStatus.APPROVED in statuses:
        approved = [Task.approval_status == ApprovalStatus.APPROVED]
        if scope == "mine":
            approved.append(select(Stage.id).where(Stage.task_id == Task.id, involves_me).exists())
        if actionable:
            approved.append(
                select(Stage.id).where(Stage.task_id == Task.id, involves_me, Stage.status.in_(stage_logic.ACTIONABLE)).exists()
            )
        parts.append(and_(*approved))
    proposal_statuses = [st for st in statuses if st != ApprovalStatus.APPROVED]
    if proposal_statuses:
        # proposals here are always MY OWN, whatever the scope ("My proposals")
        parts.append(and_(Task.approval_status.in_(proposal_statuses), Task.created_by == user.id))
    conds.append(or_(*parts))

    base = select(Task).join(agg, agg.c.task_id == Task.id).where(*conds)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    tasks = list(db.scalars(base.order_by(*common.task_order(sort)).offset(params.offset).limit(params.limit)))
    if not tasks:
        return [], total
    people = common.creators(db, tasks)

    task_ids = [t.id for t in tasks]
    stages_by_task: dict[uuid.UUID, list[Stage]] = {tid: [] for tid in task_ids}
    for stage in db.scalars(select(Stage).where(Stage.task_id.in_(task_ids)).order_by(Stage.task_id, Stage.position, Stage.id)):
        stages_by_task[stage.task_id].append(stage)

    # what makes a stage "mine": direct assignment, or my tag in THAT room
    assigned = set(
        db.scalars(
            select(StageAssignee.stage_id).where(
                StageAssignee.user_id == user.id,
                StageAssignee.stage_id.in_(select(Stage.id).where(Stage.task_id.in_(task_ids))),
            )
        )
    )
    my_tags_by_room: dict[uuid.UUID, set[uuid.UUID]] = {}
    for room_id, tag_id in db.execute(
        select(Membership.room_id, MembershipTag.tag_id)
        .join(MembershipTag, MembershipTag.membership_id == Membership.id)
        .where(Membership.user_id == user.id, Membership.status == MembershipStatus.ACTIVE)
    ):
        my_tags_by_room.setdefault(room_id, set()).add(tag_id)

    tag_ids = {s.tag_id for stages in stages_by_task.values() for s in stages if s.tag_id}
    tags = {t.id: t for t in db.scalars(select(Tag).where(Tag.id.in_(tag_ids)))} if tag_ids else {}

    # permissions differ per room (temp head here, member there), so resolve each room once
    contexts = {rid: room_service.get_room_context(db, rid, user) for rid in {t.room_id for t in tasks}}

    items = []
    for task in tasks:
        stages = stages_by_task[task.id]
        ctx = contexts[task.room_id]
        can_edit, can_override = can(ctx, "stage.edit"), can(ctx, "stage.override_lock")
        my_tags = my_tags_by_room.get(task.room_id, set())
        step_of = stage_logic.steps(stages)

        my_stages = []
        for i, s in enumerate(stages):
            if not (s.id in assigned or (s.tag_id is not None and s.tag_id in my_tags)):
                continue
            tag = tags.get(s.tag_id)
            my_stages.append(
                MyStageOut(
                    id=s.id,
                    title=s.title,
                    status=s.status,
                    step=step_of[i],
                    due_date=as_utc(s.due_date),
                    is_overdue=common.stage_is_overdue(s, now),
                    allowed_statuses=stage_logic.allowed_statuses(
                        stages, i, participant=True, can_edit=can_edit, can_override=can_override
                    ) if common.is_approved(task) else [],  # no work until approved
                    tag=TagBrief(id=tag.id, name=tag.name) if tag else None,
                    assigned_to_me=s.id in assigned,
                    blocked_reason=s.blocked_reason,
                )
            )

        base_item = common.build_list_item(task, stages, bool(my_stages), now, people[task.created_by])
        items.append(
            MyTaskItem(
                **base_item.model_dump(),
                room=RoomBrief(id=task.room_id, name=rooms[task.room_id].name),
                my_stages=my_stages,
            )
        )
    return items, total
