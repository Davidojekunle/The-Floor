import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import Page, UtcDateTime
from app.schemas.member import TagBrief
from app.schemas.room import UserBrief

StageStatusName = Literal["locked", "todo", "in_progress", "blocked", "done"]
TaskStatusName = Literal["not_started", "in_progress", "done"]
ApprovalStatusName = Literal["pending", "approved", "rejected"]


def _clean(v: str | None, what: str) -> str | None:
    if v is None:
        return v
    v = " ".join(v.split())
    if not v:
        raise ValueError(f"{what} can't be empty.")
    return v


# ------------------------------------------------------------------ output

class NudgeOut(BaseModel):
    """The last nudge on a stage. Shown to the people on it and to heads."""
    at: datetime
    by: UserBrief | None
    kind: Literal["update", "block"]
    note: str | None
    open: bool = Field(description="True until someone on the stage answers it.")


class NudgeIn(BaseModel):
    note: str | None = Field(None, max_length=200, description="Optional one line, e.g. “The event is on Friday.”")


class StageOut(BaseModel):
    id: uuid.UUID
    title: str
    position: int
    step: int
    parallel_with_previous: bool
    status: StageStatusName
    blocked_reason: str | None
    unlocked_early: bool
    tag: TagBrief | None
    assignees: list[UserBrief]
    due_date: datetime | None
    is_overdue: bool
    completed_at: datetime | None
    completed_by: UserBrief | None
    involves_me: bool
    allowed_statuses: list[StageStatusName]
    can_update_status: bool
    update_count: int = 0  # progress updates posted on this stage
    nudge: NudgeOut | None = None
    nudge_kind: Literal["update", "block"] | None = Field(
        None, description="What a nudge would be now (heads only): update = late or stuck 3+ days, block = blocked.")
    can_nudge: bool = Field(False, description="Heads/temp heads, the stage is late, stuck or blocked, and not nudged in 24h.")


class TaskDetail(BaseModel):
    id: uuid.UUID
    room_id: uuid.UUID
    title: str
    description: str | None
    start_date: datetime | None
    due_date: datetime
    approval_status: ApprovalStatusName
    status: TaskStatusName
    progress: int
    stages_done: int
    stages_total: int
    current_stage_ids: list[uuid.UUID]
    current_stage_title: str | None
    is_overdue: bool
    is_blocked: bool
    created_by: UserBrief
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
    # proposal lifecycle (phase 4)
    approved_by: UserBrief | None
    submitted_at: datetime
    decided_at: datetime | None
    decided_by: UserBrief | None
    rejection_reason: str | None
    # what the CURRENT user may do with this task (so the UI never rebuilds the proposer rule)
    can_edit: bool
    can_delete: bool
    can_resubmit: bool
    can_decide: bool
    stages: list[StageOut]


class TaskListItem(BaseModel):
    """Also the calendar item."""

    id: uuid.UUID
    title: str
    start_date: datetime | None
    due_date: datetime
    approval_status: ApprovalStatusName
    status: TaskStatusName
    progress: int
    stages_done: int
    stages_total: int
    current_stage_title: str | None
    is_overdue: bool
    is_blocked: bool
    involves_me: bool
    created_by: UserBrief
    submitted_at: datetime
    decided_at: datetime | None
    rejection_reason: str | None


class TaskPage(Page[TaskListItem]):
    pass


# ------------------------------------------------------------------ input

class StageIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    tag_id: uuid.UUID | None = None
    assignee_ids: list[uuid.UUID] = []
    due_date: UtcDateTime | None = None
    parallel_with_previous: bool = False

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        return _clean(v, "Title")


class TaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    start_date: UtcDateTime | None = None
    due_date: UtcDateTime
    stages: list[StageIn] = Field(min_length=1, max_length=30)

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        return _clean(v, "Title")


class TaskUpdate(BaseModel):
    """Only fields that are sent change. Send null to clear description or start_date."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=5000)
    start_date: UtcDateTime | None = None
    due_date: UtcDateTime | None = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str | None) -> str | None:
        return _clean(v, "Title")


class StageCreate(StageIn):
    position: int | None = Field(None, ge=1, description="1-based insert point. Default: append.")


class StageUpdate(BaseModel):
    """Only fields that are sent change. assignee_ids replaces the whole set."""

    title: str | None = Field(None, min_length=1, max_length=120)
    tag_id: uuid.UUID | None = None
    assignee_ids: list[uuid.UUID] | None = None
    due_date: UtcDateTime | None = None
    parallel_with_previous: bool | None = None
    position: int | None = Field(None, ge=1)

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str | None) -> str | None:
        return _clean(v, "Title")


class StatusUpdate(BaseModel):
    status: Literal["todo", "in_progress", "done", "blocked"]
    blocked_reason: str | None = Field(None, max_length=300)


# ------------------------------------------------------------------ My Tasks (across rooms)

class RoomBrief(BaseModel):
    id: uuid.UUID
    name: str


class MyStageOut(BaseModel):
    id: uuid.UUID
    title: str
    status: StageStatusName
    step: int
    due_date: datetime | None
    is_overdue: bool
    allowed_statuses: list[StageStatusName]  # computed with MY permissions in that room
    tag: TagBrief | None
    assigned_to_me: bool  # false = I'm in via the tag
    blocked_reason: str | None


class MyTaskItem(TaskListItem):
    room: RoomBrief
    my_stages: list[MyStageOut]


class MyTaskPage(Page[MyTaskItem]):
    pass


class RejectBody(BaseModel):
    reason: str | None = Field(None, max_length=500)
