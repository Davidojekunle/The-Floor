import uuid
from datetime import timedelta

from app.models.room import TempHead
from app.utils.time import utcnow
from tests.conftest import (
    auth_headers, create_room, create_tag, join_and_approve, members_of, membership_id_for,
    request_join, user_id_of,
)

API = "/api/v1"


def setup(client):
    """head + two members (Bola, Ada) in one room."""
    head = auth_headers(client, email="head@example.com", name="Head")
    bola = auth_headers(client, email="bola@example.com", name="Bola")
    ada = auth_headers(client, email="ada@example.com", name="ada")  # lowercase on purpose
    room = create_room(client, head)
    join_and_approve(client, room, head, bola)
    join_and_approve(client, room, head, ada)
    return head, bola, ada, room


def patch_tags(client, room_id, membership_id, tag_ids, headers):
    return client.patch(
        f"{API}/rooms/{room_id}/members/{membership_id}", json={"tag_ids": tag_ids}, headers=headers
    )


# ---------- list ----------

def test_list_members_head_first_then_by_name_case_insensitive(client):
    head, bola, ada, room = setup(client)
    body = members_of(client, room["id"], bola)  # a plain member can see the list
    assert [m["user"]["name"] for m in body["items"]] == ["Head", "ada", "Bola"]
    assert [m["role"] for m in body["items"]] == ["head", "member", "member"]
    assert body["total"] == 3


def test_list_excludes_pending_and_non_active(client):
    head, bola, ada, room = setup(client)
    pending = auth_headers(client, email="pending@example.com", name="Pending")
    request_join(client, pending, room["invite_code"])
    assert members_of(client, room["id"], head)["total"] == 3


def test_list_is_paginated(client):
    head, bola, ada, room = setup(client)
    body = members_of(client, room["id"], head, limit=2, page=2)
    assert [m["user"]["name"] for m in body["items"]] == ["Bola"]
    assert body["total"] == 3


def test_non_member_gets_404(client):
    head, bola, ada, room = setup(client)
    stranger = auth_headers(client, email="stranger@example.com", name="Stranger")
    assert client.get(f"{API}/rooms/{room['id']}/members", headers=stranger).status_code == 404


def test_active_temp_head_shows_as_temp_head(client, db):
    head, bola, ada, room = setup(client)
    db.add(
        TempHead(
            room_id=uuid.UUID(room["id"]),
            user_id=uuid.UUID(user_id_of(client, bola)),
            granted_by=uuid.UUID(user_id_of(client, head)),
            expires_at=utcnow() + timedelta(hours=1),
        )
    )
    db.commit()
    roles = {m["user"]["name"]: m["role"] for m in members_of(client, room["id"], head)["items"]}
    assert roles == {"Head": "head", "ada": "member", "Bola": "temp_head"}


# ---------- assign tags ----------

def test_head_sets_multiple_tags_and_replaces_them(client):
    head, bola, ada, room = setup(client)
    editor = create_tag(client, room["id"], head, "Editor")
    writer = create_tag(client, room["id"], head, "Writer")
    mid = membership_id_for(client, room["id"], head, user_id_of(client, bola))

    r = patch_tags(client, room["id"], mid, [editor["id"], writer["id"]], head)
    assert r.status_code == 200
    assert [t["name"] for t in r.json()["tags"]] == ["Editor", "Writer"]

    r = patch_tags(client, room["id"], mid, [writer["id"]], head)  # replaces, not adds
    assert [t["name"] for t in r.json()["tags"]] == ["Writer"]

    r = patch_tags(client, room["id"], mid, [], head)  # clears
    assert r.json()["tags"] == []


def test_duplicate_ids_in_request_are_fine(client):
    head, bola, ada, room = setup(client)
    editor = create_tag(client, room["id"], head, "Editor")
    mid = membership_id_for(client, room["id"], head, user_id_of(client, bola))
    r = patch_tags(client, room["id"], mid, [editor["id"], editor["id"]], head)
    assert r.status_code == 200 and len(r.json()["tags"]) == 1


def test_tags_show_in_list_and_counts_update(client):
    head, bola, ada, room = setup(client)
    editor = create_tag(client, room["id"], head, "Editor")
    for h in (bola, ada):
        mid = membership_id_for(client, room["id"], head, user_id_of(client, h))
        patch_tags(client, room["id"], mid, [editor["id"]], head)

    tags = client.get(f"{API}/rooms/{room['id']}/tags", headers=head).json()["items"]
    assert tags[0]["member_count"] == 2
    listed = {m["user"]["name"]: [t["name"] for t in m["tags"]] for m in members_of(client, room["id"], head)["items"]}
    assert listed == {"Head": [], "ada": ["Editor"], "Bola": ["Editor"]}


def test_filter_members_by_tag(client):
    head, bola, ada, room = setup(client)
    editor = create_tag(client, room["id"], head, "Editor")
    mid = membership_id_for(client, room["id"], head, user_id_of(client, bola))
    patch_tags(client, room["id"], mid, [editor["id"]], head)

    body = members_of(client, room["id"], head, tag=editor["id"])
    assert [m["user"]["name"] for m in body["items"]] == ["Bola"]
    assert body["total"] == 1

    r = client.get(f"{API}/rooms/{room['id']}/members", params={"tag": str(uuid.uuid4())}, headers=head)
    assert r.status_code == 404


def test_tag_from_another_room_is_rejected_as_422(client):
    head, bola, ada, room = setup(client)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    foreign = create_tag(client, other_room["id"], other_head, "Foreign")
    mid = membership_id_for(client, room["id"], head, user_id_of(client, bola))

    r = patch_tags(client, room["id"], mid, [foreign["id"]], head)
    assert r.status_code == 422
    assert "tag_ids" in r.json()["error"]["fields"]
    assert members_of(client, room["id"], head)["items"][2]["tags"] == []  # nothing was applied


def test_unknown_tag_is_422(client):
    head, bola, ada, room = setup(client)
    mid = membership_id_for(client, room["id"], head, user_id_of(client, bola))
    assert patch_tags(client, room["id"], mid, [str(uuid.uuid4())], head).status_code == 422


def test_member_cannot_assign_tags_not_even_to_themselves(client):
    head, bola, ada, room = setup(client)
    editor = create_tag(client, room["id"], head, "Editor")
    mid = membership_id_for(client, room["id"], head, user_id_of(client, bola))
    assert patch_tags(client, room["id"], mid, [editor["id"]], bola).status_code == 403


def test_cannot_tag_a_pending_member_or_one_from_another_room(client):
    head, bola, ada, room = setup(client)
    editor = create_tag(client, room["id"], head, "Editor")
    pending = auth_headers(client, email="pending@example.com", name="Pending")
    pending_mid = request_join(client, pending, room["invite_code"]).json()["membership_id"]
    assert patch_tags(client, room["id"], pending_mid, [editor["id"]], head).status_code == 404

    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    other_mid = membership_id_for(client, other_room["id"], other_head, user_id_of(client, other_head))
    assert patch_tags(client, room["id"], other_mid, [editor["id"]], head).status_code == 404


# ---------- remove ----------

def test_head_removes_member(client):
    head, bola, ada, room = setup(client)
    editor = create_tag(client, room["id"], head, "Editor")
    mid = membership_id_for(client, room["id"], head, user_id_of(client, bola))
    patch_tags(client, room["id"], mid, [editor["id"]], head)

    assert client.delete(f"{API}/rooms/{room['id']}/members/{mid}", headers=head).status_code == 204

    assert client.get(f"{API}/rooms/{room['id']}", headers=bola).status_code == 404  # lost access
    assert client.get(f"{API}/me", headers=bola).json()["rooms"] == []
    assert "Bola" not in [m["user"]["name"] for m in members_of(client, room["id"], head)["items"]]
    assert client.get(f"{API}/rooms/{room['id']}/tags", headers=head).json()["items"][0]["member_count"] == 0


def test_removed_member_can_ask_again_but_starts_clean(client):
    head, bola, ada, room = setup(client)
    editor = create_tag(client, room["id"], head, "Editor")
    mid = membership_id_for(client, room["id"], head, user_id_of(client, bola))
    patch_tags(client, room["id"], mid, [editor["id"]], head)
    client.delete(f"{API}/rooms/{room['id']}/members/{mid}", headers=head)

    assert request_join(client, bola, room["invite_code"]).status_code == 201
    join_and_approve_again = client.post(
        f"{API}/rooms/{room['id']}/join-requests/{mid}/approve", headers=head
    )
    assert join_and_approve_again.status_code == 200
    back = next(m for m in members_of(client, room["id"], head)["items"] if m["user"]["name"] == "Bola")
    assert back["tags"] == []  # old tags did not come back


def test_removal_revokes_temp_head_so_it_cannot_resurrect(client, db):
    head, bola, ada, room = setup(client)
    db.add(
        TempHead(
            room_id=uuid.UUID(room["id"]),
            user_id=uuid.UUID(user_id_of(client, bola)),
            granted_by=uuid.UUID(user_id_of(client, head)),
            expires_at=utcnow() + timedelta(days=7),
        )
    )
    db.commit()
    mid = membership_id_for(client, room["id"], head, user_id_of(client, bola))
    client.delete(f"{API}/rooms/{room['id']}/members/{mid}", headers=head)

    request_join(client, bola, room["invite_code"])
    client.post(f"{API}/rooms/{room['id']}/join-requests/{mid}/approve", headers=head)
    assert client.get(f"{API}/rooms/{room['id']}", headers=bola).json()["my_role"] == "member"


def test_cannot_remove_the_head_even_as_head(client):
    head, bola, ada, room = setup(client)
    head_mid = membership_id_for(client, room["id"], head, user_id_of(client, head))
    r = client.delete(f"{API}/rooms/{room['id']}/members/{head_mid}", headers=head)
    assert r.status_code == 403
    assert members_of(client, room["id"], head)["total"] == 3


def test_member_and_temp_head_cannot_remove(client, db):
    head, bola, ada, room = setup(client)
    db.add(
        TempHead(
            room_id=uuid.UUID(room["id"]),
            user_id=uuid.UUID(user_id_of(client, bola)),
            granted_by=uuid.UUID(user_id_of(client, head)),
            expires_at=utcnow() + timedelta(hours=1),
        )
    )
    db.commit()
    ada_mid = membership_id_for(client, room["id"], head, user_id_of(client, ada))
    assert client.delete(f"{API}/rooms/{room['id']}/members/{ada_mid}", headers=bola).status_code == 403  # temp head
    bola_mid = membership_id_for(client, room["id"], head, user_id_of(client, bola))
    assert client.delete(f"{API}/rooms/{room['id']}/members/{bola_mid}", headers=ada).status_code == 403  # member


def test_remove_is_idempotent_and_rejects_pending(client):
    head, bola, ada, room = setup(client)
    mid = membership_id_for(client, room["id"], head, user_id_of(client, bola))
    assert client.delete(f"{API}/rooms/{room['id']}/members/{mid}", headers=head).status_code == 204
    assert client.delete(f"{API}/rooms/{room['id']}/members/{mid}", headers=head).status_code == 204

    pending = auth_headers(client, email="pending@example.com", name="Pending")
    pending_mid = request_join(client, pending, room["invite_code"]).json()["membership_id"]
    r = client.delete(f"{API}/rooms/{room['id']}/members/{pending_mid}", headers=head)
    assert r.status_code == 409 and r.json()["error"]["code"] == "MEMBER_NOT_ACTIVE"


def test_unknown_or_foreign_membership_is_404(client):
    head, bola, ada, room = setup(client)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    foreign = membership_id_for(client, other_room["id"], other_head, user_id_of(client, other_head))
    assert client.delete(f"{API}/rooms/{room['id']}/members/{uuid.uuid4()}", headers=head).status_code == 404
    assert client.delete(f"{API}/rooms/{room['id']}/members/{foreign}", headers=head).status_code == 404
