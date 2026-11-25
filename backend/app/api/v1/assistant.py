from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_room_context
from app.db.session import get_db
from app.models.user import User
from app.permissions.rules import RoomContext
from app.schemas.assistant import AssistantReply, AssistantRequest, AssistantStatus
from app.services import task_assistant

router = APIRouter()


@router.get("", response_model=AssistantStatus)
def assistant_status(
    ctx: RoomContext = Depends(get_room_context), user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Staff only for now (404 for everyone else). How many new descriptions this room has left this week."""
    return task_assistant.status(db, ctx, user)


@router.post("/task-draft", response_model=AssistantReply)
def task_draft(
    body: AssistantRequest,
    ctx: RoomContext = Depends(get_room_context),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Describe a task in plain words; get questions back, or a draft to confirm. Nothing is created:
    the app fills the task form with the draft and the person presses Create there."""
    return task_assistant.reply(
        db, ctx, user, body.conversation_id, [m.model_dump() for m in body.messages]
    )
