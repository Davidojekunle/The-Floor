"""The admin page: is the app healthy, and is it being used? Totals and counts only.

Nothing here returns what anyone wrote (task titles, chat, notes) or who did what: staff see
numbers, never content, so the page is safe to show the people whose data it summarises.
"""
import time as _time
from datetime import datetime, timedelta, timezone

from sqlalchemy import Integer, case, distinct, func, or_, select, text
from sqlalchemy.orm import Session

from app.models.calendar import CalendarFeed
from app.models.email import OutboxEmail
from app.models.enums import ApprovalStatus, MembershipStatus, StageStatus
from app.models.message import Message, MessageType
from app.models.progress import ProgressUpdate
from app.models.push import PushSubscription
from app.models.refresh_token import RefreshToken
from app.models.room import Membership, Room
from app.models.task import Stage, Task
from app.models.user import User
from app.utils.time import utcnow

STARTED_AT = utcnow()
WEEKS = 8

# The background loop (emails, digests, reminders) reports in here after every pass.
LOOP: dict = {"last_run_at": None, "last_error_at": None, "last_error": None}


def loop_ran() -> None:
    LOOP["last_run_at"] = utcnow()


def loop_failed(e: Exception) -> None:
    LOOP["last_error_at"] = utcnow()
    LOOP["last_error"] = type(e).__name__  # the class only: messages can carry people's data


def _count(db: Session, stmt) -> int:
    return int(db.scalar(stmt) or 0)


def _aware(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is None:  # SQLite hands back naive datetimes
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _health(db: Session, now: datetime) -> dict:
    from app.services.push_service import STATS as PUSH

    t0 = _time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db.rollback()
        db_ok = False
    latency = round((_time.perf_counter() - t0) * 1000, 1)
    try:
        migration = db.scalar(text("SELECT version_num FROM alembic_version"))
    except Exception:  # tests build the tables without alembic
        db.rollback()
        migration = None

    week = now - timedelta(days=7)
    waiting = (OutboxEmail.sent_at.is_(None), OutboxEmail.failed_at.is_(None))
    return {
        "database_ok": db_ok,
        "database_ms": latency,
        "migration": migration,
        "started_at": STARTED_AT,
        "uptime_seconds": int((now - STARTED_AT).total_seconds()),
        "loop_last_run_at": LOOP["last_run_at"],
        "loop_last_error_at": LOOP["last_error_at"],
        "loop_last_error": LOOP["last_error"],
        "emails_waiting": _count(db, select(func.count()).select_from(OutboxEmail).where(*waiting)),
        "oldest_waiting_email_at": _aware(db.scalar(select(func.min(OutboxEmail.created_at)).where(*waiting))),
        "emails_sent_7d": _count(db, select(func.count()).select_from(OutboxEmail).where(OutboxEmail.sent_at >= week)),
        "emails_failed_7d": _count(db, select(func.count()).select_from(OutboxEmail).where(OutboxEmail.failed_at >= week)),
        "push_sent_since_start": PUSH["sent"],
        "push_failed_since_start": PUSH["failed"],
        "push_expired_since_start": PUSH["gone"],
    }


def _active_users(db: Session, since: datetime) -> int:
    # An open session swaps its refresh token at least every 15 minutes, so a new token means someone was here.
    return _count(db, select(func.count(distinct(RefreshToken.user_id))).where(RefreshToken.created_at >= since))


def _finished_tasks():
    """(task_id, finished_at) for approved tasks whose stages are all done."""
    done = func.sum(case((Stage.status == StageStatus.DONE, 1), else_=0).cast(Integer))
    return (
        select(Stage.task_id, func.max(Stage.completed_at).label("finished_at"))
        .join(Task, Task.id == Stage.task_id)
        .where(Task.approval_status == ApprovalStatus.APPROVED)
        .group_by(Stage.task_id)
        .having(func.count() == done)
        .subquery()
    )


def stats(db: Session, now: datetime | None = None) -> dict:
    now = now or utcnow()
    week, month = now - timedelta(days=7), now - timedelta(days=30)

    people = {
        "total": _count(db, select(func.count()).select_from(User)),
        "new_7d": _count(db, select(func.count()).select_from(User).where(User.created_at >= week)),
        "new_30d": _count(db, select(func.count()).select_from(User).where(User.created_at >= month)),
        "active_7d": _active_users(db, week),
        "active_30d": _active_users(db, month),
        "with_push": _count(db, select(func.count(distinct(PushSubscription.user_id)))),
        "with_calendar": _count(db, select(func.count(distinct(CalendarFeed.user_id)))),
    }

    members = (
        select(Membership.room_id, func.count().label("n"))
        .where(Membership.status == MembershipStatus.ACTIVE)
        .group_by(Membership.room_id)
        .subquery()
    )
    busy = select(Task.room_id).where(Task.created_at >= month)
    chatty = select(Message.room_id).where(Message.type == MessageType.USER, Message.created_at >= month)
    rooms = {
        "total": _count(db, select(func.count()).select_from(Room)),
        "new_30d": _count(db, select(func.count()).select_from(Room).where(Room.created_at >= month)),
        "active_30d": _count(db, select(func.count()).select_from(Room).where(or_(Room.id.in_(busy), Room.id.in_(chatty)))),
        "average_members": round(float(db.scalar(select(func.avg(members.c.n))) or 0), 1),
        "pending_join_requests": _count(
            db, select(func.count()).select_from(Membership).where(Membership.status == MembershipStatus.PENDING)
        ),
    }

    finished = _finished_tasks()
    approved = Task.approval_status == ApprovalStatus.APPROVED
    due = func.coalesce(Stage.due_date, Task.due_date)
    working = Stage.status.in_([StageStatus.TODO, StageStatus.IN_PROGRESS])
    live_stages = select(func.count()).select_from(Stage).join(Task, Task.id == Stage.task_id).where(approved)
    tasks_total = _count(db, select(func.count()).select_from(Task).where(approved))
    work = {
        "tasks_total": tasks_total,
        "tasks_open": tasks_total - _count(db, select(func.count()).select_from(finished)),
        "tasks_created_7d": _count(db, select(func.count()).select_from(Task).where(Task.created_at >= week)),
        "tasks_finished_7d": _count(db, select(func.count()).select_from(finished).where(finished.c.finished_at >= week)),
        "proposals_waiting": _count(
            db, select(func.count()).select_from(Task).where(Task.approval_status == ApprovalStatus.PENDING)
        ),
        "stages_done_7d": _count(
            db, select(func.count()).select_from(Stage).where(Stage.status == StageStatus.DONE, Stage.completed_at >= week)
        ),
        "stages_in_progress": _count(db, live_stages.where(Stage.status == StageStatus.IN_PROGRESS)),
        "stages_overdue": _count(
            db, live_stages.where(or_(working, Stage.status == StageStatus.BLOCKED), due < now)
        ),
        "stages_blocked": _count(db, live_stages.where(Stage.status == StageStatus.BLOCKED)),
        "stages_stuck": _count(db, live_stages.where(working, Stage.status_since < now - timedelta(days=3))),
    }

    nudged = select(func.count()).select_from(Stage).where(Stage.last_nudged_at >= month)
    activity = {
        "messages_7d": _count(
            db, select(func.count()).select_from(Message).where(Message.type == MessageType.USER, Message.created_at >= week)
        ),
        "updates_7d": _count(db, select(func.count()).select_from(ProgressUpdate).where(ProgressUpdate.created_at >= week)),
        "nudges_30d": _count(db, nudged),
        "nudges_answered_30d": _count(db, nudged.where(Stage.nudge_open.is_(False))),
    }

    return {
        "generated_at": now,
        "health": _health(db, now),
        "people": people,
        "rooms": rooms,
        "work": work,
        "activity": activity,
        "weeks": _weeks(db, now),
    }


def _weeks(db: Session, now: datetime) -> list[dict]:
    """The last 8 weeks, oldest first. The tables are small, so bucket in Python (same on SQLite and Postgres)."""
    first = now - timedelta(days=7 * WEEKS)
    weeks = [
        {"week_start": first + timedelta(days=7 * i), "signups": 0, "tasks_created": 0, "stages_done": 0, "messages": 0}
        for i in range(WEEKS)
    ]
    sources = (
        ("signups", select(User.created_at).where(User.created_at >= first)),
        ("tasks_created", select(Task.created_at).where(Task.created_at >= first)),
        ("stages_done", select(Stage.completed_at).where(Stage.status == StageStatus.DONE, Stage.completed_at >= first)),
        ("messages", select(Message.created_at).where(Message.type == MessageType.USER, Message.created_at >= first)),
    )
    for key, stmt in sources:
        for (at,) in db.execute(stmt):
            i = int((_aware(at) - first).total_seconds() // (7 * 86400))
            if 0 <= i < WEEKS:
                weeks[i][key] += 1
    return weeks
