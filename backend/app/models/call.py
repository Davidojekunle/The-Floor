"""Calls (contract v4). C1: instant calls in a room or about a task. Video goes between browsers and the
provider (LiveKit); these rows only track the call's life and who is in it."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text, Uuid, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time import utcnow


class CallKind:
    INSTANT = "instant"
    SCHEDULED = "scheduled"


class CallStatus:
    SCHEDULED = "scheduled"
    LIVE = "live"
    ENDED = "ended"
    CANCELLED = "cancelled"


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = (
        # one live call per room (room calls) and one per task: the database settles a race to start one
        Index("uq_calls_live_room", "room_id", unique=True,
              postgresql_where=text("status = 'live' AND task_id IS NULL"),
              sqlite_where=text("status = 'live' AND task_id IS NULL")),
        Index("uq_calls_live_task", "task_id", unique=True,
              postgresql_where=text("status = 'live' AND task_id IS NOT NULL"),
              sqlite_where=text("status = 'live' AND task_id IS NOT NULL")),
        Index("ix_calls_room_status", "room_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True)
    kind: Mapped[str] = mapped_column(String(20), default=CallKind.INSTANT)
    status: Mapped[str] = mapped_column(String(20), default=CallStatus.LIVE)
    missed: Mapped[bool] = mapped_column(Boolean, default=False)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # scheduled (C2)
    ends_at_planned: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    hard_stop_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # the 3-hour limit
    # since when nobody has been in it (set at start and whenever the last person leaves; cleared on a join)
    empty_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    provider_room: Mapped[str | None] = mapped_column(String(100), nullable=True)
    external_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)  # C2: a pasted Meet/Zoom link
    invite_everyone: Mapped[bool] = mapped_column(Boolean, default=False)  # C2
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # C2
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CallParticipant(Base):
    """One join: a row per provider session, closed when they leave. Feeds "who's in" and minutes used."""

    __tablename__ = "call_participants"
    __table_args__ = (Index("ix_call_participants_call_open", "call_id", "left_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    call_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    session_id: Mapped[str] = mapped_column(String(100), unique=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    left_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
