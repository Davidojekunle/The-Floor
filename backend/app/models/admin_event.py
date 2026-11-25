import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time import utcnow


class AdminEvent(Base):
    """The admin change log: who turned a site switch on or off, and who made or removed an admin."""

    __tablename__ = "admin_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    actor_name: Mapped[str] = mapped_column(String(100))  # kept if the account is later deleted
    action: Mapped[str] = mapped_column(String(40))  # setting_changed | admin_added | admin_removed
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
