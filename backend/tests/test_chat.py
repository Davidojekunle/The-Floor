"""Phase 6a: room chat. make_team() already posts two system messages (Femi joined, Tola joined)."""
import uuid
from datetime import timedelta

from app.models.room import TempHead
from app.utils.time import utcnow
from tests.conftest import (
    auth_headers, create_room, create_task, make_team, membership_id_for, messages, post_task,
    request_join, send, unread,
)

API = "/api/v1"


def bodies(page):
    return [m["body"] for m in page["items"]]


def err(r, status, code=None):
    assert r.status_code == status, r.text
    if code:
        assert r.json()["error"]["code"] == code
    return r.json()["error"]


# =========================================================== send and read

def test_send_and_read_newest_first(client):
    team = make_team(client)
    r = send(client, team, team.tola, "  Footage is uploaded\nfolder 2  ")
    assert r.status_code == 201
    m = r.json()
    assert (m["type"], m["sender"]["name"], m["body"]) == ("user", "Tola", "Footage is uploaded\nfolder 2")
    assert (m["task"], m["stage"], m["event"], m["deleted"], m["can_delete"]) == (None, None, None, False, True)

    send(client, team, team.femi, "Nice")
    page = messages(client, team, team.femi)
    assert bodies(page)[:2] == ["Nice", "Footage is uploaded\nfolder 2"]
    assert page["has_more"] is False
    assert [x["can_delete"] for x in page["items"][:2]] == [True, False]  # Femi may delete only her own


def test_body_limits(client):
    team = make_team(client)
    for bad in ("", "   ", "x" * 4001):
        assert "body" in err(send(client, team, team.femi, bad), 422)["fields"]
    assert send(client, team, team.femi, "x" * 4000).status_code == 201


def test_only_active_members_can_read_or_post(client):
    team = make_team(client)
    stranger = auth_headers(client, email="stranger@example.com", name="Stranger")
    assert client.get(f"{API}/rooms/{team.room['id']}/messages", headers=stranger).status_code == 404
    assert send(client, team, stranger).status_code == 404

    kemi = auth_headers(client, email="kemi@example.com", name="Kemi")
    request_join(client, kemi, team.room["invite_code"])  # pending
    assert client.get(f"{API}/rooms/{team.room['id']}/messages", headers=kemi).status_code == 404

    mid = membership_id_for(client, team.room["id"], team.head, team.ids["tola"])
    client.delete(f"{API}/rooms/{team.room['id']}/members/{mid}", headers=team.head)
    assert client.get(f"{API}/rooms/{team.room['id']}/messages", headers=team.tola).status_code == 404  # removed: gone at once


# =========================================================== references

def test_reference_a_task_and_a_stage(client):
    team = make_team(client)
    task = create_task(client, team)
    m = send(client, team, team.tola, "On it", task_id=task["id"], stage_id=task["stages"][1]["id"]).json()
    assert (m["task"]["title"], m["stage"]["title"]) == ("Product promo video", "Shoot")

    only_stage = send(client, team, team.tola, "Stage only", stage_id=task["stages"][2]["id"]).json()
    assert (only_stage["task"]["id"], only_stage["stage"]["title"]) == (task["id"], "Edit")  # task filled in


def test_titles_are_live(client):
    team = make_team(client)
    task = create_task(client, team)
    send(client, team, team.tola, "About it", task_id=task["id"])
    client.patch(f"{API}/rooms/{team.room['id']}/tasks/{task['id']}", json={"title": "Promo v2"}, headers=team.head)
    assert messages(client, team)["items"][0]["task"]["title"] == "Promo v2"


def test_references_that_are_refused(client):
    team = make_team(client)
    one, two = create_task(client, team, title="One"), create_task(client, team, title="Two")
    proposal = post_task(client, team, team.femi).json()
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    theirs = client.post(f"{API}/rooms/{other_room['id']}/tasks", headers=other_head,
                         json={"title": "Theirs", "due_date": "2099-01-01T00:00:00Z", "stages": [{"title": "S"}]}).json()

    assert "task_id" in err(send(client, team, team.femi, "x", task_id=proposal["id"]), 422)["fields"]  # never reveal proposals
    assert "task_id" in err(send(client, team, team.femi, "x", task_id=theirs["id"]), 422)["fields"]
    assert "task_id" in err(send(client, team, team.femi, "x", task_id=str(uuid.uuid4())), 422)["fields"]
    assert "stage_id" in err(send(client, team, team.femi, "x", task_id=one["id"], stage_id=two["stages"][0]["id"]), 422)["fields"]
    assert "stage_id" in err(send(client, team, team.femi, "x", stage_id=proposal["stages"][0]["id"]), 422)["fields"]


def test_a_deleted_task_leaves_the_message_without_a_reference(client):
    team = make_team(client)
    task = create_task(client, team)
    send(client, team, team.tola, "About it", task_id=task["id"], stage_id=task["stages"][0]["id"])
    client.delete(f"{API}/rooms/{team.room['id']}/tasks/{task['id']}", headers=team.head)
    m = next(x for x in messages(client, team)["items"] if x["body"] == "About it")
    assert (m["task"], m["stage"]) == (None, None)


def test_task_filter(client):
    team = make_team(client)
    task = create_task(client, team)
    send(client, team, team.tola, "About it", task_id=task["id"])
    send(client, team, team.tola, "Unrelated")
    page = messages(client, team, task_id=task["id"])
    assert set(bodies(page)) == {"About it", "Ada created Product promo video"}  # includes its system message

    proposal = post_task(client, team, team.femi).json()
    r = client.get(f"{API}/rooms/{team.room['id']}/messages", params={"task_id": proposal["id"]}, headers=team.femi)
    assert r.status_code == 404


# =========================================================== delete

def test_delete_own_message_leaves_a_placeholder(client):
    team = make_team(client)
    m = send(client, team, team.tola, "Oops").json()
    url = f"{API}/rooms/{team.room['id']}/messages/{m['id']}"
    assert client.delete(url, headers=team.tola).status_code == 204
    gone = messages(client, team, team.tola)["items"][0]
    assert (gone["id"], gone["deleted"], gone["body"], gone["can_delete"]) == (m["id"], True, None, False)
    assert client.delete(url, headers=team.tola).status_code == 204  # again


def test_who_may_delete_what(client, db):
    team = make_team(client)
    m = send(client, team, team.tola, "Mine").json()
    url = f"{API}/rooms/{team.room['id']}/messages/{m['id']}"
    err(client.delete(url, headers=team.femi), 403, "FORBIDDEN")

    system = messages(client, team)["items"][-1]  # "Femi joined the room"
    assert system["type"] == "system" and system["can_delete"] is True  # head sees moderation rights
    err(client.delete(f"{API}/rooms/{team.room['id']}/messages/{system['id']}", headers=team.femi), 403)

    db.add(TempHead(room_id=uuid.UUID(team.room["id"]), user_id=uuid.UUID(team.ids["femi"]),
                    granted_by=uuid.UUID(team.ids["head"]), expires_at=utcnow() + timedelta(hours=1)))
    db.commit()
    assert client.delete(url, headers=team.femi).status_code == 204  # temp head moderates
    assert client.delete(f"{API}/rooms/{team.room['id']}/messages/{system['id']}", headers=team.head).status_code == 204


def test_delete_unknown_or_foreign_message_is_404(client):
    team = make_team(client)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    theirs = client.post(f"{API}/rooms/{other_room['id']}/messages", json={"body": "hi"}, headers=other_head).json()
    assert client.delete(f"{API}/rooms/{team.room['id']}/messages/{theirs['id']}", headers=team.head).status_code == 404
    assert client.delete(f"{API}/rooms/{team.room['id']}/messages/{uuid.uuid4()}", headers=team.head).status_code == 404


# =========================================================== paging

def seven(client, team):
    for i in range(1, 8):
        send(client, team, team.femi, f"m{i}")


def test_latest_page_then_before_until_the_start(client):
    team = make_team(client)
    seven(client, team)
    page = messages(client, team, limit=3)
    assert bodies(page) == ["m7", "m6", "m5"] and page["has_more"] is True

    page = messages(client, team, limit=3, before=page["items"][-1]["id"])
    assert bodies(page) == ["m4", "m3", "m2"] and page["has_more"] is True

    page = messages(client, team, limit=3, before=page["items"][-1]["id"])
    assert bodies(page) == ["m1", "Tola joined the room", "Femi joined the room"] and page["has_more"] is False


def test_after_returns_the_messages_immediately_after_the_cursor(client):
    team = make_team(client)
    send(client, team, team.femi, "start")
    start = messages(client, team, limit=1)["items"][0]["id"]
    seven(client, team)  # a burst bigger than the page

    page = messages(client, team, limit=3, after=start)
    assert bodies(page) == ["m3", "m2", "m1"] and page["has_more"] is True  # not the latest three


def test_polling_after_never_skips_a_message(client):
    team = make_team(client)
    send(client, team, team.femi, "start")
    newest = messages(client, team, limit=1)["items"][0]["id"]
    seven(client, team)

    seen = []
    while True:
        page = messages(client, team, limit=3, after=newest)
        seen += reversed(bodies(page))
        if page["items"]:
            newest = page["items"][0]["id"]
        if not page["has_more"]:
            break
    assert seen == [f"m{i}" for i in range(1, 8)]
    assert messages(client, team, after=newest) == {"items": [], "has_more": False, "last_read_message_id": None}


def test_paging_errors(client):
    team = make_team(client)
    a = send(client, team, team.femi, "a").json()["id"]
    r = client.get(f"{API}/rooms/{team.room['id']}/messages", params={"before": a, "after": a}, headers=team.head)
    assert r.status_code == 422
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    theirs = client.post(f"{API}/rooms/{other_room['id']}/messages", json={"body": "hi"}, headers=other_head).json()
    r = client.get(f"{API}/rooms/{team.room['id']}/messages", params={"after": theirs["id"]}, headers=team.head)
    assert "after" in err(r, 422)["fields"]
    r = client.get(f"{API}/rooms/{team.room['id']}/messages", params={"limit": 101}, headers=team.head)
    assert r.status_code == 422


# =========================================================== unread

def test_new_members_start_with_nothing_unread(client):
    team = make_team(client)
    assert unread(client, team.tola) == 0  # read position starts at her own "joined" message
    assert unread(client, team.femi) == 1  # Tola joined after Femi
    assert unread(client, team.head) == 0  # both joins were approved by the head (her own actions)


def test_unread_excludes_own_messages_and_own_actions(client):
    team = make_team(client)
    send(client, team, team.femi, "one")
    send(client, team, team.femi, "two")
    assert unread(client, team.tola) == 2
    assert unread(client, team.femi) == 1  # her own messages don't count

    create_task(client, team)  # posts "Ada created ..."
    assert unread(client, team.tola) == 3
    assert unread(client, team.head) == 2  # Femi's two, not her own task_created


def test_mark_read_all_and_up_to(client):
    team = make_team(client)
    for i in range(1, 5):
        send(client, team, team.femi, f"m{i}")
    page = messages(client, team, team.tola)
    m2 = next(m["id"] for m in page["items"] if m["body"] == "m2")

    r = client.post(f"{API}/rooms/{team.room['id']}/messages/read", json={"up_to": m2}, headers=team.tola)
    assert r.status_code == 204
    assert unread(client, team.tola) == 2  # m3, m4
    assert messages(client, team, team.tola)["last_read_message_id"] == m2

    client.post(f"{API}/rooms/{team.room['id']}/messages/read", headers=team.tola)  # no body: everything
    assert unread(client, team.tola) == 0


def test_read_position_only_moves_forward(client):
    team = make_team(client)
    first = send(client, team, team.femi, "first").json()["id"]
    send(client, team, team.femi, "second")
    client.post(f"{API}/rooms/{team.room['id']}/messages/read", headers=team.tola)
    client.post(f"{API}/rooms/{team.room['id']}/messages/read", json={"up_to": first}, headers=team.tola)
    assert unread(client, team.tola) == 0


def test_mark_read_with_a_foreign_message_is_422(client):
    team = make_team(client)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    theirs = client.post(f"{API}/rooms/{other_room['id']}/messages", json={"body": "hi"}, headers=other_head).json()
    r = client.post(f"{API}/rooms/{team.room['id']}/messages/read", json={"up_to": theirs["id"]}, headers=team.tola)
    assert "up_to" in err(r, 422)["fields"]


def test_deleted_messages_stop_counting_as_unread(client):
    team = make_team(client)
    m = send(client, team, team.femi, "oops").json()
    assert unread(client, team.tola) == 1
    client.delete(f"{API}/rooms/{team.room['id']}/messages/{m['id']}", headers=team.femi)
    assert unread(client, team.tola) == 0


def test_unread_is_per_room(client):
    team = make_team(client)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Side project")
    from tests.conftest import join_and_approve
    join_and_approve(client, other_room, other_head, team.tola)
    client.post(f"{API}/rooms/{other_room['id']}/messages", json={"body": "hi"}, headers=other_head)
    assert unread(client, team.tola, "Side project") == 1
    assert unread(client, team.tola, "Studio Alpha") == 0
