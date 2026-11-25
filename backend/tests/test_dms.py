"""Private DMs: only between people who share a room to start, open after that, block stops them, switch decides who."""
import pytest
from sqlalchemy import update

from app.models.user import User
from tests.conftest import auth_headers, make_team

API = "/api/v1"


def set_mode(client, headers, mode):
    assert client.patch(f"{API}/admin/settings", json={"direct_messages": mode}, headers=headers).status_code == 200


@pytest.fixture
def team(client, db):
    t = make_team(client)
    db.execute(update(User).where(User.email == "head@example.com").values(is_staff=True))
    db.commit()
    set_mode(client, t.head, "everyone")
    return t


def start(client, who, other_id):
    return client.post(f"{API}/dms", json={"user_id": other_id}, headers=who)


def send(client, who, thread_id, body):
    return client.post(f"{API}/dms/{thread_id}/messages", json={"body": body}, headers=who)


def test_message_someone_in_your_room(client, team):
    r = start(client, team.femi, team.ids["tola"])
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["other"]["name"] == "Tola" and t["can_send"] is True and t["last_message"] is None
    # starting again finds the same conversation, from either side
    assert start(client, team.tola, team.ids["femi"]).json()["id"] == t["id"]

    m = send(client, team.femi, t["id"], "  hey, the script is ready  ")
    assert m.status_code == 201 and m.json()["body"] == "hey, the script is ready"
    assert client.get(f"{API}/me", headers=team.tola).json()["unread_dms"] == 1
    assert client.get(f"{API}/me", headers=team.femi).json()["unread_dms"] == 0  # your own message is read

    threads = client.get(f"{API}/dms", headers=team.tola).json()["items"]
    assert len(threads) == 1 and threads[0]["unread"] == 1 and threads[0]["last_message"]["body"] == "hey, the script is ready"
    page = client.get(f"{API}/dms/{t['id']}/messages", headers=team.tola).json()
    assert [x["body"] for x in page["items"]] == ["hey, the script is ready"] and page["has_more"] is False

    assert client.post(f"{API}/dms/{t['id']}/read", headers=team.tola).status_code == 204
    assert client.get(f"{API}/me", headers=team.tola).json()["unread_dms"] == 0


def test_cant_start_with_someone_outside_your_rooms(client, team):
    stranger = auth_headers(client, email="zed@example.com", name="Zed")
    zed_id = client.get(f"{API}/me", headers=stranger).json()["id"]
    r = start(client, team.femi, zed_id)
    assert r.status_code == 403 and "one of your rooms" in r.json()["error"]["message"]
    assert start(client, team.femi, team.ids["femi"]).status_code == 404  # yourself


def test_stays_open_after_leaving_the_room(client, team):
    t = start(client, team.femi, team.ids["tola"]).json()
    room = team.room["id"]
    assert client.post(f"{API}/rooms/{room}/leave", headers=team.tola).status_code in (200, 204)
    assert send(client, team.femi, t["id"], "still there?").status_code == 201
    assert start(client, team.femi, team.ids["tola"]).json()["id"] == t["id"]  # finding it needs no shared room


def test_only_the_two_people_see_it(client, team):
    t = start(client, team.femi, team.ids["tola"]).json()
    send(client, team.femi, t["id"], "private")
    assert client.get(f"{API}/dms/{t['id']}", headers=team.head).status_code == 404
    assert client.get(f"{API}/dms/{t['id']}/messages", headers=team.head).status_code == 404
    assert send(client, team.head, t["id"], "hi").status_code == 404
    assert client.get(f"{API}/dms", headers=team.head).json()["items"] == []


def test_block_stops_both_ways_and_unblock_reopens(client, team):
    t = start(client, team.femi, team.ids["tola"]).json()
    send(client, team.femi, t["id"], "hello")
    assert client.put(f"{API}/blocks/{team.ids['femi']}", headers=team.tola).status_code == 204
    assert send(client, team.femi, t["id"], "hello?").status_code == 403
    assert send(client, team.tola, t["id"], "bye").status_code == 403
    mine = client.get(f"{API}/dms/{t['id']}", headers=team.tola).json()
    theirs = client.get(f"{API}/dms/{t['id']}", headers=team.femi).json()
    assert mine["you_blocked"] is True and mine["can_send"] is False
    assert theirs["you_blocked"] is False and theirs["can_send"] is False
    assert [b["name"] for b in client.get(f"{API}/blocks", headers=team.tola).json()] == ["Femi"]
    # old messages stay readable
    assert client.get(f"{API}/dms/{t['id']}/messages", headers=team.tola).json()["items"][0]["body"] == "hello"
    assert client.delete(f"{API}/blocks/{team.ids['femi']}", headers=team.tola).status_code == 204
    assert send(client, team.femi, t["id"], "back").status_code == 201


def test_a_block_also_stops_a_new_conversation(client, team):
    client.put(f"{API}/blocks/{team.ids['tola']}", headers=team.femi)
    assert start(client, team.tola, team.ids["femi"]).status_code == 403


def test_delete_your_own_message(client, team):
    t = start(client, team.femi, team.ids["tola"]).json()
    m = send(client, team.femi, t["id"], "oops").json()
    assert client.delete(f"{API}/dms/{t['id']}/messages/{m['id']}", headers=team.tola).status_code == 404
    assert client.delete(f"{API}/dms/{t['id']}/messages/{m['id']}", headers=team.femi).status_code == 204
    item = client.get(f"{API}/dms/{t['id']}/messages", headers=team.tola).json()["items"][0]
    assert item["deleted"] is True and item["body"] is None
    assert client.get(f"{API}/me", headers=team.tola).json()["unread_dms"] == 0  # deleted ones aren't unread


def test_admin_switch(client, team):
    set_mode(client, team.head, "staff")
    me = client.get(f"{API}/me", headers=team.femi).json()
    assert me["direct_messages"] is False
    assert client.get(f"{API}/dms", headers=team.femi).status_code == 404
    # staff can't start one with someone who doesn't have DMs
    assert start(client, team.head, team.ids["femi"]).status_code == 404
    set_mode(client, team.head, "off")
    assert client.get(f"{API}/dms", headers=team.head).status_code == 404
    assert client.get(f"{API}/me", headers=team.head).json()["direct_messages"] is False


def test_paging_older_messages(client, team):
    t = start(client, team.femi, team.ids["tola"]).json()
    for i in range(55):
        assert send(client, team.femi, t["id"], f"m{i}").status_code == 201
    first = client.get(f"{API}/dms/{t['id']}/messages", headers=team.tola).json()
    assert len(first["items"]) == 50 and first["has_more"] is True and first["items"][-1]["body"] == "m54"
    older = client.get(f"{API}/dms/{t['id']}/messages", params={"before": first["items"][0]["created_at"]},
                       headers=team.tola).json()
    assert [x["body"] for x in older["items"]] == [f"m{i}" for i in range(5)] and older["has_more"] is False
