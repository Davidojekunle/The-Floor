"""Phase 7: live hints over WebSockets."""
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.websockets import WebSocketDisconnect

from app.core.config import get_settings
from app.core.security import ALGORITHM
from app.models.room import TempHead
from app.realtime import events as live
from app.realtime.expiry import expired_grant_events
from app.realtime.hub import hub
from app.utils.time import utcnow
from tests.conftest import (
    auth_headers, create_room, create_tag, create_task, join_and_approve, make_team, membership_id_for,
    post_task, put_status, request_join, send,
)

API = "/api/v1"
ALLOWED_KEYS = {"type", "room_id", "at", "task_id", "stage_id", "message_id", "reason", "notification_id"}


@pytest.fixture
def lc(app):
    """One TestClient portal for HTTP and sockets, like one server process."""
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def token_of(headers):
    return headers["Authorization"].split()[1]


@contextmanager
def socket(client, headers):
    with client.websocket_connect(f"{API}/ws") as ws:
        ws.send_json({"type": "auth", "token": token_of(headers)})
        ready = ws.receive_json()
        assert ready["type"] == "ready", ready
        ws.ready = ready
        yield ws


def drain(ws, bell=False):
    """Everything delivered so far: ping, then read until the pong.

    Bell events (notification_created) are left out unless bell=True; test_notifications covers them."""
    time.sleep(0.05)
    ws.send_json({"type": "ping"})
    out = []
    while True:
        m = ws.receive_json()
        if m["type"] == "pong":
            return out
        assert set(m) <= ALLOWED_KEYS, m  # hints only, never content
        if bell or m["type"] != "notification_created":
            out.append(m)


def kinds(msgs):
    return [m["type"] for m in msgs]


def closed_with(ws):
    with pytest.raises(WebSocketDisconnect) as e:
        ws.receive_json()
    return e.value.code


# =========================================================== connecting

def test_ready_lists_my_active_rooms(lc):
    team = make_team(lc)
    with socket(lc, team.femi) as ws:
        assert ws.ready["rooms"] == [team.room["id"]]


def test_ping_pong(lc):
    team = make_team(lc)
    with socket(lc, team.femi) as ws:
        assert drain(ws) == []


@pytest.mark.parametrize("first", [
    {"type": "auth", "token": "garbage"},
    {"type": "hello"},
    {"type": "auth"},
    "not json at all",
])
def test_bad_first_message_closes_with_4401(lc, first):
    make_team(lc)
    with lc.websocket_connect(f"{API}/ws") as ws:
        ws.send_text(first) if isinstance(first, str) else ws.send_json(first)
        assert closed_with(ws) == 4401


def test_expired_token_is_refused(lc):
    team = make_team(lc)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    expired = jwt.encode({"sub": team.ids["femi"], "exp": past}, get_settings().secret_key, algorithm=ALGORITHM)
    with lc.websocket_connect(f"{API}/ws") as ws:
        ws.send_json({"type": "auth", "token": expired})
        assert closed_with(ws) == 4401


def test_silence_after_connecting_closes_with_4401(lc, monkeypatch):
    make_team(lc)
    monkeypatch.setattr(get_settings(), "ws_auth_timeout_seconds", 0.2)
    with lc.websocket_connect(f"{API}/ws") as ws:
        assert closed_with(ws) == 4401


def test_socket_closes_with_4401_when_the_token_expires(lc):
    team = make_team(lc)
    soon = datetime.now(timezone.utc) + timedelta(seconds=3)  # exp is whole seconds: leave room for the handshake
    short = jwt.encode({"sub": team.ids["femi"], "exp": soon}, get_settings().secret_key, algorithm=ALGORITHM)
    with lc.websocket_connect(f"{API}/ws") as ws:
        ws.send_json({"type": "auth", "token": short})
        assert ws.receive_json()["type"] == "ready"
        assert closed_with(ws) == 4401


def test_a_connected_socket_holds_no_database_connection(lc, engine):
    if not hasattr(engine.pool, "checkedout"):
        pytest.skip("pool has no checkout count (in-memory SQLite)")
    team = make_team(lc)
    with socket(lc, team.femi), socket(lc, team.tola):
        assert engine.pool.checkedout() == 0


def test_disconnecting_unregisters(lc):
    team = make_team(lc)
    with socket(lc, team.femi):
        assert uuid.UUID(team.ids["femi"]) in hub.connected_users()
    assert uuid.UUID(team.ids["femi"]) not in hub.connected_users()


# =========================================================== chat

def test_message_created_reaches_room_members_only(lc):
    team = make_team(lc)
    outsider = auth_headers(lc, email="out@example.com", name="Out")
    create_room(lc, outsider, "Elsewhere")
    with socket(lc, team.tola) as tola, socket(lc, team.femi) as femi, socket(lc, outsider) as out:
        m = send(lc, team, team.femi, "hello").json()
        for ws in (tola, femi):  # the sender gets it too (harmless refetch)
            (event,) = drain(ws)
            assert event == {"type": "message_created", "room_id": team.room["id"], "message_id": m["id"], "at": event["at"]}
        assert drain(out) == []


def test_message_deleted(lc):
    team = make_team(lc)
    m = send(lc, team, team.femi, "oops").json()
    with socket(lc, team.tola) as tola:
        lc.delete(f"{API}/rooms/{team.room['id']}/messages/{m['id']}", headers=team.femi)
        assert kinds(drain(tola)) == ["message_deleted"]


def test_several_tabs_each_get_every_event(lc):
    team = make_team(lc)
    with socket(lc, team.tola) as tab1, socket(lc, team.tola) as tab2:
        send(lc, team, team.femi, "hi")
        assert kinds(drain(tab1)) == kinds(drain(tab2)) == ["message_created"]


# =========================================================== tasks

def test_task_changed_on_create_reaches_everyone_with_its_system_message(lc):
    team = make_team(lc)
    with socket(lc, team.tola) as tola:
        task = create_task(lc, team)
        got = drain(tola)
        assert sorted(kinds(got)) == ["message_created", "task_changed"]
        assert next(m for m in got if m["type"] == "task_changed")["task_id"] == task["id"]


def test_stage_status_change_sends_one_task_changed(lc):
    team = make_team(lc)
    task = create_task(lc, team)
    with socket(lc, team.tola) as tola:
        put_status(lc, team, task, task["stages"][0], "in_progress", team.femi)
        assert kinds(drain(tola)) == ["task_changed"]
        put_status(lc, team, task, task["stages"][0], "in_progress", team.femi)  # no-op
        assert drain(tola) == []


def test_proposal_events_reach_only_the_proposer_and_approvers(lc):
    team = make_team(lc)
    with socket(lc, team.head) as head, socket(lc, team.femi) as femi, socket(lc, team.tola) as tola:
        p = post_task(lc, team, team.femi).json()
        assert kinds(drain(head)) == ["task_changed"]
        assert kinds(drain(femi)) == ["task_changed"]
        assert drain(tola) == []  # can't see it, hears nothing

        lc.post(f"{API}/rooms/{team.room['id']}/tasks/{p['id']}/approve", headers=team.head)
        assert "task_changed" in kinds(drain(tola))  # approved: now everyone's


def test_temp_heads_count_as_approvers(lc, db):
    team = make_team(lc)
    db.add(TempHead(room_id=uuid.UUID(team.room["id"]), user_id=uuid.UUID(team.ids["tola"]),
                    granted_by=uuid.UUID(team.ids["head"]), expires_at=utcnow() + timedelta(hours=1)))
    db.commit()
    with socket(lc, team.tola) as tola:
        post_task(lc, team, team.femi)
        assert kinds(drain(tola)) == ["task_changed"]


def test_task_deleted(lc):
    team = make_team(lc)
    task = create_task(lc, team)
    with socket(lc, team.tola) as tola:
        lc.delete(f"{API}/rooms/{team.room['id']}/tasks/{task['id']}", headers=team.head)
        (event,) = drain(tola)
        assert (event["type"], event["task_id"]) == ("task_deleted", task["id"])


def test_progress_updates(lc):
    team = make_team(lc)
    task = create_task(lc, team)
    stage = task["stages"][0]
    with socket(lc, team.tola) as tola:
        lc.post(f"{API}/rooms/{team.room['id']}/tasks/{task['id']}/stages/{stage['id']}/updates",
                json={"note": "half done", "share_to_chat": True}, headers=team.femi)
        got = drain(tola)
        assert sorted(kinds(got)) == ["message_created", "task_updates_changed"]
        assert next(m for m in got if m["type"] == "task_updates_changed")["stage_id"] == stage["id"]


# =========================================================== rooms and membership

def test_join_request_and_approval(lc):
    team = make_team(lc)
    kemi = auth_headers(lc, email="kemi@example.com", name="Kemi")
    with socket(lc, team.head) as head, socket(lc, kemi) as k:
        assert k.ready["rooms"] == []
        mid = request_join(lc, kemi, team.room["invite_code"]).json()["membership_id"]
        assert kinds(drain(head)) == ["room_changed"]  # badge
        assert drain(k) == []  # not a member yet

        lc.post(f"{API}/rooms/{team.room['id']}/join-requests/{mid}/approve", headers=team.head)
        got = drain(k)
        assert "room_access_granted" in kinds(got)
        assert next(m for m in got if m["type"] == "room_access_granted")["room_id"] == team.room["id"]

        send(lc, team, team.femi, "welcome")  # from now on she hears the room
        assert "message_created" in kinds(drain(k))


def test_join_request_rejected(lc):
    team = make_team(lc)
    kemi = auth_headers(lc, email="kemi@example.com", name="Kemi")
    mid = request_join(lc, kemi, team.room["invite_code"]).json()["membership_id"]
    with socket(lc, kemi) as k:
        lc.post(f"{API}/rooms/{team.room['id']}/join-requests/{mid}/reject", headers=team.head)
        assert kinds(drain(k)) == ["join_request_rejected"]


def test_removal_sends_access_lost_and_stops_events(lc):
    team = make_team(lc)
    mid = membership_id_for(lc, team.room["id"], team.head, team.ids["tola"])
    with socket(lc, team.tola) as tola, socket(lc, team.femi) as femi:
        lc.delete(f"{API}/rooms/{team.room['id']}/members/{mid}", headers=team.head)
        assert kinds(drain(tola)) == ["room_access_lost"]
        assert kinds(drain(femi)) == ["room_changed"]

        send(lc, team, team.femi, "after she left")
        assert drain(tola) == []


def test_room_changed_on_tags_and_temp_head(lc):
    team = make_team(lc)
    with socket(lc, team.tola) as tola:
        create_tag(lc, team.room["id"], team.head, "Colorist")
        assert kinds(drain(tola)) == ["room_changed"]
        mid = membership_id_for(lc, team.room["id"], team.head, team.ids["tola"])
        expires = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        lc.put(f"{API}/rooms/{team.room['id']}/members/{mid}/temp-head", json={"expires_at": expires}, headers=team.head)
        assert sorted(kinds(drain(tola))) == ["message_created", "room_changed"]


def test_events_never_cross_rooms(lc):
    team = make_team(lc)
    bola = auth_headers(lc, email="bola@example.com", name="Bola")
    room_b = create_room(lc, bola, "Side project")
    join_and_approve(lc, room_b, bola, team.tola)
    with socket(lc, team.femi) as femi:
        lc.post(f"{API}/rooms/{room_b['id']}/messages", json={"body": "B only"}, headers=bola)
        create_tag(lc, room_b["id"], bola, "B tag")
        assert drain(femi) == []


# =========================================================== reliability rules

def test_a_rolled_back_change_sends_nothing(lc, db):
    team = make_team(lc)
    with socket(lc, team.tola) as tola:
        db.execute(text("SELECT 1"))  # like a real request: a transaction is open before anything is queued
        live.room_changed(db, uuid.UUID(team.room["id"]))
        db.rollback()
        db.commit()
        assert drain(tola) == []


def test_failed_requests_send_nothing(lc):
    team = make_team(lc)
    create_tag(lc, team.room["id"], team.head, "Editor")
    with socket(lc, team.tola) as tola:
        r = lc.post(f"{API}/rooms/{team.room['id']}/tags", json={"name": "editor"}, headers=team.head)
        assert r.status_code == 409
        assert drain(tola) == []


def test_temp_head_expiry_announces_room_changed(lc, db):
    team = make_team(lc)
    now = utcnow()
    for user, expires, revoked in (
        ("tola", now - timedelta(seconds=5), None),      # expired in the window: announce
        ("femi", now + timedelta(hours=1), None),         # still active: no
    ):
        db.add(TempHead(room_id=uuid.UUID(team.room["id"]), user_id=uuid.UUID(team.ids[user]),
                        granted_by=uuid.UUID(team.ids["head"]), expires_at=expires, revoked_at=revoked))
    db.commit()

    found = expired_grant_events(db, now - timedelta(seconds=30), now)
    assert [(p["type"], p["room_id"]) for p, _ in found] == [("room_changed", team.room["id"])]
    assert found[0][1] == {uuid.UUID(team.ids[w]) for w in ("head", "femi", "tola")}
    assert expired_grant_events(db, now, now + timedelta(seconds=30)) == []  # already announced window

    with socket(lc, team.tola) as tola:
        hub.publish(found)
        assert kinds(drain(tola)) == ["room_changed"]
