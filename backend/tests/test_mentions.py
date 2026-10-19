"""@mentions in chat, and pushes for chat messages."""
import json

import pytest

from app.services import notification_email, push_service
from app.utils.time import utcnow
from tests.conftest import auth_headers, make_team, send
from tests.test_notifications import LATER, clear, outbox
from tests.test_push import subscribe

API = "/api/v1"


@pytest.fixture
def team(client):
    t = make_team(client)
    for h in (t.head, t.femi, t.tola):
        clear(client, h)
    return t


@pytest.fixture
def pushes(monkeypatch):
    sent = []
    monkeypatch.setattr("pywebpush.webpush", lambda subscription_info, data, **kw: sent.append(json.loads(data)))
    monkeypatch.setattr(push_service._pool, "submit", lambda fn, *args: fn(*args))
    return sent


def mention(client, team, headers, body, *people):
    return send(client, team, headers, body, mention_ids=[team.ids[p] for p in people])


def bell(client, headers):
    r = client.get(f"{API}/me/notifications", headers=headers, params={"unread": True})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def message(client, team, headers, message_id):
    items = client.get(f"{API}/rooms/{team.room['id']}/messages", headers=headers).json()["items"]
    return next(m for m in items if m["id"] == message_id)


def settings(client, headers, **changes):
    return client.patch(f"{API}/me/notification-settings", json=changes, headers=headers).json()


# =========================================================== the message

def test_a_mention_is_stored_and_returned(client, team):
    m = mention(client, team, team.femi, "@Tola can you look at the cut?", "tola")
    assert m.status_code == 201, m.text
    assert m.json()["mentions"] == [{"id": team.ids["tola"], "name": "Tola"}]
    assert message(client, team, team.head, m.json()["id"])["mentions"] == [{"id": team.ids["tola"], "name": "Tola"}]


def test_only_real_visible_mentions_count(client, team):
    outsider = auth_headers(client, email="out@example.com", name="Out")
    out_id = client.get(f"{API}/me", headers=outsider).json()["id"]
    body = {"body": "@Femi @Out thanks", "mention_ids": [team.ids["tola"], team.ids["femi"], out_id]}
    # Tola's @Name was deleted from the text, Femi is the sender, Out isn't in the room
    m = client.post(f"{API}/rooms/{team.room['id']}/messages", json=body, headers=team.femi).json()
    assert m["mentions"] == []


def test_deleted_messages_drop_their_mentions(client, team):
    m = mention(client, team, team.femi, "@Tola hi", "tola").json()
    client.delete(f"{API}/rooms/{team.room['id']}/messages/{m['id']}", headers=team.femi)
    gone = message(client, team, team.head, m["id"])
    assert gone["mentions"] == [] and gone["body"] is None


# =========================================================== notifications

def test_the_mentioned_person_gets_a_bell_item(client, team):
    mention(client, team, team.femi, "@Tola can you look at the cut?", "tola")
    (n,) = bell(client, team.tola)
    assert n["type"] == "mentioned"
    assert n["title"] == "Femi mentioned you in Studio Alpha"
    assert n["data"]["preview"] == "@Tola can you look at the cut?"
    assert bell(client, team.femi) == [] and bell(client, team.head) == []


def test_mentions_are_emailed_by_default(client, db, team):
    mention(client, team, team.femi, "@Tola can you look at the cut?", "tola")
    assert notification_email.flush_due(db, utcnow() + LATER) == 1
    (email,) = outbox(db, "mentions")
    assert email.subject == "Femi mentioned you in Studio Alpha"
    assert "“@Tola can you look at the cut?”" in email.text_body
    assert f"/rooms/{team.room['id']}/chat" in email.text_body


def test_mention_push_follows_the_switch(client, team, pushes):
    subscribe(client, team.tola)
    mention(client, team, team.femi, "@Tola one", "tola")
    assert [p["title"] for p in pushes] == ["Femi mentioned you in Studio Alpha"]
    assert pushes[0]["url"] == f"/rooms/{team.room['id']}/chat"
    assert pushes[0]["body"] == "@Tola one"

    settings(client, team.tola, mentions=False)
    mention(client, team, team.femi, "@Tola two", "tola")
    assert len(pushes) == 1
    assert len(bell(client, team.tola)) == 2  # the bell still shows everything


def test_plain_messages_push_nothing_by_default(client, team, pushes):
    subscribe(client, team.tola)
    send(client, team, team.femi, "Morning all")
    assert pushes == []


def test_every_message_when_switched_on(client, team, pushes):
    assert client.get(f"{API}/me/notification-settings", headers=team.tola).json()["all_messages"] is False
    subscribe(client, team.tola)
    settings(client, team.tola, all_messages=True)
    send(client, team, team.femi, "Morning all")
    (p,) = pushes
    assert p == {"title": "Femi in Studio Alpha", "body": "Morning all", "url": f"/rooms/{team.room['id']}/chat",
                 "tag": f"chat:{team.room['id']}"}
    send(client, team, team.tola, "Morning!")  # your own message: nothing
    assert len(pushes) == 1
    assert bell(client, team.tola) == []  # push only, the bell isn't for every message


def test_a_mention_beats_the_every_message_push(client, team, pushes):
    subscribe(client, team.tola)
    settings(client, team.tola, all_messages=True)
    mention(client, team, team.femi, "@Tola look", "tola")
    assert [p["title"] for p in pushes] == ["Femi mentioned you in Studio Alpha"]  # one pop-up, not two


def test_muted_rooms_stay_silent(client, team, pushes):
    subscribe(client, team.tola)
    settings(client, team.tola, all_messages=True)
    client.put(f"{API}/me/notification-settings/muted-rooms/{team.room['id']}", headers=team.tola)
    send(client, team, team.femi, "Morning all")
    mention(client, team, team.femi, "@Tola look", "tola")
    assert pushes == []
    assert bell(client, team.tola) == []


def test_long_messages_are_cut_for_previews(client, team, pushes):
    subscribe(client, team.tola)
    settings(client, team.tola, all_messages=True)
    send(client, team, team.femi, "word " * 100)
    assert len(pushes[0]["body"]) == 140 and pushes[0]["body"].endswith("…")
