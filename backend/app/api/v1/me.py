from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import MeResponse
from app.services import room_service

router = APIRouter()


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return MeResponse(
        id=user.id,
        name=user.name,
        email=user.email,
        timezone=user.timezone,
        rooms=room_service.list_rooms_for_user(db, user),
    )
