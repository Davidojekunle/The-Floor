"""OpenAPI settings: stable operation names and a documented error shape."""
from fastapi.routing import APIRoute

from app.schemas.errors import ErrorResponse


def operation_id(route: APIRoute) -> str:
    """create_room -> createRoom. Clean names make generated API clients readable."""
    head, *rest = route.name.split("_")
    return head + "".join(word.title() for word in rest)


def err(description: str) -> dict:
    return {"model": ErrorResponse, "description": description}


# Applied to every route (see main.py)
GLOBAL_RESPONSES = {
    422: err("Validation error. `fields` maps each invalid field to a message."),
    500: err("Unexpected server error."),
}

# Applied to routes that need a logged-in user (see api/v1/router.py)
AUTHED_RESPONSES = {
    401: err("Missing, invalid, or expired token."),
    403: err("Member of the room, but not allowed to do this."),
    404: err("Not found, or the caller is not an active member of the room."),
    409: err(
        "Conflicts with the current state. Match on `code`: INVALID_TRANSITION, LATER_STAGES_STARTED, "
        "LAST_STAGE, TASK_NOT_APPROVED, ALREADY_APPROVED, ALREADY_HEAD, ALREADY_MEMBER, ALREADY_REQUESTED, "
        "REQUEST_NOT_PENDING, MEMBER_NOT_ACTIVE, "
        "or CONFLICT (duplicate name)."
    ),
}

# Precise, per-route declarations for the auth endpoints
REGISTER_RESPONSES = {409: err("Email already registered. `fields.email` is set.")}
LOGIN_RESPONSES = {401: err("INVALID_CREDENTIALS: wrong email or password.")}
ME_RESPONSES = {401: err("Missing, invalid, or expired token.")}
MY_TASKS_RESPONSES = {
    401: err("Missing, invalid, or expired token."),
    404: err("`room` was given, but you're not an active member of it."),
}
