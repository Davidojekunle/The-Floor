"""Unit tests for the permission matrix (spec section 5). No HTTP, no DB."""
import pytest

from app.models.enums import Role
from app.permissions.rules import ALL_PERMISSIONS, RoomContext, can, permissions_for_role, require
from app.core.errors import Forbidden


def ctx_for(role: str) -> RoomContext:
    return RoomContext(room=None, membership=None, role=role, permissions=permissions_for_role(role))


# permission -> (head, temp_head, member)
MATRIX = {
    "join.manage":         (True,  False, False),
    "tag.manage":          (True,  False, False),
    "task.create":         (True,  True,  False),
    "task.propose":        (True,  True,  True),
    "task.approve":        (True,  True,  False),
    "stage.edit":          (True,  True,  False),
    "stage.override_lock": (True,  True,  False),
    "tempHead.manage":     (True,  False, False),
    "member.remove":       (True,  False, False),
    "room.delete":         (True,  False, False),
    "invite.manage":       (True,  False, False),
    "chat.send":           (True,  True,  True),
    "chat.delete_any":     (True,  True,  False),
}


def test_matrix_covers_every_permission():
    assert set(MATRIX) == set(ALL_PERMISSIONS)


@pytest.mark.parametrize("permission", sorted(MATRIX))
@pytest.mark.parametrize("role_index,role", [(0, Role.HEAD), (1, Role.TEMP_HEAD), (2, Role.MEMBER)])
def test_permission_matrix(permission, role_index, role):
    assert can(ctx_for(role), permission) is MATRIX[permission][role_index]


def test_unknown_permission_raises_instead_of_silently_denying():
    with pytest.raises(ValueError):
        can(ctx_for(Role.HEAD), "task.creat")  # typo


def test_require_raises_forbidden():
    with pytest.raises(Forbidden):
        require(ctx_for(Role.MEMBER), "join.manage")
    require(ctx_for(Role.HEAD), "join.manage")  # does not raise
