"""One user, many rooms, a different role in each. Plus tenant isolation and temp head."""
import uuid
from datetime import timedelta

from app.models.room import TempHead
from app.utils.time import utcnow
from tests.conftest import approve, auth_headers, create_room, join_and_approve, request_join, user_id_of

API = "/api/v1"


def setup_two_rooms(client):
    """ada is head of A and a plain member of B (head of B is bola)."""
    ada = auth_headers(client, email="ada@example.com", name="Ada")
    bola = auth_headers(client, email="bola@example.com", name="Bola")
    room_a = create_room(client, ada, "Room A")
    room_b = create_room(client, bola, "Room B")
    join_and_approve(client, room_b, bola, ada)
    return ada, bola, room_a, room_b


def test_same_user_has_different_roles_per_room(client):
    ada, bola, room_a, room_b = setup_two_rooms(client)

    rooms = {r["name"]: r["my_role"] for r in client.get(f"{API}/me", headers=ada).json()["rooms"]}
    assert rooms == {"Room A": "head", "Room B": "member"}

    a = client.get(f"{API}/rooms/{room_a['id']}", headers=ada).json()
    b = client.get(f"{API}/rooms/{room_b['id']}", headers=ada).json()
    assert "join.manage" in a["permissions"]
    assert "join.manage" not in b["permissions"]


def test_head_powers_do_not_leak_across_rooms(client):
    ada, bola, room_a, room_b = setup_two_rooms(client)
    assert client.post(f"{API}/rooms/{room_a['id']}/invite/regenerate", headers=ada).status_code == 200
    assert client.post(f"{API}/rooms/{room_b['id']}/invite/regenerate", headers=ada).status_code == 403


def test_membership_id_from_another_room_is_not_found(client):
    """Tenant isolation: head of B can't act on a join request that belongs to room A."""
    ada, bola, room_a, room_b = setup_two_rooms(client)
    carol = auth_headers(client, email="carol@example.com", name="Carol")
    mid_in_a = request_join(client, carol, room_a["invite_code"]).json()["membership_id"]

    assert approve(client, room_b["id"], mid_in_a, bola).status_code == 404
    assert approve(client, room_a["id"], mid_in_a, ada).status_code == 200  # the real head can


def test_leaving_one_room_state_does_not_affect_others(client):
    ada, bola, room_a, room_b = setup_two_rooms(client)
    # a rejected request in a third room changes nothing about A and B
    dan = auth_headers(client, email="dan@example.com", name="Dan")
    room_c = create_room(client, dan, "Room C")
    mid = request_join(client, ada, room_c["invite_code"]).json()["membership_id"]
    client.post(f"{API}/rooms/{room_c['id']}/join-requests/{mid}/reject", headers=dan)

    names = sorted(r["name"] for r in client.get(f"{API}/me", headers=ada).json()["rooms"])
    assert names == ["Room A", "Room B"]


# ---------- temp head (resolved from the DB at request time) ----------

def grant_temp_head(db, room_id, user_id, granted_by, *, expires_in=timedelta(hours=1), revoked=False):
    db.add(
        TempHead(
            room_id=uuid.UUID(room_id),
            user_id=uuid.UUID(user_id),
            granted_by=uuid.UUID(granted_by),
            expires_at=utcnow() + expires_in,
            revoked_at=utcnow() if revoked else None,
        )
    )
    db.commit()


def test_active_temp_head_gets_task_powers_only(client, db):
    ada, bola, room_a, room_b = setup_two_rooms(client)
    # bola (head of B) makes ada temp head in B
    grant_temp_head(db, room_b["id"], user_id_of(client, ada), user_id_of(client, bola))

    body = client.get(f"{API}/rooms/{room_b['id']}", headers=ada).json()
    assert body["my_role"] == "temp_head"
    assert body["temp_head_expires_at"] is not None
    assert "task.approve" in body["permissions"]
    assert "join.manage" not in body["permissions"]
    assert body["invite_code"] is None

    # shows up in the switcher, and join management is still denied
    rooms = {r["name"]: r["my_role"] for r in client.get(f"{API}/me", headers=ada).json()["rooms"]}
    assert rooms["Room B"] == "temp_head"
    assert client.get(f"{API}/rooms/{room_b['id']}/join-requests", headers=ada).status_code == 403


def test_temp_head_in_one_room_does_not_apply_to_another(client, db):
    ada, bola, room_a, room_b = setup_two_rooms(client)
    # give ada temp head in B and make sure room A is untouched
    grant_temp_head(db, room_b["id"], user_id_of(client, ada), user_id_of(client, bola))
    a = client.get(f"{API}/rooms/{room_a['id']}", headers=ada).json()
    assert a["my_role"] == "head" and a["temp_head_expires_at"] is None


def test_expired_temp_head_lapses_automatically(client, db):
    ada, bola, room_a, room_b = setup_two_rooms(client)
    grant_temp_head(
        db, room_b["id"], user_id_of(client, ada), user_id_of(client, bola), expires_in=timedelta(seconds=-5)
    )
    body = client.get(f"{API}/rooms/{room_b['id']}", headers=ada).json()
    assert body["my_role"] == "member"
    assert body["temp_head_expires_at"] is None


def test_revoked_temp_head_is_ignored(client, db):
    ada, bola, room_a, room_b = setup_two_rooms(client)
    grant_temp_head(db, room_b["id"], user_id_of(client, ada), user_id_of(client, bola), revoked=True)
    assert client.get(f"{API}/rooms/{room_b['id']}", headers=ada).json()["my_role"] == "member"
