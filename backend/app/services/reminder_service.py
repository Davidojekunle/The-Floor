"""Automatic reminders to the people on a stage: once when it's due within a day, once when it's overdue.

Only stages that are someone's turn (To do / In progress) on approved tasks. Each reminder remembers the
due date it was sent for, so moving the due date re-arms it. A stage that only just became someone's turn
waits an hour first, so a reminder doesn't land on top of its "ready for you". Runs from the sender loop.
Filed under "Work for you", so that switch (and muting a room) controls them.
"""
from datetime import timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import ApprovalStatus, StageStatus
from app.models.room import Room
from app.models.task import Stage, Task
from app.models.user import User
from app.services import notification_service as notes
from app.utils.time import as_utc, utcnow

WINDOW = timedelta(hours=24)
GRACE = timedelta(hours=1)


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def send_reminders(db: Session, now=None) -> int:
    now = now or utcnow()
    due_expr = func.coalesce(Stage.due_date, Task.due_date)
    rows = db.execute(
        select(Stage, Task, Room)
        .join(Task, Task.id == Stage.task_id)
        .join(Room, Room.id == Task.room_id)
        .where(Task.approval_status == ApprovalStatus.APPROVED,
               Stage.status.in_([StageStatus.TODO, StageStatus.IN_PROGRESS]),
               due_expr <= now + WINDOW)
    ).all()
    sent = 0
    for stage, task, room in rows:
        if now - as_utc(stage.status_since) < GRACE:
            continue
        due = as_utc(stage.due_date or task.due_date)
        overdue = due < now
        last = stage.reminded_overdue_for if overdue else stage.reminded_soon_for
        if last is not None and as_utc(last) == due:
            continue
        people = notes._participants(db, room.id, [stage])[stage.id]
        for uid in people:
            if overdue:
                title = f"“{stage.title}” on “{task.title}” is overdue"
                kind = "stage_overdue"
            else:
                user = db.get(User, uid)
                tz = _zone(user.timezone if user else None)
                day = "today" if due.astimezone(tz).date() == now.astimezone(tz).date() else "tomorrow"
                title = f"“{stage.title}” on “{task.title}” is due {day}"
                kind = "stage_due_soon"
            notes.notify(db, uid, kind, title, room=room, task=task, stage=stage)
            sent += 1
        if overdue:
            stage.reminded_overdue_for = due
            stage.reminded_soon_for = due  # never "due tomorrow" after "overdue"
        else:
            stage.reminded_soon_for = due
    db.commit()
    return sent
