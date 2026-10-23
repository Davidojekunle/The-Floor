import uuid

from tests.conftest import (
    approve, auth_headers, create_room, join_and_approve, reject, request_join, user_id_of,
)

API = "/api/v1"


def two_users(client):
    head = auth_headers(client, email="head@example.com", name="Head")
    other = auth_headers(client, email="other@example.com", name="Other")
    return head, other


# ---------- create + read ----------

def test_create_room_makes_creator_head(client):
    h = auth_headers(client)
    room = create_room(client, h, "  Studio Alpha  ")
    assert room["name"] == "Studio Alpha"
    assert room["my_role"] == "head"
    assert room["member_count"] == 1
    assert room["invite_code"]
    assert "join.manage" in room["permissions"]
    assert room["temp_head_expires_at"] is None


def test_create_room_requires_login(client):
    assert client.post(f"{API}/rooms", json={"name": "X"}).status_code == 401


def test_create_room_rejects_blank_name(client):
    h = auth_headers(client)
    r = client.post(f"{API}/rooms", json={"name": "   "}, headers=h)
    assert r.status_code == 422
    assert "name" in r.json()["error"]["fields"]


def test_list_rooms_only_mine_and_paginated(client):
    head, other = two_users(client)
    create_room(client, head, "A")
    create_room(client, head, "B")
    create_room(client, other, "Not mine")

    r = client.get(f"{API}/rooms", headers=head)
    body = r.json()
    assert body["total"] == 2
    assert [x["name"] for x in body["items"]] == ["A", "B"]

    r = client.get(f"{API}/rooms?limit=1&page=2", headers=head)
    assert [x["name"] for x in r.json()["items"]] == ["B"]


def test_get_room_as_member_hides_invite_and_limits_permissions(client):
    head, other = two_users(client)
    room = create_room(client, head)
    join_and_approve(client, room, head, other)

    r = client.get(f"{API}/rooms/{room['id']}", headers=other)
    assert r.status_code == 200
    body = r.json()
    assert body["my_role"] == "member"
    assert body["invite_code"] is None
    assert body["member_count"] == 2
    assert sorted(body["permissions"]) == ["chat.send", "task.propose"]


# ---------- 404 for everyone who isn't an active member ----------

def test_non_member_gets_404_identical_to_missing_room(client):
    head, other = two_users(client)
    room = create_room(client, head)

    real = client.get(f"{API}/rooms/{room['id']}", headers=other)
    fake = client.get(f"{API}/rooms/{uuid.uuid4()}", headers=other)
    assert real.status_code == 404
    assert real.json() == fake.json()  # room existence is not leaked


def test_pending_member_cannot_see_room(client):
    head, other = two_users(client)
    room = create_room(client, head)
    request_join(client, other, room["invite_code"])
    assert client.get(f"{API}/rooms/{room['id']}", headers=other).status_code == 404


# ---------- join via invite link ----------

def test_join_preview(client):
    head, other = two_users(client)
    room = create_room(client, head, "Studio Alpha")

    r = client.get(f"{API}/join/{room['invite_code']}", headers=other)
    assert r.status_code == 200
    assert r.json() == {
        "room_name": "Studio Alpha", "member_count": 1, "already_requested": False, "already_member": False,
        "invited": False,
    }


def test_join_preview_requires_login_and_valid_code(client):
    head, other = two_users(client)
    room = create_room(client, head)
    assert client.get(f"{API}/join/{room['invite_code']}").status_code == 401
    assert client.get(f"{API}/join/nope", headers=other).status_code == 404


def test_request_join_creates_pending_and_preview_reflects_it(client):
    head, other = two_users(client)
    room = create_room(client, head)

    r = request_join(client, other, room["invite_code"])
    assert r.status_code == 201
    assert r.json()["status"] == "pending"
    assert r.json()["room_id"] == room["id"]

    preview = client.get(f"{API}/join/{room['invite_code']}", headers=other).json()
    assert preview["already_requested"] is True
    assert preview["member_count"] == 1  # pending doesn't count


def test_duplicate_request_and_already_member_are_409(client):
    head, other = two_users(client)
    room = create_room(client, head)

    assert request_join(client, other, room["invite_code"]).status_code == 201
    dup = request_join(client, other, room["invite_code"])
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "ALREADY_REQUESTED"

    already = request_join(client, head, room["invite_code"])  # head is already in
    assert already.status_code == 409 and already.json()["error"]["code"] == "ALREADY_MEMBER"


def test_bad_invite_code_is_404(client):
    _, other = two_users(client)
    assert request_join(client, other, "nope").status_code == 404


def test_regenerate_invite_invalidates_old_link(client):
    head, other = two_users(client)
    room = create_room(client, head)
    old = room["invite_code"]

    r = client.post(f"{API}/rooms/{room['id']}/invite/regenerate", headers=head)
    assert r.status_code == 200
    new = r.json()["invite_code"]
    assert new != old

    assert request_join(client, other, old).status_code == 404
    assert request_join(client, other, new).status_code == 201


def test_member_cannot_regenerate_invite(client):
    head, other = two_users(client)
    room = create_room(client, head)
    join_and_approve(client, room, head, other)
    r = client.post(f"{API}/rooms/{room['id']}/invite/regenerate", headers=other)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "FORBIDDEN"


# ---------- join request management ----------

def test_head_lists_pending_requests(client):
    head, other = two_users(client)
    room = create_room(client, head)
    request_join(client, other, room["invite_code"])

    r = client.get(f"{API}/rooms/{room['id']}/join-requests", headers=head)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["user"]["name"] == "Other"
    assert item["user"]["id"] == user_id_of(client, other)
    assert "membership_id" in item and "requested_at" in item


def test_member_cannot_list_or_decide_requests(client):
    head, other = two_users(client)
    third = auth_headers(client, email="third@example.com", name="Third")
    room = create_room(client, head)
    join_and_approve(client, room, head, other)
    mid = request_join(client, third, room["invite_code"]).json()["membership_id"]

    assert client.get(f"{API}/rooms/{room['id']}/join-requests", headers=other).status_code == 403
    assert approve(client, room["id"], mid, other).status_code == 403
    assert reject(client, room["id"], mid, other).status_code == 403


def test_approve_gives_access_and_appears_in_me(client):
    head, other = two_users(client)
    room = create_room(client, head)
    mid = request_join(client, other, room["invite_code"]).json()["membership_id"]

    a = approve(client, room["id"], mid, head)
    assert a.status_code == 200 and a.json()["status"] == "active"

    assert client.get(f"{API}/rooms/{room['id']}", headers=other).status_code == 200
    rooms = client.get(f"{API}/me", headers=other).json()["rooms"]
    assert [(x["name"], x["my_role"]) for x in rooms] == [("Studio Alpha", "member")]


def test_approve_is_idempotent(client):
    head, other = two_users(client)
    room = create_room(client, head)
    mid = request_join(client, other, room["invite_code"]).json()["membership_id"]
    assert approve(client, room["id"], mid, head).status_code == 200
    again = approve(client, room["id"], mid, head)
    assert again.status_code == 200 and again.json()["status"] == "active"


def test_reject_blocks_access_and_allows_asking_again(client):
    head, other = two_users(client)
    room = create_room(client, head)
    mid = request_join(client, other, room["invite_code"]).json()["membership_id"]

    r = reject(client, room["id"], mid, head)
    assert r.status_code == 200 and r.json()["status"] == "rejected"
    assert reject(client, room["id"], mid, head).status_code == 200  # idempotent
    assert client.get(f"{API}/rooms/{room['id']}", headers=other).status_code == 404

    again = request_join(client, other, room["invite_code"])
    assert again.status_code == 201 and again.json()["status"] == "pending"
    assert again.json()["membership_id"] == mid  # same row, no duplicates


def test_cannot_reject_someone_already_approved(client):
    head, other = two_users(client)
    room = create_room(client, head)
    mid = join_and_approve(client, room, head, other)
    r = reject(client, room["id"], mid, head)
    assert r.status_code == 409 and r.json()["error"]["code"] == "REQUEST_NOT_PENDING"


def test_unknown_membership_is_404(client):
    head, _ = two_users(client)
    room = create_room(client, head)
    assert approve(client, room["id"], str(uuid.uuid4()), head).status_code == 404


def test_pending_count_on_me_for_head_only(client):
    head, other = two_users(client)
    third = auth_headers(client, email="third@example.com", name="Third")
    room = create_room(client, head)
    join_and_approve(client, room, head, other)
    request_join(client, third, room["invite_code"])

    head_rooms = client.get(f"{API}/me", headers=head).json()["rooms"]
    other_rooms = client.get(f"{API}/me", headers=other).json()["rooms"]
    assert head_rooms[0]["pending_count"] == 1
    assert other_rooms[0]["pending_count"] == 0
