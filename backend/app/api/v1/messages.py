import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_room_context
from app.db.session import get_db
from app.permissions.rules import RoomContext
from app.schemas.message import MarkRead, MessageCreate, MessageOut, MessagePage
from app.core.ratelimit import MINUTE, limiter
from app.services import chat_service

router = APIRouter()


@router.get("", response_model=MessagePage)
def list_messages(
    before: Annotated[uuid.UUID | None, Query(description="The `limit` messages immediately before this one")] = None,
    after: Annotated[uuid.UUID | None, Query(description="The `limit` messages immediately after this one (polling)")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    task_id: Annotated[uuid.UUID | None, Query(description="Only messages about this task")] = None,
    ctx: RoomContext = Depends(get_room_context),
    db: Session = Depends(get_db),
):
    return chat_service.list_messages(db, ctx, before=before, after=after, limit=limit, task_id=task_id)


@router.post("", response_model=MessageOut, status_code=201)
def send_message(body: MessageCreate, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    limiter.hit(f"chat:{ctx.membership.user_id}:{ctx.room.id}", 30, MINUTE)
    return chat_service.send_message(db, ctx, body)


@router.post("/read", status_code=204)
def mark_messages_read(
    body: MarkRead | None = None, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)
):
    chat_service.mark_read(db, ctx, body.up_to if body else None)
    return Response(status_code=204)


@router.delete("/{message_id}", status_code=204)
def delete_message(message_id: uuid.UUID, ctx: RoomContext = Depends(get_room_context), db: Session = Depends(get_db)):
    chat_service.delete_message(db, ctx, message_id)
    return Response(status_code=204)
