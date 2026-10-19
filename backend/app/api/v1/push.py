"""Browser push: the server's public key, and registering or forgetting this browser."""
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.openapi import err
from app.core.ratelimit import MINUTE, limiter
from app.db.session import get_db
from app.models.user import User
from app.services import push_service

router = APIRouter()
UNAUTHED = {401: err("Missing, invalid, or expired token.")}


class PushConfig(BaseModel):
    public_key: str = Field(description="VAPID public key (base64url) for pushManager.subscribe's applicationServerKey.")


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200)
    auth: str = Field(min_length=8, max_length=100)


class PushSubscriptionIn(BaseModel):
    """PushSubscription.toJSON() from the browser."""
    endpoint: str = Field(max_length=1000)
    keys: PushKeys


class PushEndpoint(BaseModel):
    endpoint: str = Field(max_length=1000)


@router.get("/push/config", response_model=PushConfig, responses=UNAUTHED)
def get_push_config(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return PushConfig(public_key=push_service.public_key(db))


@router.post("/push/subscriptions", status_code=204,
             responses={**UNAUTHED, 422: err("Not a browser push address, or the keys are malformed.")})
def subscribe_push(body: PushSubscriptionIn, request: Request, user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    """Register this browser for push. Idempotent: the app sends it again on every start while push is on."""
    limiter.hit(f"push-subscribe:{user.id}", 30, MINUTE)
    push_service.subscribe(db, user, endpoint=body.endpoint, p256dh=body.keys.p256dh, auth=body.keys.auth,
                           user_agent=request.headers.get("user-agent"))
    return Response(status_code=204)


@router.post("/push/subscriptions/remove", status_code=204, responses=UNAUTHED)
def unsubscribe_push(body: PushEndpoint, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Stop pushing to this browser (turned off here, or signing out). Unknown endpoints are fine."""
    push_service.unsubscribe(db, user, body.endpoint)
    return Response(status_code=204)
