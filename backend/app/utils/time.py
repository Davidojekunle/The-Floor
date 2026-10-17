from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware current time in UTC. Store UTC everywhere."""
    return datetime.now(timezone.utc)


def as_utc(dt: datetime | None) -> datetime | None:
    """SQLite hands back naive datetimes; treat them as UTC. Postgres already returns aware ones."""
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
