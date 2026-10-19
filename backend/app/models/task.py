import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ApprovalStatus, StageStatus
from app.utils.time import utcnow


class Task(Base):
    """One deliverable. Its progress comes from its stages and is never stored."""

    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_room_due", "room_id", "due_date"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    approval_status: Mapped[str] = mapped_column(String(20), default=ApprovalStatus.APPROVED)
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # proposal lifecycle (phase 4)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)  # create, and every resubmit
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Stage(Base):
    """One unit of work inside a task, owned by a tag and/or specific people."""

    __tablename__ = "stages"
    __table_args__ = (Index("ix_stages_task_position", "task_id", "position"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer)  # 1..N, renumbered by the server
    parallel_with_previous: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(20), default=StageStatus.LOCKED)
    blocked_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    unlocked_early: Mapped[bool] = mapped_column(Boolean, default=False)
    tag_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tags.id", ondelete="SET NULL"), nullable=True, index=True
    )
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # when the stage reached its current status (kept by the listener below, whatever changed it)
    status_since: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    # nudges: a head asked for an update (kind "update") or about a block (kind "block")
    last_nudged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_nudged_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    nudge_kind: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nudge_note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nudge_open: Mapped[bool] = mapped_column(Boolean, default=False)  # true until someone on the stage answers

    # the finished work: a link to what this stage produced (a video, a design, a doc), shown on the task
    result_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    result_note: Mapped[str | None] = mapped_column(String(300), nullable=True)
    result_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    result_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # automatic reminders: the effective due date each one was sent for (a changed due date re-arms them)
    reminded_soon_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminded_overdue_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@event.listens_for(Stage.status, "set")
def _stamp_status_since(stage: "Stage", value, oldvalue, initiator) -> None:
    if value != oldvalue:
        stage.status_since = utcnow()


class StageAssignee(Base):
    __tablename__ = "stage_assignees"
    __table_args__ = (Index("ix_stage_assignees_user", "user_id"),)

    stage_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("stages.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
