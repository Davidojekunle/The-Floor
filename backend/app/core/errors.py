"""One error format for the whole API (matches the frontend handoff doc):

    { "error": { "code": "FORBIDDEN", "message": "...", "fields": {...} } }

`fields` only appears on validation errors.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("taskroom")


class AppError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str = "", fields: dict[str, str] | None = None):
        self.message = message or self.code.replace("_", " ").capitalize()
        self.fields = fields
        super().__init__(self.message)


class Unauthenticated(AppError):
    status_code = 401
    code = "UNAUTHENTICATED"


class InvalidCredentials(Unauthenticated):
    """Wrong email or password on login (kept separate from an expired or missing token)."""

    code = "INVALID_CREDENTIALS"


class Forbidden(AppError):
    status_code = 403
    code = "FORBIDDEN"


class NotFound(AppError):
    status_code = 404
    code = "NOT_FOUND"


class Conflict(AppError):
    status_code = 409
    code = "CONFLICT"


class InvalidTransition(Conflict):
    code = "INVALID_TRANSITION"


class LaterStagesStarted(Conflict):
    code = "LATER_STAGES_STARTED"


class LastStage(Conflict):
    code = "LAST_STAGE"


class AlreadyMember(Conflict):
    code = "ALREADY_MEMBER"


class AlreadyRequested(Conflict):
    code = "ALREADY_REQUESTED"


class RequestNotPending(Conflict):
    code = "REQUEST_NOT_PENDING"


class MemberNotActive(Conflict):
    code = "MEMBER_NOT_ACTIVE"


class TaskNotApproved(Conflict):
    code = "TASK_NOT_APPROVED"


class AlreadyApproved(Conflict):
    code = "ALREADY_APPROVED"


class NotNudgeable(Conflict):
    code = "NOT_NUDGEABLE"


class AlreadyNudged(Conflict):
    code = "ALREADY_NUDGED"


class NobodyOnStage(Conflict):
    code = "NOBODY_ON_STAGE"


class RateLimited(AppError):
    status_code = 429
    code = "RATE_LIMITED"

    def __init__(self, retry_after: int, message: str = "Too many attempts. Please wait and try again."):
        super().__init__(message)
        self.headers = {"Retry-After": str(max(1, int(retry_after)))}


class ResetTokenInvalid(AppError):
    status_code = 400
    code = "RESET_TOKEN_INVALID"


class EmailTokenInvalid(AppError):
    status_code = 400
    code = "EMAIL_TOKEN_INVALID"


class HeadMustTransfer(Conflict):
    code = "HEAD_MUST_TRANSFER"


class AlreadyHead(Conflict):
    code = "ALREADY_HEAD"


class ValidationFailed(AppError):
    status_code = 422
    code = "VALIDATION_ERROR"


_HTTP_CODES = {
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
}


def _body(code: str, message: str, fields: dict[str, str] | None = None) -> dict:
    error: dict = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return {"error": error}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(exc.code, exc.message, exc.fields),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        fields: dict[str, str] = {}
        for err in exc.errors():
            # loc looks like ("body", "email"); drop the "body"/"query" prefix
            path = ".".join(str(p) for p in err["loc"][1:]) or str(err["loc"][0])
            fields[path] = err["msg"].removeprefix("Value error, ")
        return JSONResponse(
            status_code=422,
            content=_body("VALIDATION_ERROR", "Some fields are invalid.", fields),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException):
        code = _HTTP_CODES.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content=_body(code, str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        from sqlalchemy.exc import TimeoutError as PoolTimeout

        if isinstance(exc, PoolTimeout):  # every database connection is busy: a crowd, not a bug
            logger.warning("Database pool exhausted on %s %s", request.method, request.url.path)
            return JSONResponse(
                status_code=503,
                content=_body("SERVER_BUSY", "The Floor is busy right now. Try again in a few seconds."),
                headers={"Retry-After": "5"},
            )
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=_body("SERVER_ERROR", "Something went wrong."),
        )
