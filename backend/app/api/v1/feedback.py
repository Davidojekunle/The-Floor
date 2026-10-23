"""Feedback from inside the app: emailed to the team's support inbox, with what's needed to follow up."""
from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.errors import ValidationFailed
from app.core.openapi import err
from app.core.ratelimit import HOUR, limiter
from app.db.session import get_db
from app.models.user import User
from app.services import email_service

router = APIRouter()

KINDS = {"problem": "Problem", "idea": "Idea", "other": "Other"}


class FeedbackIn(BaseModel):
    kind: Literal["problem", "idea", "other"] = "other"
    message: str = Field(min_length=1, max_length=4000)
    page: str | None = Field(default=None, max_length=300, description="The app page it was sent from")


@router.post("/feedback", status_code=204,
             responses={401: err("Missing, invalid, or expired token."), 429: err("Too much feedback in an hour.")})
def send_feedback(body: FeedbackIn, request: Request, user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    """Queue an email to the support inbox. Replying to it answers the person who sent it."""
    message = body.message.strip()
    if not message:
        raise ValidationFailed("Some fields are invalid.", fields={"message": "Write something first."})
    limiter.hit(f"feedback:{user.id}", 10, HOUR)
    kind = KINDS[body.kind]
    first_line = " ".join(message.split())[:60]
    text, html_body = email_service.render(
        f"{kind} from {user.name}",
        [
            message,
            f"From: {user.name} <{user.email}>",
            f"Page: {body.page or 'unknown'}",
            f"Browser: {(request.headers.get('user-agent') or 'unknown')[:300]}",
        ],
    )
    email_service.queue(
        db, to=get_settings().support_email, subject=f"[{kind}] {first_line}", text=text, html_body=html_body,
        category="feedback", user_id=user.id, headers={"Reply-To": user.email},
    )
    db.commit()
    return Response(status_code=204)
