import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time import utcnow


class DirectThread(Base):
    """A private conversation between two people. Started only between people who share a room;
    once started it stays open (unless one of them blocks the other)."""

    __tablename__ = "direct_threads"
    __table_args__ = (UniqueConstraint("user_low_id", "user_high_id", name="uq_direct_threads_pair"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    # the pair, in a fixed order (by id) so there's only ever one thread per two people
    user_low_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    user_high_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    low_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    high_read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DirectMessage(Base):
    __tablename__ = "direct_messages"
    __table_args__ = (Index("ix_direct_messages_thread_created", "thread_id", "created_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    thread_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("direct_threads.id", ondelete="CASCADE"))
    sender_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    body: Mapped[str | None] = mapped_column(Text, nullable=True)  # cleared when deleted
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserBlock(Base):
    """blocker_id doesn't want messages from blocked_id. Either direction stops a thread."""

    __tablename__ = "user_blocks"

    blocker_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    blocked_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
