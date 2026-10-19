from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.openapi import LOGIN_RESPONSES, REGISTER_RESPONSES
from app.core.security import create_access_token
from app.db.session import get_db
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserOut
from app.services import auth_service

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=201, responses=REGISTER_RESPONSES)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    return auth_service.register_user(
        db, name=body.name, email=body.email, password=body.password, timezone=body.timezone
    )


@router.post("/login", response_model=TokenResponse, responses=LOGIN_RESPONSES)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = auth_service.authenticate(db, email=body.email, password=body.password)
    token, expires_in = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_in=expires_in)
