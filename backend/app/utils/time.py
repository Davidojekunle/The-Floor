from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware current time in UTC. Store UTC everywhere."""
    return datetime.now(timezone.utc)
