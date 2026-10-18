from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str  # UNAUTHENTICATED, INVALID_CREDENTIALS, FORBIDDEN, NOT_FOUND, CONFLICT, VALIDATION_ERROR, SERVER_ERROR, ...
    message: str
    fields: dict[str, str] | None = None  # only on validation errors (and duplicate email on register)


class ErrorResponse(BaseModel):
    error: ErrorBody
