from pydantic import BaseModel

from app.schemas.common import UtcDateTime


class AdminHealth(BaseModel):
    database_ok: bool
    database_ms: float
    migration: str | None
    started_at: UtcDateTime
    uptime_seconds: int
    loop_last_run_at: UtcDateTime | None  # emails, digests and reminders; should be seconds ago
    loop_last_error_at: UtcDateTime | None
    loop_last_error: str | None  # the error's type only
    emails_waiting: int
    oldest_waiting_email_at: UtcDateTime | None
    emails_sent_7d: int
    emails_failed_7d: int
    push_sent_since_start: int
    push_failed_since_start: int
    push_expired_since_start: int  # browsers that dropped their subscription (cleaned up)


class AdminPeople(BaseModel):
    total: int
    new_7d: int
    new_30d: int
    active_7d: int
    active_30d: int
    with_push: int
    with_calendar: int


class AdminRooms(BaseModel):
    total: int
    new_30d: int
    active_30d: int  # a task made or a chat message sent in the last 30 days
    average_members: float
    pending_join_requests: int


class AdminWork(BaseModel):
    tasks_total: int
    tasks_open: int
    tasks_created_7d: int
    tasks_finished_7d: int
    proposals_waiting: int
    stages_done_7d: int
    stages_in_progress: int
    stages_overdue: int
    stages_blocked: int
    stages_stuck: int  # To do or In progress for 3+ days


class AdminActivity(BaseModel):
    messages_7d: int
    updates_7d: int
    nudges_30d: int
    nudges_answered_30d: int


class AdminWeek(BaseModel):
    week_start: UtcDateTime
    signups: int
    tasks_created: int
    stages_done: int
    messages: int


class AdminStats(BaseModel):
    generated_at: UtcDateTime
    health: AdminHealth
    people: AdminPeople
    rooms: AdminRooms
    work: AdminWork
    activity: AdminActivity
    weeks: list[AdminWeek]
