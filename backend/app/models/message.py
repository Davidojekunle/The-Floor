import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time import utcnow


class MessageType:
    USER = "user"
    SYSTEM = "system"


class Message(Base):
    """One message in a room's chat. System messages are posted by the server for key events."""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_room_created", "room_id", "created_at", "id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    room_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rooms.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(20), default=MessageType.USER)
    sender_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)  # null for system
    body: Mapped[str | None] = mapped_column(Text, nullable=True)  # cleared when deleted

    # optional pointer at work (titles are read live when the message is shown)
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"), nullable=True, index=True)
    stage_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("stages.id", ondelete="SET NULL"), nullable=True)

    # system messages only
    event_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    event_actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event_subject_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    event_detail: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
