from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """All models inherit from this. Alembic reads Base.metadata."""
