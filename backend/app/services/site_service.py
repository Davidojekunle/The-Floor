"""Site-wide switches staff change from the admin page: calls (off, staff only, everyone), new sign-ups,
notification emails, the daily digest, push, and an announcement banner. Stored in the database, so changing one
takes effect at once with no redeploy. Security emails (password resets, confirmations) never depend on these.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.site import SiteSetting
from app.models.user import User
from app.utils.time import utcnow

DEFAULTS: dict = {
    "calls": "off",  # off | staff | everyone
    "signups_open": True,
    "notification_emails": True,
    "daily_digest": True,
    "push": True,
    "announcement": None,  # text shown to everyone signed in, or None
    "task_assistant": "staff",  # off | staff | everyone: who can "Describe your task"
}
_CACHE = "site_settings"


def get(db: Session) -> dict:
    """All switches, defaults filled in. Read once per database session."""
    if _CACHE not in db.info:
        stored = {row.key: row.value for row in db.scalars(select(SiteSetting))}
        db.info[_CACHE] = {**DEFAULTS, **{k: v for k, v in stored.items() if k in DEFAULTS}}
    return db.info[_CACHE]


def update(db: Session, user: User, changes: dict) -> dict:
    from app.services import admin_people  # here, not at the top: admin_people never imports this module back

    before = dict(get(db))
    for key, value in changes.items():
        if key not in DEFAULTS:
            continue
        if before.get(key) != value:
            short = lambda v: v[:200] if isinstance(v, str) else v  # noqa: E731
            admin_people.log(db, user, "setting_changed", {"key": key, "old": short(before.get(key)), "new": short(value)})
        row = db.get(SiteSetting, key)
        if row is None:
            row = SiteSetting(key=key)
            db.add(row)
        row.value, row.updated_at, row.updated_by = value, utcnow(), user.id
    db.info.pop(_CACHE, None)
    db.commit()
    return get(db)


# ------------------------------------------------------------------ calls

def calls_ready() -> bool:
    """The video provider is configured on this server (or faked in tests)."""
    s = get_settings()
    return s.video_provider == "fake" or bool(s.livekit_url and s.livekit_api_key and s.livekit_api_secret)


def calls_mode(db: Session) -> str:
    """CALLS_ENABLED (tests, local) forces everyone; otherwise the admin switch, and off until LiveKit is set up."""
    if get_settings().calls_enabled:
        return "everyone"
    return get(db)["calls"] if calls_ready() else "off"


def calls_for(db: Session, user: User | None) -> bool:
    mode = calls_mode(db)
    return mode == "everyone" or (mode == "staff" and user is not None and user.is_staff)


def calls_anywhere(db: Session) -> bool:
    return calls_mode(db) != "off"


def calls_public(db: Session) -> bool:
    """Chat cards about calls go to the whole room only once calls are on for everyone."""
    return calls_mode(db) == "everyone"


# ------------------------------------------------------------------ other switches

def notification_emails(db: Session) -> bool:
    return bool(get(db)["notification_emails"])


def daily_digest(db: Session) -> bool:
    return bool(get(db)["daily_digest"]) and notification_emails(db)


def push(db: Session) -> bool:
    return bool(get(db)["push"])


def signups_open(db: Session) -> bool:
    return bool(get(db)["signups_open"])


def public(db: Session) -> dict:
    """What any visitor may know: whether sign-ups are open, and the announcement."""
    s = get(db)
    return {"signups_open": bool(s["signups_open"]), "announcement": s["announcement"]}
