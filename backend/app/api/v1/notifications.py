import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.errors import NotFound
from app.core.openapi import err
from app.db.session import get_db
from app.models.notification import Notification
from app.models.user import User
from app.schemas.notification import (
    MarkReadRequest,
    NamedRef,
    NotificationOut,
    NotificationPage,
    NotificationSettingsOut,
    NotificationSettingsUpdate,
    TitledRef,
)
from app.services import notification_service as notes
from app.services import room_service
from app.utils.time import as_utc

router = APIRouter()
UNAUTHED = {401: err("Missing, invalid, or expired token.")}


def notification_out(n: Notification) -> NotificationOut:
    return NotificationOut(
        id=n.id, type=n.type, title=n.title,
        room=NamedRef(id=n.room_id, name=n.room_name) if n.room_id else None,
        task=TitledRef(id=n.task_id, title=n.task_title) if n.task_id else None,
        stage=TitledRef(id=n.stage_id, title=n.stage_title) if n.stage_id else None,
        actor=NamedRef(id=n.actor_id, name=n.actor_name) if n.actor_id else None,
        data=n.data, created_at=as_utc(n.created_at), read=n.read_at is not None,
    )


def settings_out(db: Session, user: User) -> NotificationSettingsOut:
    s = notes.settings_for(db, user.id)
    return NotificationSettingsOut(**{k: getattr(s, k) for k in notes.SWITCHES},
                                   muted_rooms=notes.muted_room_ids(db, user.id))


# ------------------------------------------------------------------ the bell

@router.get("/me/notifications", response_model=NotificationPage,
            responses={**UNAUTHED, 422: err("`before` isn't one of your notifications, or `limit` is out of range.")})
def list_notifications(
    unread: Annotated[bool, Query(description="Only unread ones")] = False,
    before: Annotated[uuid.UUID | None, Query(description="Cursor: the last id of the previous page")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Newest first."""
    rows, has_more = notes.list_notifications(db, user, unread=unread, before=before, limit=limit)
    return NotificationPage(items=[notification_out(n) for n in rows], has_more=has_more)


@router.post("/me/notifications/read", status_code=204,
             responses={**UNAUTHED, 422: err("`up_to` isn't one of your notifications.")})
def mark_notifications_read(body: MarkReadRequest | None = None, user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """With `up_to`: that one and everything older. With no body: everything."""
    notes.mark_read(db, user, body.up_to if body else None)
    return Response(status_code=204)


@router.post("/me/notifications/{notification_id}/read", status_code=204,
             responses={**UNAUTHED, 404: err("Not one of your notifications.")})
def mark_notification_read(notification_id: uuid.UUID, user: User = Depends(get_current_user),
                           db: Session = Depends(get_db)):
    if not notes.mark_one_read(db, user, notification_id):
        raise NotFound("Notification not found.")
    return Response(status_code=204)


# ------------------------------------------------------------------ settings

@router.get("/me/notification-settings", response_model=NotificationSettingsOut, responses=UNAUTHED)
def get_notification_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return settings_out(db, user)


@router.patch("/me/notification-settings", response_model=NotificationSettingsOut, responses=UNAUTHED)
def update_notification_settings(body: NotificationSettingsUpdate, user: User = Depends(get_current_user),
                                 db: Session = Depends(get_db)):
    notes.update_settings(db, user, body.model_dump(exclude_unset=True))
    return settings_out(db, user)


MUTE_RESPONSES = {**UNAUTHED, 404: err("Not a room you're an active member of.")}


@router.put("/me/notification-settings/muted-rooms/{room_id}", response_model=NotificationSettingsOut,
            responses=MUTE_RESPONSES)
def mute_room(room_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Silences this room on both channels. Safe to repeat. Unread chat badges still show."""
    room_service.get_room_context(db, room_id, user)  # 404 unless an active member
    notes.mute(db, user, room_id)
    return settings_out(db, user)


@router.delete("/me/notification-settings/muted-rooms/{room_id}", response_model=NotificationSettingsOut,
               responses=UNAUTHED)
def unmute_room(room_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Safe to repeat, and works for a room you've since left."""
    notes.unmute(db, user, room_id)
    return settings_out(db, user)
