"""The ONE place that decides who can do what inside a room.

Routes and services never check `role == "head"`. They call `can()` / `require()`.
The same permission strings are sent to the frontend (RoomOut.permissions),
so the UI never has to re-implement these rules.
"""
from dataclasses import dataclass
from datetime import datetime

from app.core.errors import Forbidden
from app.models.enums import Role

ALL_PERMISSIONS = (
    "join.manage",
    "tag.manage",
    "task.create",
    "task.propose",
    "task.approve",
    "stage.edit",
    "stage.override_lock",
    "tempHead.manage",
    "member.remove",
    "room.delete",
    "head.transfer",
    "invite.manage",
    "chat.send",
    "chat.delete_any",
)

_MEMBER = frozenset({"task.propose", "chat.send"})

# Temp head = tasks and chat moderation only. No joins, tags, members, invite, or temp-head management.
_TEMP_HEAD = _MEMBER | frozenset(
    {"task.create", "task.approve", "stage.edit", "stage.override_lock", "chat.delete_any"}
)

_HEAD = frozenset(ALL_PERMISSIONS)

PERMISSIONS_BY_ROLE: dict[str, frozenset[str]] = {
    Role.HEAD: _HEAD,
    Role.TEMP_HEAD: _TEMP_HEAD,
    Role.MEMBER: _MEMBER,
}


def permissions_for_role(role: str) -> frozenset[str]:
    return PERMISSIONS_BY_ROLE[role]


def resolve_role(membership, temp_head) -> str:
    """head > temp_head (only if an active grant was passed in) > member."""
    if membership.role == Role.HEAD:
        return Role.HEAD
    if temp_head is not None:
        return Role.TEMP_HEAD
    return Role.MEMBER


@dataclass(frozen=True)
class RoomContext:
    """Everything a route needs to know about the caller inside one room."""

    room: object
    membership: object
    role: str
    permissions: frozenset
    temp_head_expires_at: datetime | None = None


def can(ctx: RoomContext, action: str) -> bool:
    if action not in ALL_PERMISSIONS:
        raise ValueError(f"Unknown permission: {action!r}")  # catches typos instead of silently denying
    return action in ctx.permissions


def require(ctx: RoomContext, action: str, message: str | None = None) -> None:
    if not can(ctx, action):
        raise Forbidden(message or "You don't have permission to do that in this room.")
