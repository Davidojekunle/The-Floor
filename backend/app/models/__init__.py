# Import every model here so Base.metadata (used by Alembic) sees all tables.
from app.models.room import Membership, Room, TempHead  # noqa: F401
from app.models.user import User  # noqa: F401
