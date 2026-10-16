from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.models.user import User
from app.schemas.auth import MeResponse

router = APIRouter()


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(get_current_user)):
    # `rooms` is empty until rooms exist (next step); the shape is already final.
    return MeResponse(id=user.id, name=user.name, email=user.email, timezone=user.timezone, rooms=[])
