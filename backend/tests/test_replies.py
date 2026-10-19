"""Quote replies in chat."""
from tests.conftest import auth_headers, create_room, send
from tests.test_mentions import bell, message, pushes, settings, team  # noqa: F401  (fixtures)
from tests.test_push import subscribe

API = "/api/v1"


def reply(client, team, headers, to_id, body="On it", **extra):
    return send(client, team, headers, body, reply_to_id=to_id, **extra)


def test_a_reply_quotes_the_original(client, team):
    original = send(client, team, team.femi, "Script draft is up").json()
    r = reply(client, team, team.tola, original["id"])
    assert r.status_code == 201, r.text
    assert r.json()["reply_to"] == {"id": original["id"], "type": "user", "deleted": False,
                                    "sender": {"id": team.ids["femi"], "name": "Femi"}, "preview": "Script draft is up"}
    assert message(client, team, team.head, r.json()["id"])["reply_to"]["preview"] == "Script draft is up"


def test_messages_without_a_reply_have_none(client, team):
    assert send(client, team, team.femi, "hi").json()["reply_to"] is None


def test_long_originals_are_cut_and_put_on_one_line(client, team):
    original = send(client, team, team.femi, "line one\nline two " + "x" * 300).json()
    quote = reply(client, team, team.tola, original["id"]).json()["reply_to"]["preview"]
    assert "\n" not in quote and len(quote) == 140 and quote.endswith("…")


def test_deleting_the_original_keeps_the_reply_but_hides_the_text(client, team):
    original = send(client, team, team.femi, "oops").json()
    r = reply(client, team, team.tola, original["id"]).json()
    client.delete(f"{API}/rooms/{team.room['id']}/messages/{original['id']}", headers=team.femi)
    assert message(client, team, team.head, r["id"])["reply_to"] == {
        "id": original["id"], "type": "user", "deleted": True, "sender": {"id": team.ids["femi"], "name": "Femi"},
        "preview": None}


def test_you_cannot_reply_to_a_deleted_or_foreign_message(client, team):
    gone = send(client, team, team.femi, "oops").json()
    client.delete(f"{API}/rooms/{team.room['id']}/messages/{gone['id']}", headers=team.femi)
    r = reply(client, team, team.tola, gone["id"])
    assert r.status_code == 422 and r.json()["error"]["fields"]["reply_to_id"] == "That message was deleted."

    other = auth_headers(client, email="out@example.com", name="Out")
    elsewhere = create_room(client, other, "Elsewhere")
    foreign = client.post(f"{API}/rooms/{elsewhere['id']}/messages", json={"body": "secret"}, headers=other).json()
    r = reply(client, team, team.tola, foreign["id"])
    assert r.status_code == 422 and r.json()["error"]["fields"]["reply_to_id"] == "Unknown message in this room."


def test_replying_to_a_system_message(client, team):
    items = client.get(f"{API}/rooms/{team.room['id']}/messages", headers=team.tola).json()["items"]
    joined = next(m for m in items if m["type"] == "system")
    r = reply(client, team, team.tola, joined["id"], "Welcome!").json()
    assert r["reply_to"]["type"] == "system" and r["reply_to"]["sender"] is None
    assert r["reply_to"]["preview"] == joined["body"]
    assert bell(client, team.femi) == [] and bell(client, team.head) == []  # nobody to notify


def test_the_person_replied_to_is_notified(client, team, pushes):
    subscribe(client, team.femi)
    original = send(client, team, team.femi, "Script draft is up").json()
    reply(client, team, team.tola, original["id"], "Looks great")
    (n,) = bell(client, team.femi)
    assert (n["type"], n["title"], n["data"]["preview"]) == ("replied", "Tola replied to you in Studio Alpha", "Looks great")
    assert [p["title"] for p in pushes] == ["Tola replied to you in Studio Alpha"]
    assert pushes[0]["url"] == f"/rooms/{team.room['id']}/chat"


def test_replying_to_yourself_notifies_nobody(client, team):
    original = send(client, team, team.femi, "first").json()
    reply(client, team, team.femi, original["id"], "and another thing")
    assert bell(client, team.femi) == []


def test_reply_plus_mention_of_the_same_person_is_one_notification(client, team, pushes):
    subscribe(client, team.femi)
    settings(client, team.femi, all_messages=True)
    original = send(client, team, team.femi, "draft").json()
    reply(client, team, team.tola, original["id"], "@Femi yes", mention_ids=[team.ids["femi"]])
    assert [n["type"] for n in bell(client, team.femi)] == ["replied"]
    assert len(pushes) == 1  # not a second "every message" push either


def test_replies_follow_the_mentions_switch(client, team, pushes):
    subscribe(client, team.femi)
    settings(client, team.femi, mentions=False)
    original = send(client, team, team.femi, "draft").json()
    reply(client, team, team.tola, original["id"])
    assert pushes == []
    assert [n["type"] for n in bell(client, team.femi)] == ["replied"]  # the bell still shows it
