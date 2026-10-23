from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.v1.me import build_me
from app.core.config import get_settings
from app.core.errors import Forbidden
from app.core.ratelimit import HOUR, MINUTE, client_ip, limiter
from app.core.openapi import LOGIN_RESPONSES, REGISTER_RESPONSES, SESSION_RESPONSES, err
from app.core.security import create_access_token
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    AcceptedResponse,
    CancelEmailChangeRequest,
    ChangeEmailRequest,
    ChangePasswordRequest,
    ConfirmEmailRequest,
    ForgotPasswordRequest,
    LoginRequest,
    RefreshResponse,
    RegisterRequest,
    ResetPasswordRequest,
    TokenResponse,
    UserOut,
    VerifyEmailRequest,
)
from app.schemas.errors import ErrorResponse
from app.services import account_service, auth_service, email_service, password_service, session_service
from app.services.auth_service import normalize_email

router = APIRouter()

COOKIE = "tr_refresh"
COOKIE_PATH = "/api/v1/auth"


def require_client_header(
    x_taskroom_client: Annotated[str | None, Header(description="Must be `web`. Blocks cross-site requests.")] = None,
) -> None:
    if x_taskroom_client != "web":
        raise Forbidden("Send the header X-Taskroom-Client: web.")


def _set_cookie(response: Response, raw: str) -> None:
    s = get_settings()
    response.set_cookie(
        COOKIE, raw, max_age=s.refresh_token_days * 86400, httponly=True, samesite="lax",
        secure=s.refresh_cookie_secure, path=COOKIE_PATH,
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE, path=COOKIE_PATH, httponly=True, samesite="lax", secure=get_settings().refresh_cookie_secure)


@router.post("/register", response_model=UserOut, status_code=201, responses=REGISTER_RESPONSES)
def register(body: RegisterRequest, request: Request, db: Session = Depends(get_db)):
    limiter.hit(f"register:ip:{client_ip(request)}", 50, HOUR)  # loose: a whole class may share one IP
    limiter.hit(f"register:email:{normalize_email(body.email)}", 3, HOUR)
    user = auth_service.register_user(
        db, name=body.name, email=body.email, password=body.password, timezone=body.timezone
    )
    account_service.send_verification(db, user, email_service.link_base(request))
    db.commit()
    return user


@router.post("/login", response_model=TokenResponse, responses=LOGIN_RESPONSES, dependencies=[Depends(require_client_header)])
def login(body: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)):
    limiter.hit(f"login:ip:{client_ip(request)}", 100, MINUTE)
    # counted per email whether or not the account exists, so a 429 never reveals which emails are registered
    limiter.hit(f"login:email:{normalize_email(body.email)}", 5, MINUTE)
    user = auth_service.authenticate(db, email=body.email, password=body.password)
    raw = session_service.start_session(db, user)
    db.commit()
    _set_cookie(response, raw)
    token, expires_in = create_access_token(user.id)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/refresh", response_model=RefreshResponse, responses=SESSION_RESPONSES, dependencies=[Depends(require_client_header)])
def refresh_session(
    request: Request,
    response: Response,
    tr_refresh: Annotated[str | None, Cookie(include_in_schema=False)] = None,
    db: Session = Depends(get_db),
):
    limiter.hit(f"refresh:ip:{client_ip(request)}", 300, MINUTE)
    try:
        user, raw = session_service.rotate(db, tr_refresh)
    except session_service.SessionEnded as exc:
        failed = JSONResponse(status_code=401, content={"error": {"code": exc.code, "message": exc.message}})
        _clear_cookie(failed)
        return failed
    _set_cookie(response, raw)
    token, expires_in = create_access_token(user.id)
    return RefreshResponse(access_token=token, expires_in=expires_in, me=build_me(db, user))


@router.post("/logout", status_code=204, responses=SESSION_RESPONSES, dependencies=[Depends(require_client_header)])
def logout(
    tr_refresh: Annotated[str | None, Cookie(include_in_schema=False)] = None,
    db: Session = Depends(get_db),
):
    session_service.end_session(db, tr_refresh)
    done = Response(status_code=204)
    _clear_cookie(done)
    return done


@router.post("/logout-all", status_code=204, responses=SESSION_RESPONSES, dependencies=[Depends(require_client_header)])
def logout_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    session_service.end_all_sessions(db, user)
    done = Response(status_code=204)
    _clear_cookie(done)
    return done


FORGOT_RESPONSES = {**SESSION_RESPONSES}
FORGOT_RESPONSES.pop(401, None)


@router.post("/forgot-password", status_code=202, response_model=AcceptedResponse,
             responses=FORGOT_RESPONSES, dependencies=[Depends(require_client_header)])
def forgot_password(body: ForgotPasswordRequest, request: Request, db: Session = Depends(get_db)):
    limiter.hit(f"forgot:ip:{client_ip(request)}", 100, HOUR)
    password_service.request_reset(db, body.email, request)
    # identical whether or not the account exists
    return AcceptedResponse(message="If an account exists for that address, we've sent a link to reset the password.")


@router.post("/reset-password", status_code=204, dependencies=[Depends(require_client_header)],
             responses={400: {"model": ErrorResponse,
                              "description": "RESET_TOKEN_INVALID: the link is bad, used, cancelled, or expired."}})
def reset_password(body: ResetPasswordRequest, db: Session = Depends(get_db)):
    password_service.reset(db, body.token, body.new_password)
    return Response(status_code=204)


# ================================================================== account (L3)

CLIENT = [Depends(require_client_header)]
WRONG_PASSWORD = {401: err("INVALID_CREDENTIALS (`fields.current_password`): wrong current password. "
                           "UNAUTHENTICATED: missing or expired token."),
                  403: err("Missing the X-Taskroom-Client: web header.")}
BAD_EMAIL_LINK = {400: err("EMAIL_TOKEN_INVALID: the link is bad, used, cancelled, or expired.")}
TAKEN = {409: err("CONFLICT: the new address belongs to another account. `fields.new_email` is set.")}


@router.post("/change-password", response_model=TokenResponse, dependencies=CLIENT, responses=WRONG_PASSWORD)
def change_password(
    body: ChangePasswordRequest,
    user: User = Depends(get_current_user),
    tr_refresh: Annotated[str | None, Cookie(include_in_schema=False)] = None,
    db: Session = Depends(get_db),
):
    """Every other session ends immediately. This tab gets a fresh access token and keeps its session."""
    token, expires_in = account_service.change_password(db, user, body.current_password, body.new_password, tr_refresh)
    return TokenResponse(access_token=token, expires_in=expires_in)


@router.post("/change-email", status_code=202, response_model=AcceptedResponse, dependencies=CLIENT,
             responses={**WRONG_PASSWORD, **TAKEN})
def change_email(body: ChangeEmailRequest, request: Request, user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    """Sends a confirm link to the new address and a cancel link to the current one."""
    account_service.request_email_change(db, user, body.new_email, body.current_password, request)
    return AcceptedResponse(message=f"We've sent a link to {normalize_email(body.new_email)}. "
                                    "Open it and enter your password to finish.")


@router.delete("/change-email", status_code=204, dependencies=CLIENT, responses=SESSION_RESPONSES)
def cancel_email_change(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Cancels a pending change. Safe to repeat."""
    account_service.cancel_email_change(db, user)
    return Response(status_code=204)


@router.post("/confirm-email", status_code=204, dependencies=CLIENT,
             responses={**BAD_EMAIL_LINK, **TAKEN,
                        401: err("INVALID_CREDENTIALS (`fields.current_password`): wrong password."),
                        403: err("Missing the X-Taskroom-Client: web header.")})
def confirm_email(body: ConfirmEmailRequest, db: Session = Depends(get_db)):
    """No login needed (works on any device), but the account's password is. Sessions stay signed in."""
    account_service.confirm_email(db, body.token, body.current_password)
    return Response(status_code=204)


@router.post("/verify-email", status_code=204, dependencies=CLIENT, responses=BAD_EMAIL_LINK)
def verify_email(body: VerifyEmailRequest, db: Session = Depends(get_db)):
    """The link from the "Confirm your email" message. Works signed in or not."""
    account_service.verify_email(db, body.token)
    return Response(status_code=204)


@router.post("/verify-email/resend", status_code=202, response_model=AcceptedResponse, dependencies=CLIENT,
             responses=SESSION_RESPONSES)
def resend_verification(request: Request, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Send the confirmation email again (3 an hour). Already confirmed: nothing is sent."""
    account_service.resend_verification(db, user, request)
    return AcceptedResponse(message=f"We've sent a new link to {user.email}.")


@router.post("/cancel-email-change", status_code=204, dependencies=CLIENT,
             responses={**BAD_EMAIL_LINK, 403: err("Missing the X-Taskroom-Client: web header.")})
def cancel_email_change_by_link(body: CancelEmailChangeRequest, request: Request, db: Session = Depends(get_db)):
    """The "this wasn't me" link from the notice sent to the old address. No login needed."""
    limiter.hit(f"cancel-email:ip:{client_ip(request)}", 100, HOUR)
    account_service.cancel_email_change_by_link(db, body.token)
    return Response(status_code=204)
