"""Calendar subscription feeds: links for signed-in people, and the public .ics the calendar apps fetch."""
import uuid

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_room_context
from app.core.openapi import err
from app.core.ratelimit import MINUTE, client_ip, limiter
from app.db.session import get_db
from app.models.user import User
from app.permissions.rules import RoomContext
from app.services import calendar_service

router = APIRouter()
UNAUTHED = {401: err("Missing, invalid, or expired token.")}


class CalendarLinks(BaseModel):
    url: str = Field(description="The private .ics address. Anyone with it can read the feed.")
    webcal_url: str = Field(description="The same address as webcal://, which opens calendar apps directly.")
    google_url: str = Field(description="Opens Google Calendar’s “add this calendar” page.")


@router.get("/me/calendar-feed", response_model=CalendarLinks, responses=UNAUTHED)
def get_my_calendar_feed(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Your stages across all your rooms. Made on first request."""
    return calendar_service.links(calendar_service.get_or_create(db, user))


@router.post("/me/calendar-feed/reset", response_model=CalendarLinks, responses=UNAUTHED)
def reset_my_calendar_feed(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """A new private address; the old one stops working."""
    return calendar_service.links(calendar_service.reset(db, user))


@router.get("/rooms/{room_id}/calendar-feed", response_model=CalendarLinks)
def get_room_calendar_feed(room_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context),
                           db: Session = Depends(get_db)):
    """Every unfinished task in this room, for you. Stops working if you leave the room."""
    user = db.get(User, ctx.membership.user_id)
    return calendar_service.links(calendar_service.get_or_create(db, user, ctx.room.id))


@router.post("/rooms/{room_id}/calendar-feed/reset", response_model=CalendarLinks)
def reset_room_calendar_feed(room_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context),
                             db: Session = Depends(get_db)):
    user = db.get(User, ctx.membership.user_id)
    return calendar_service.links(calendar_service.reset(db, user, ctx.room.id))


@router.get("/calendar/{token}.ics", response_class=Response, responses={
    200: {"content": {"text/calendar": {}}, "description": "An iCalendar feed."},
    404: err("Unknown or reset link, or the room is no longer yours."),
})
def calendar_feed(token: str, request: Request, db: Session = Depends(get_db)):
    """Public on purpose: calendar apps can't sign in. The token is the secret."""
    limiter.hit(f"calendar:ip:{client_ip(request)}", 120, MINUTE)
    body = calendar_service.render(db, token)
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Cache-Control": "private, max-age=300", "Content-Disposition": 'inline; filename="the-floor.ics"'})
