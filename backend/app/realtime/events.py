"""Queue live events during a request; they're sent only after the commit succeeds.

Recipients are worked out at commit time (after a flush), using the same visibility
rules as REST, so a member removed in this request is excluded and one approved in it
is included. A rolled-back change sends nothing.
"""
import uuid

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.models.enums import ApprovalStatus, MembershipStatus, Role
from app.models.room import Membership, TempHead
from app.models.task import Task
from app.realtime.hub import hub
from app.utils.time import utcnow

_PENDING = "realtime_pending"
_CLOSE = "realtime_close"
_READY = "realtime_ready"


# ------------------------------------------------------------------ audiences

def room_members(db: Session, room_id) -> set[uuid.UUID]:
    return set(
        db.scalars(
            select(Membership.user_id).where(Membership.room_id == room_id, Membership.status == MembershipStatus.ACTIVE)
        )
    )


def task_audience(db: Session, task: Task) -> set[uuid.UUID]:
    """Who may see this task through REST right now."""
    members = room_members(db, task.room_id)
    if task.approval_status == ApprovalStatus.APPROVED:
        return members
    approvers = set(
        db.scalars(
            select(Membership.user_id).where(
                Membership.room_id == task.room_id, Membership.status == MembershipStatus.ACTIVE, Membership.role == Role.HEAD
            )
        )
    ) | set(
        db.scalars(
            select(TempHead.user_id).where(
                TempHead.room_id == task.room_id, TempHead.revoked_at.is_(None), TempHead.expires_at > utcnow()
            )
        )
    )
    return ({task.created_by} | approvers) & members


# ------------------------------------------------------------------ queueing

def _queue(db: Session, payload: dict, audience) -> None:
    """audience: ("room", room_id) | ("task", task_id) | a set of user ids (resolved now)."""
    db.info.setdefault(_PENDING, []).append((payload, audience))


def _payload(kind: str, room_id, **ids) -> dict:
    return {"type": kind, "room_id": str(room_id), **{k: str(v) for k, v in ids.items()}}


def message_created(db, room_id, message_id):
    _queue(db, _payload("message_created", room_id, message_id=message_id), ("room", room_id))


def message_deleted(db, room_id, message_id):
    _queue(db, _payload("message_deleted", room_id, message_id=message_id), ("room", room_id))


def task_changed(db, task: Task):
    _queue(db, _payload("task_changed", task.room_id, task_id=task.id), ("task", task.id))


def task_deleted(db, task: Task):
    # the task is about to disappear, so its audience is captured now
    _queue(db, _payload("task_deleted", task.room_id, task_id=task.id), task_audience(db, task))


def task_updates_changed(db, task: Task, stage_id):
    _queue(db, _payload("task_updates_changed", task.room_id, task_id=task.id, stage_id=stage_id), ("task", task.id))


def room_changed(db, room_id):
    _queue(db, _payload("room_changed", room_id), ("room", room_id))


def to_user(db, kind: str, room_id, user_id, **extra):
    """room_access_lost (with reason), room_access_granted, join_request_rejected: one person only."""
    _queue(db, {**_payload(kind, room_id), **extra}, {user_id})


def notification_created(db, user_id, room_id, notification_id):
    """A new bell item. room_id is the notification's room, or null."""
    _queue(db, {"type": "notification_created", "room_id": str(room_id) if room_id else None,
                "notification_id": str(notification_id)}, {user_id})


def account_changed(db, user_id):
    """Name, timezone, theme, email or pending_email changed: the user's other tabs refetch /me."""
    _queue(db, {"type": "account_changed", "room_id": None}, {user_id})


def close_sockets(db: Session, user_id) -> None:
    """After the commit, close all of this user's sockets with 4401."""
    db.info.setdefault(_CLOSE, set()).add(user_id)


# ------------------------------------------------------------------ commit hooks

def _resolve(db: Session, audience) -> set:
    if isinstance(audience, set):
        return audience
    kind, ref = audience
    if kind == "room":
        return room_members(db, ref)
    task = db.get(Task, ref)
    return task_audience(db, task) if task is not None else set()


@event.listens_for(Session, "before_commit")
def _resolve_before_commit(session: Session) -> None:
    pending = session.info.pop(_PENDING, None)
    if not pending:
        return
    session.flush()  # recipients must see this request's own changes
    merged: dict[tuple, tuple[dict, set]] = {}
    for payload, audience in pending:
        key = tuple(sorted(payload.items()))
        entry = merged.setdefault(key, (payload, set()))
        entry[1].update(_resolve(session, audience))
    session.info.setdefault(_READY, []).extend(v for v in merged.values() if v[1])


@event.listens_for(Session, "after_commit")
def _publish_after_commit(session: Session) -> None:
    ready = session.info.pop(_READY, None)
    if ready:
        hub.publish(ready)
    closing = session.info.pop(_CLOSE, None)
    if closing:
        hub.close_users(closing)


@event.listens_for(Session, "after_rollback")
def _discard_on_rollback(session: Session) -> None:
    session.info.pop(_PENDING, None)
    session.info.pop(_READY, None)
    session.info.pop(_CLOSE, None)
