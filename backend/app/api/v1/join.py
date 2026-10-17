from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.room import JoinPreview, MembershipOut
from app.services import room_service

router = APIRouter()


@router.get("/{invite_code}", response_model=JoinPreview)
def preview(invite_code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return room_service.join_preview(db, user, invite_code)


@router.post("/{invite_code}", response_model=MembershipOut, status_code=201)
def request_to_join(invite_code: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return room_service.request_join(db, user, invite_code)
