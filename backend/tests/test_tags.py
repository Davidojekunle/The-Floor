import uuid

from tests.conftest import auth_headers, create_room, create_tag, join_and_approve

API = "/api/v1"


def setup(client):
    head = auth_headers(client, email="head@example.com", name="Head")
    member = auth_headers(client, email="member@example.com", name="Member")
    room = create_room(client, head)
    join_and_approve(client, room, head, member)
    return head, member, room


# ---------- create ----------

def test_head_creates_tag_and_name_is_cleaned(client):
    head, _, room = setup(client)
    tag = create_tag(client, room["id"], head, "  Video   Editor ")
    assert tag["name"] == "Video Editor"
    assert tag["member_count"] == 0


def test_duplicate_name_is_409_ignoring_case(client):
    head, _, room = setup(client)
    create_tag(client, room["id"], head, "Video Editor")
    r = client.post(f"{API}/rooms/{room['id']}/tags", json={"name": "video editor"}, headers=head)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_same_tag_name_allowed_in_different_rooms(client):
    head, _, room = setup(client)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    create_tag(client, room["id"], head, "Designer")
    create_tag(client, other_room["id"], other_head, "Designer")  # no clash across rooms


def test_blank_and_too_long_names_are_422(client):
    head, _, room = setup(client)
    for name in ("   ", "x" * 51):
        r = client.post(f"{API}/rooms/{room['id']}/tags", json={"name": name}, headers=head)
        assert r.status_code == 422
        assert "name" in r.json()["error"]["fields"]


def test_member_cannot_create_rename_or_delete(client):
    head, member, room = setup(client)
    tag = create_tag(client, room["id"], head)
    base = f"{API}/rooms/{room['id']}/tags"
    assert client.post(base, json={"name": "X"}, headers=member).status_code == 403
    assert client.patch(f"{base}/{tag['id']}", json={"name": "X"}, headers=member).status_code == 403
    assert client.delete(f"{base}/{tag['id']}", headers=member).status_code == 403


def test_non_member_gets_404_on_tags(client):
    head, _, room = setup(client)
    stranger = auth_headers(client, email="stranger@example.com", name="Stranger")
    assert client.get(f"{API}/rooms/{room['id']}/tags", headers=stranger).status_code == 404
    assert client.post(f"{API}/rooms/{room['id']}/tags", json={"name": "X"}, headers=stranger).status_code == 404


# ---------- list ----------

def test_members_can_list_tags_sorted_with_counts(client):
    head, member, room = setup(client)
    create_tag(client, room["id"], head, "writer")
    create_tag(client, room["id"], head, "Editor")
    create_tag(client, room["id"], head, "Camera")

    r = client.get(f"{API}/rooms/{room['id']}/tags", headers=member)
    assert r.status_code == 200
    body = r.json()
    assert [t["name"] for t in body["items"]] == ["Camera", "Editor", "writer"]  # case-insensitive order
    assert body["total"] == 3 and body["limit"] == 100  # dropdown-friendly default


def test_tags_are_isolated_per_room(client):
    head, _, room = setup(client)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    create_tag(client, other_room["id"], other_head, "Secret")

    assert client.get(f"{API}/rooms/{room['id']}/tags", headers=head).json()["items"] == []


# ---------- rename ----------

def test_rename_tag(client):
    head, _, room = setup(client)
    tag = create_tag(client, room["id"], head, "Editor")
    r = client.patch(f"{API}/rooms/{room['id']}/tags/{tag['id']}", json={"name": "Video Editor"}, headers=head)
    assert r.status_code == 200
    assert r.json()["name"] == "Video Editor"


def test_rename_changing_only_case_is_allowed(client):
    head, _, room = setup(client)
    tag = create_tag(client, room["id"], head, "editor")
    r = client.patch(f"{API}/rooms/{room['id']}/tags/{tag['id']}", json={"name": "Editor"}, headers=head)
    assert r.status_code == 200 and r.json()["name"] == "Editor"


def test_rename_to_existing_name_is_409(client):
    head, _, room = setup(client)
    create_tag(client, room["id"], head, "Editor")
    other = create_tag(client, room["id"], head, "Writer")
    r = client.patch(f"{API}/rooms/{room['id']}/tags/{other['id']}", json={"name": "EDITOR"}, headers=head)
    assert r.status_code == 409


def test_tag_from_another_room_is_404(client):
    head, _, room = setup(client)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    foreign = create_tag(client, other_room["id"], other_head, "Foreign")

    base = f"{API}/rooms/{room['id']}/tags/{foreign['id']}"
    assert client.patch(base, json={"name": "Hacked"}, headers=head).status_code == 404
    assert client.delete(base, headers=head).status_code == 404
    # and it was not touched
    assert client.get(f"{API}/rooms/{other_room['id']}/tags", headers=other_head).json()["items"][0]["name"] == "Foreign"


# ---------- delete ----------

def test_delete_tag_removes_it_from_members(client):
    head, member, room = setup(client)
    tag = create_tag(client, room["id"], head, "Editor")
    members = client.get(f"{API}/rooms/{room['id']}/members", headers=head).json()["items"]
    member_row = next(m for m in members if m["role"] == "member")
    client.patch(
        f"{API}/rooms/{room['id']}/members/{member_row['membership_id']}", json={"tag_ids": [tag["id"]]}, headers=head
    )

    assert client.delete(f"{API}/rooms/{room['id']}/tags/{tag['id']}", headers=head).status_code == 204

    members = client.get(f"{API}/rooms/{room['id']}/members", headers=head).json()["items"]
    assert all(m["tags"] == [] for m in members)
    assert client.get(f"{API}/rooms/{room['id']}/tags", headers=head).json()["total"] == 0


def test_delete_unknown_tag_is_404(client):
    head, _, room = setup(client)
    assert client.delete(f"{API}/rooms/{room['id']}/tags/{uuid.uuid4()}", headers=head).status_code == 404
