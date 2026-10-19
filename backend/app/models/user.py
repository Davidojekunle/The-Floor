import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.utils.time import utcnow


class User(Base):
    """A global account. Roles and tags live on Membership (per room), not here."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    theme: Mapped[str] = mapped_column(String(10), default="system", server_default="system")  # system | light | dark
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # access tokens issued before this moment (whole seconds) are rejected: sign-out takes effect at once
    sessions_valid_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
