"""Calls, C1 (contract v4). The video provider is faked (services/video.FakeVideo): no real calls start."""
import base64
import hashlib
import json
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.models.call import Call
from app.models.email import OutboxEmail
from app.services import call_service, video
from app.utils.time import utcnow
from tests.conftest import auth_headers, create_task, join_and_approve, make_team, membership_id_for, post_task

API = "/api/v1"
KEY, SECRET = "APItestkey", "a-test-api-secret-that-is-long-enough-for-hs256"


@pytest.fixture
def fake(monkeypatch):
    s = get_settings()
    for k, v in {"calls_enabled": True, "video_provider": "fake", "livekit_url": "wss://thefloor-test.livekit.cloud",
                 "livekit_api_key": KEY, "livekit_api_secret": SECRET}.items():
        monkeypatch.setattr(s, k, v)
    return video.reset_fake()


def calls_url(team, *rest):
    return "/".join([f"{API}/rooms/{team.room['id']}/calls", *rest])


def start(client, team, headers, task_id=None):
    return client.post(calls_url(team), json={"task_id": task_id} if task_id else {}, headers=headers)


def bell(client, headers):
    return client.get(f"{API}/me/notifications", headers=headers).json()["items"]


def last_message(client, team, headers):
    return client.get(f"{API}/rooms/{team.room['id']}/messages", params={"limit": 1}, headers=headers).json()["items"][0]


def signed(body: dict, secret=SECRET):
    import jwt

    raw = json.dumps(body).encode()
    digest = base64.b64encode(hashlib.sha256(raw).digest()).decode()
    token = jwt.encode({"iss": KEY, "sha256": digest}, secret, algorithm="HS256")
    return raw, {"Authorization": token, "Content-Type": "application/webhook+json"}


def webhook(client, kind, room, user_id, session, joined_at=1700000000):
    raw, headers = signed({"event": kind, "room": {"name": room},
                           "participant": {"sid": session, "identity": str(user_id), "joined_at": str(joined_at)}})
    return client.post(f"{API}/webhooks/livekit", content=raw, headers=headers)


def provider_room(db, call_id):
    db.expire_all()
    return db.get(Call, uuid.UUID(call_id)).provider_room


# ================================================================ switched off

def test_everything_is_hidden_until_calls_are_switched_on(client):
    team = make_team(client)
    assert start(client, team, team.head).status_code == 404
    assert client.get(f"{API}/me", headers=team.head).json()["calls_enabled"] is False


# ================================================================ starting

def test_starting_a_room_call(client, db, fake):
    team = make_team(client)
    r = start(client, team, team.femi)
    assert r.status_code == 201, r.text
    call = r.json()
    assert (call["status"], call["kind"], call["title"]) == ("live", "instant", "Call in Studio Alpha")
    assert call["can_end"] is True and call["participants"] == []
    assert len(fake.rooms) == 1  # a private provider room, made before anything was saved

    msg = last_message(client, team, team.head)
    assert msg["body"] == "Femi started a call" and msg["event"]["detail"] == {"call_id": call["id"]}
    # everyone else in the room is told, by bell and push; never by email (it would arrive too late)
    calls = lambda h: [n for n in bell(client, h) if n["type"] == "call_started"]  # noqa: E731
    assert [n["title"] for n in calls(team.head)] == ["Femi started a call in Studio Alpha"]
    assert calls(team.femi) == []
    assert db.scalars(select(OutboxEmail)).all() == []

    me = client.get(f"{API}/me", headers=team.tola).json()
    assert me["calls_enabled"] is True and me["rooms"][0]["live_call"] == {"id": call["id"], "participant_count": 0}


def test_one_live_call_per_room_starting_again_joins_it(client, fake):
    team = make_team(client)
    first = start(client, team, team.head).json()
    again = start(client, team, team.tola)
    assert again.status_code == 200 and again.json()["id"] == first["id"]
    assert len(fake.rooms) == 1


def test_a_call_about_a_task(client, fake):
    team = make_team(client)
    kemi = auth_headers(client, email="kemi@example.com", name="Kemi")
    join_and_approve(client, team.room, team.head, kemi)  # in the room, not on the task
    task = create_task(client, team)
    room_call = start(client, team, team.head).json()
    r = start(client, team, team.head, task["id"])
    assert r.status_code == 201  # a task call is separate from the room call
    call = r.json()
    assert call["id"] != room_call["id"] and call["title"] == "Call about Product promo video"
    assert call["task"] == {"id": task["id"], "title": "Product promo video"}
    # the task's people are told (its stages' tag holders), not everyone in the room
    assert [n["title"] for n in bell(client, team.femi)][0] == "Ada started a call about Product promo video"
    assert [n for n in bell(client, kemi) if n["title"].endswith("about Product promo video")] == []
    detail = client.get(f"{API}/rooms/{team.room['id']}/tasks/{task['id']}", headers=team.tola).json()
    assert detail["live_call"] == {"id": call["id"], "participant_count": 0}


def test_no_call_about_a_proposal(client, fake):
    team = make_team(client)
    proposal = post_task(client, team, team.femi).json()
    r = start(client, team, team.femi, proposal["id"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "TASK_NOT_APPROVED"


def test_provider_down_saves_nothing(client, db, fake):
    team = make_team(client)
    fake.down = True
    r = start(client, team, team.head)
    assert r.status_code == 503 and r.json()["error"]["code"] == "CALL_PROVIDER_UNAVAILABLE"
    assert db.scalars(select(Call)).all() == []
    fake.down = False
    assert start(client, team, team.head).status_code == 201  # retrying is safe


# ================================================================ joining

def test_joining_hands_each_person_their_own_pass(client, fake):
    team = make_team(client)
    call = start(client, team, team.femi).json()
    p = client.post(calls_url(team, call["id"], "join"), headers=team.tola)
    assert p.status_code == 200, p.text
    j = p.json()
    assert j["provider"] == "livekit" and j["server_url"] == "wss://thefloor-test.livekit.cloud"
    assert j["token"].startswith("fake-token:floor-") and j["token"].endswith(f":{team.ids['tola']}:0")  # not an owner
    head_pass = client.post(calls_url(team, call["id"], "join"), headers=team.head).json()
    assert head_pass["token"].endswith(":1")  # the head can manage the call


def test_a_full_call(client, db, fake, monkeypatch):
    team = make_team(client)
    monkeypatch.setattr(get_settings(), "call_max_participants", 1)
    call = start(client, team, team.femi).json()
    webhook(client, "participant_joined", provider_room(db, call["id"]), team.ids["femi"], "s-femi")
    r = client.post(calls_url(team, call["id"], "join"), headers=team.tola)
    assert r.status_code == 409 and r.json()["error"]["code"] == "CALL_FULL"
    assert client.post(calls_url(team, call["id"], "join"), headers=team.femi).status_code == 200  # rejoining is fine


# ================================================================ ending

def test_who_can_end_for_everyone(client, fake):
    team = make_team(client)
    call = start(client, team, team.femi).json()
    tola_view = client.get(calls_url(team, call["id"]), headers=team.tola).json()
    assert tola_view["can_end"] is False
    assert client.post(calls_url(team, call["id"], "end"), headers=team.tola).status_code == 403
    assert client.post(calls_url(team, call["id"], "end"), headers=team.head).status_code == 204  # the head can
    assert client.post(calls_url(team, call["id"], "end"), headers=team.femi).json()["error"]["code"] == "CALL_ENDED"
    assert client.post(calls_url(team, call["id"], "join"), headers=team.tola).json()["error"]["code"] == "CALL_ENDED"
    assert fake.deleted  # the provider room is closed
    assert start(client, team, team.tola).json()["id"] != call["id"]  # a new call can start


def test_call_ended_card_counts_minutes_and_people(client, db, fake):
    team = make_team(client)
    call = start(client, team, team.head).json()
    room = provider_room(db, call["id"])
    webhook(client, "participant_joined", room, team.ids["head"], "s1")
    webhook(client, "participant_joined", room, team.ids["tola"], "s2")
    db.execute(update(Call).where(Call.id == uuid.UUID(call["id"])).values(started_at=utcnow() - timedelta(minutes=24)))
    db.commit()
    client.post(calls_url(team, call["id"], "end"), headers=team.head)
    msg = last_message(client, team, team.femi)
    assert msg["body"] == "Call ended · 24 min · 2 people"
    assert msg["event"]["detail"]["people"] == 2


# ================================================================ who's in: the webhook

def test_webhook_tracks_who_is_in(client, db, fake):
    team = make_team(client)
    call = start(client, team, team.head).json()
    room = provider_room(db, call["id"])
    assert webhook(client, "participant_joined", room, team.ids["tola"], "s-tola").status_code == 200
    webhook(client, "participant_joined", room, team.ids["tola"], "s-tola")  # delivered twice: counted once
    webhook(client, "participant_joined", room, team.ids["tola"], "s-tola-phone")  # a second device: still one person
    got = client.get(calls_url(team, call["id"]), headers=team.head).json()
    assert got["participants"] == [{"id": team.ids["tola"], "name": "Tola"}]
    assert client.get(f"{API}/me", headers=team.head).json()["rooms"][0]["live_call"]["participant_count"] == 1
    webhook(client, "participant_left", room, team.ids["tola"], "s-tola")
    webhook(client, "participant_left", room, team.ids["tola"], "s-tola-phone")
    assert client.get(calls_url(team, call["id"]), headers=team.head).json()["participants"] == []


def test_webhook_signatures(client, db, fake):
    team = make_team(client)
    call = start(client, team, team.head).json()
    raw, headers = signed({"event": "participant_joined", "room": {"name": provider_room(db, call["id"])},
                           "participant": {"sid": "x", "identity": str(team.ids["head"])}},
                          secret="someone-else's-secret-that-is-long-enough-for-hs256")
    assert client.post(f"{API}/webhooks/livekit", content=raw, headers=headers).status_code == 401
    raw, headers = signed({"event": "participant_joined"})
    assert client.post(f"{API}/webhooks/livekit", content=raw + b" ", headers=headers).status_code == 401  # body changed
    assert client.post(f"{API}/webhooks/livekit", json={"event": "participant_joined"}).status_code == 401  # unsigned


# ================================================================ the minute check

def test_check_ends_a_call_two_minutes_after_the_last_person_leaves(client, db, fake):
    team = make_team(client)
    call = start(client, team, team.head).json()
    room = provider_room(db, call["id"])
    fake.present[room] = [video.Present("s1", str(team.ids["head"]), utcnow())]
    call_service.check_calls(db)
    assert client.get(calls_url(team, call["id"]), headers=team.head).json()["participants"][0]["name"] == "Ada"

    fake.present[room] = []  # left, and the webhook never said so
    call_service.check_calls(db)
    assert client.get(calls_url(team, call["id"]), headers=team.head).json()["status"] == "live"  # time to rejoin
    db.execute(update(Call).where(Call.id == uuid.UUID(call["id"])).values(empty_since=utcnow() - timedelta(minutes=3)))
    db.commit()
    assert call_service.check_calls(db) == 1
    assert client.get(calls_url(team, call["id"]), headers=team.head).json()["status"] == "ended"


def test_check_ends_a_call_at_the_hard_stop(client, db, fake):
    team = make_team(client)
    call = start(client, team, team.head).json()
    room = provider_room(db, call["id"])
    fake.present[room] = [video.Present("s1", str(team.ids["head"]), utcnow())]
    db.execute(update(Call).where(Call.id == uuid.UUID(call["id"])).values(hard_stop_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    assert call_service.check_calls(db) == 1


def test_provider_down_during_the_check_keeps_the_call(client, db, fake):
    team = make_team(client)
    call = start(client, team, team.head).json()
    webhook(client, "participant_joined", provider_room(db, call["id"]), team.ids["head"], "s1")
    fake.down = True
    assert call_service.check_calls(db) == 0
    assert client.get(calls_url(team, call["id"]), headers=team.head).json()["participants"] != []


# ================================================================ people, tasks and rooms going

def test_someone_removed_from_the_room_is_dropped_from_its_call(client, db, fake):
    team = make_team(client)
    call = start(client, team, team.head).json()
    room = provider_room(db, call["id"])
    webhook(client, "participant_joined", room, team.ids["tola"], "s-tola")
    mid = membership_id_for(client, team.room["id"], team.head, team.ids["tola"])
    assert client.delete(f"{API}/rooms/{team.room['id']}/members/{mid}", headers=team.head).status_code == 204
    assert (room, [team.ids["tola"]]) in fake.ejected
    assert client.get(calls_url(team, call["id"]), headers=team.head).json()["participants"] == []


def test_deleting_the_task_ends_its_call(client, db, fake):
    team = make_team(client)
    task = create_task(client, team)
    call = start(client, team, team.head, task["id"]).json()
    assert client.delete(f"{API}/rooms/{team.room['id']}/tasks/{task['id']}", headers=team.head).status_code == 204
    db.expire_all()
    row = db.get(Call, uuid.UUID(call["id"]))
    assert row.status == "ended" and row.task_id is None


def test_security_headers_allow_the_call_screen_only_while_calls_are_on(client, fake, monkeypatch):
    on = client.get(f"{API}/health")
    assert "camera=(self)" in on.headers["permissions-policy"]
    assert "wss://*.livekit.cloud" in on.headers["content-security-policy"]
    monkeypatch.setattr(get_settings(), "calls_enabled", False)
    off = client.get(f"{API}/health")
    assert "camera=()" in off.headers["permissions-policy"] and "livekit" not in off.headers["content-security-policy"]
