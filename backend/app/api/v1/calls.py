"""Calls (contract v4, C1): start or join the live call in a room or about a task, and end it.
Everything here is 404 until CALLS_ENABLED is on, so calls can ship switched off and launch with a setting."""
import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_room_context
from app.models.user import User
from app.core.config import get_settings
from app.core.errors import NotFound, Unauthenticated
from app.core.openapi import err
from app.core.ratelimit import MINUTE, limiter
from app.db.session import get_db
from app.permissions.rules import RoomContext
from app.schemas.call import CallOut, CallPage, ClashCheck, ClashOut, JoinPass, MeetingIn, MeetingUpdate, RsvpIn, StartCall
from app.schemas.common import UtcDateTime
from app.schemas.common import PageParams, page_params
from app.services import call_service, meeting_service, site_service, video


def calls_on(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    """Calls are on for this person: everyone, or staff while the admin has them on for staff only."""
    if not site_service.calls_for(db, user):
        raise NotFound("Not found.")


router = APIRouter(dependencies=[Depends(calls_on)])
# Not switched off with the rest, so the webhook can be set up before launch. Its messages are signed, and only
# ever touch calls that are live.
webhooks = APIRouter()

BUSY = {503: err("CALL_PROVIDER_UNAVAILABLE: the video provider is down. Nothing was saved; retrying is safe.")}


def _limit(ctx: RoomContext) -> None:
    limiter.hit(f"calls:{ctx.membership.user_id}", 10, MINUTE)


@router.post("", response_model=CallOut, status_code=201,
             responses={200: {"model": CallOut, "description": "A call was already live here: that one."},
                        409: err("TASK_NOT_APPROVED: the task is still a proposal."), **BUSY})
def start_call(response: Response, body: StartCall | None = None, ctx: RoomContext = Depends(get_room_context),
               db: Session = Depends(get_db)):
    """Start a call in the room, or about a task. If one is already live there, you get that one (200)."""
    _limit(ctx)
    call, created = call_service.start_call(db, ctx, body.task_id if body else None)
    if not created:
        response.status_code = 200
    return call


@router.get("", response_model=CallPage)
def list_calls(status: Literal["scheduled", "live", "ended", "cancelled"] | None = Query(None),
               task_id: uuid.UUID | None = Query(None),
               from_: UtcDateTime | None = Query(None, alias="from"), to: UtcDateTime | None = Query(None),
               params: PageParams = Depends(page_params),
               ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    """The room's call log and meetings, newest first."""
    items, total = call_service.list_calls(db, ctx, status=status, task_id=task_id, offset=params.offset,
                                           limit=params.limit, start=from_, end=to)
    return CallPage(items=items, total=total, page=params.page, limit=params.limit)


@router.get("/{call_id}", response_model=CallOut)
def get_call(call_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    return call_service.get_call(db, ctx, call_id)


@router.post("/{call_id}/join", response_model=JoinPass,
             responses={409: err("CALL_ENDED: the call is over. CALL_FULL: 25 people are already in."), **BUSY})
def join_call(call_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    """Your own pass into the call, with your name on it."""
    _limit(ctx)
    return call_service.join_call(db, ctx, call_id)


@router.post("/{call_id}/end", status_code=204,
             responses={403: err("Only whoever started it, the head or a temp head can end it for everyone."),
                        409: err("CALL_ENDED: already over.")})
def end_call(call_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    """End for everyone."""
    call_service.end_call(db, ctx, call_id)
    return Response(status_code=204)


# ---------------------------------------------------------------- meetings (C2)

meetings = APIRouter(dependencies=[Depends(calls_on)])


@meetings.post("", response_model=CallOut, status_code=201,
               responses={403: err("Only the head or a temp head can schedule meetings."),
                          409: err("TASK_NOT_APPROVED: the task is still a proposal.")})
def schedule_meeting(body: MeetingIn, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    """Schedule a meeting (or a repeating series: the first one comes back). Invitees are told, with a calendar file."""
    return call_service.call_out(db, ctx, meeting_service.schedule(db, ctx, body))


@meetings.post("/check", response_model=ClashOut)
def check_meeting(body: ClashCheck, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    """Who already has a meeting then. A note for the form, never a block."""
    return ClashOut(clashes=meeting_service.clashes(db, ctx, starts_at=body.starts_at,
                                                    duration_minutes=body.duration_minutes, invite=body.invite,
                                                    exclude_id=body.exclude_call_id))


@meetings.patch("/{call_id}", response_model=CallOut,
                responses={403: err("Not yours to change."), 409: err("CALL_ENDED: it already started or finished.")})
def update_meeting(call_id: uuid.UUID, body: MeetingUpdate, ctx: RoomContext = Depends(get_room_context),
                   db: Session = Depends(get_db)):
    changes = body.model_dump(exclude_unset=True)
    if "invite" in changes:
        changes["invite"] = body.invite
    return call_service.call_out(db, ctx, meeting_service.update(db, ctx, call_id, changes))


@meetings.put("/{call_id}/rsvp", response_model=CallOut,
              responses={403: err("Only invitees can answer."), 409: err("CALL_ENDED: it already started or finished.")})
def rsvp_meeting(call_id: uuid.UUID, body: RsvpIn, ctx: RoomContext = Depends(get_room_context),
                 db: Session = Depends(get_db)):
    """Going, can't make it, or null to take the answer back."""
    return call_service.call_out(db, ctx, meeting_service.answer(db, ctx, call_id, body.response))


@meetings.delete("/{call_id}", status_code=204,
                 responses={403: err("Not yours to cancel."), 409: err("CALL_ENDED: it already started or finished.")})
def cancel_meeting(call_id: uuid.UUID, following: bool = Query(False, description="Also the later ones in its series"),
                   ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    meeting_service.cancel(db, ctx, call_id, following=following)
    return Response(status_code=204)


@webhooks.post("/webhooks/livekit", include_in_schema=False)
async def livekit_webhook(request: Request, db: Session = Depends(get_db)):
    """LiveKit reports joins and leaves. Signed with our API secret, so nobody can fake them."""
    raw = await request.body()
    if not video.signature_ok(raw, request.headers.get("authorization")):
        raise Unauthenticated("Bad signature.")
    try:
        event = json.loads(raw or b"{}")
    except ValueError:
        event = {}
    from starlette.concurrency import run_in_threadpool

    await run_in_threadpool(call_service.handle_webhook, db, event)
    return {"ok": True}
