"""Private DMs between people who share a room (see services/dm_service.py for the rules)."""
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.common import UtcDateTime
from app.schemas.direct import DmMessageOut, DmMessagePage, DmSend, DmStart, DmThreadList, DmThreadOut, DmUser
from app.services import dm_service

router = APIRouter()


@router.get("/dms", response_model=DmThreadList)
def list_dm_threads(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Your conversations, most recent first."""
    return {"items": dm_service.list_threads(db, user)}


@router.post("/dms", response_model=DmThreadOut)
def start_dm(body: DmStart, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Open the conversation with someone (finds it if it already exists). A new one needs a shared room."""
    return dm_service.start(db, user, body.user_id)


@router.get("/dms/{thread_id}", response_model=DmThreadOut)
def get_dm_thread(thread_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return dm_service.get_thread(db, user, thread_id)


@router.get("/dms/{thread_id}/messages", response_model=DmMessagePage)
def list_dm_messages(
    thread_id: uuid.UUID,
    before: Annotated[UtcDateTime | None, Query(description="Only messages older than this")] = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return dm_service.messages(db, user, thread_id, before)


@router.post("/dms/{thread_id}/messages", response_model=DmMessageOut, status_code=201)
def send_dm(thread_id: uuid.UUID, body: DmSend, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return dm_service.send(db, user, thread_id, body.body)


@router.delete("/dms/{thread_id}/messages/{message_id}", status_code=204)
def delete_dm(thread_id: uuid.UUID, message_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dm_service.delete_message(db, user, thread_id, message_id)
    return Response(status_code=204)


@router.post("/dms/{thread_id}/read", status_code=204)
def mark_dm_read(thread_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dm_service.mark_read(db, user, thread_id)
    return Response(status_code=204)


@router.get("/blocks", response_model=list[DmUser])
def list_blocks(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """People you blocked."""
    return dm_service.blocks(db, user)


@router.put("/blocks/{user_id}", status_code=204)
def block_user(user_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Stop messages between you and them, both ways. They aren't told."""
    dm_service.block(db, user, user_id)
    return Response(status_code=204)


@router.delete("/blocks/{user_id}", status_code=204)
def unblock_user(user_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    dm_service.unblock(db, user, user_id)
    return Response(status_code=204)
