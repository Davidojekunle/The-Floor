"""L1: leave a room, transfer headship, delete a room."""
import uuid
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.models.message import Message
from app.models.progress import ProgressUpdate
from app.models.room import Membership, Room, TempHead
from app.models.tag import MembershipTag, Tag
from app.models.task import Stage, StageAssignee, Task
from app.models.template import TaskTemplate, TemplateStage
from app.services import lifecycle_service, room_service
from app.models.user import User
from app.utils.time import utcnow
from tests.conftest import (
    auth_headers, create_room, create_task, join_and_approve, make_team, membership_id_for, messages,
    request_join, send,
)

API = "/api/v1"


def url(team, path=""):
    return f"{API}/rooms/{team.room['id']}{path}"


def err(r, status, code=None):
    assert r.status_code == status, r.text
    if code:
        assert r.json()["error"]["code"] == code
    return r.json()["error"]


def last_event(client, team, headers=None):
    m = next(x for x in messages(client, team, headers)["items"] if x["type"] == "system")
    e = m["event"]
    return e["type"], e["actor"]["name"], (e["subject"] or {}).get("name"), m["body"]


# =========================================================== leave

def test_member_leaves_and_loses_access(client):
    team = make_team(client)
    r = client.post(url(team, "/leave"), headers=team.tola)
    assert r.status_code == 204
    assert client.get(url(team), headers=team.tola).status_code == 404
    assert client.get(f"{API}/me", headers=team.tola).json()["rooms"] == []
    names = [m["user"]["name"] for m in client.get(url(team, "/members"), headers=team.head).json()["items"]]
    assert "Tola" not in names
    assert last_event(client, team) == ("member_left", "Tola", None, "Tola left the room")


def test_leaving_cleans_up_tags_temp_head_and_assignments(client, db):
    team = make_team(client)
    create_task(client, team, stages=[{"title": "A", "assignee_ids": [team.ids["tola"]]}])
    db.add(TempHead(room_id=uuid.UUID(team.room["id"]), user_id=uuid.UUID(team.ids["tola"]),
                    granted_by=uuid.UUID(team.ids["head"]), expires_at=utcnow() + timedelta(days=1)))
    db.commit()
    client.post(url(team, "/leave"), headers=team.tola)

    tola = uuid.UUID(team.ids["tola"])
    assert db.scalar(select(func.count()).select_from(StageAssignee).where(StageAssignee.user_id == tola)) == 0
    assert db.scalar(select(func.count()).select_from(TempHead).where(TempHead.user_id == tola, TempHead.revoked_at.is_(None))) == 0
    m = db.scalar(select(Membership).where(Membership.user_id == tola))
    assert m.status == "left"
    assert db.scalar(select(func.count()).select_from(MembershipTag).where(MembershipTag.membership_id == m.id)) == 0


def test_the_head_must_transfer_before_leaving(client):
    team = make_team(client)
    err(client.post(url(team, "/leave"), headers=team.head), 409, "HEAD_MUST_TRANSFER")
    assert client.get(url(team), headers=team.head).status_code == 200


def test_temp_heads_can_leave(client, db):
    team = make_team(client)
    db.add(TempHead(room_id=uuid.UUID(team.room["id"]), user_id=uuid.UUID(team.ids["femi"]),
                    granted_by=uuid.UUID(team.ids["head"]), expires_at=utcnow() + timedelta(days=1)))
    db.commit()
    assert client.post(url(team, "/leave"), headers=team.femi).status_code == 204


def test_leaving_twice_or_as_a_non_member_is_404(client):
    team = make_team(client)
    client.post(url(team, "/leave"), headers=team.tola)
    assert client.post(url(team, "/leave"), headers=team.tola).status_code == 404
    stranger = auth_headers(client, email="stranger@example.com", name="Stranger")
    assert client.post(url(team, "/leave"), headers=stranger).status_code == 404


def test_a_leaver_can_ask_to_rejoin_and_starts_clean(client):
    team = make_team(client)
    client.post(url(team, "/leave"), headers=team.tola)
    preview = client.get(f"{API}/join/{team.room['invite_code']}", headers=team.tola).json()
    assert (preview["already_member"], preview["already_requested"]) == (False, False)
    r = request_join(client, team.tola, team.room["invite_code"])
    assert r.status_code == 201 and r.json()["status"] == "pending"
    client.post(url(team, f"/join-requests/{r.json()['membership_id']}/approve"), headers=team.head)
    me = next(m for m in client.get(url(team, "/members"), headers=team.head).json()["items"] if m["user"]["name"] == "Tola")
    assert me["tags"] == []


def test_tasks_and_messages_of_a_leaver_stay(client):
    team = make_team(client)
    send(client, team, team.tola, "bye all")
    client.post(url(team, "/leave"), headers=team.tola)
    bodies = [m["body"] for m in messages(client, team)["items"]]
    assert "bye all" in bodies


def test_leaving_reports_stages_left_with_nobody(client, db):
    team = make_team(client)
    # Edit has the Video Editor tag: Tola is its only holder. "Solo" is assigned to Tola only.
    # "Shared" is assigned to Tola and Femi. A done stage never counts.
    task = create_task(client, team, stages=[
        {"title": "Solo", "assignee_ids": [team.ids["tola"]]},
        {"title": "Shared", "assignee_ids": [team.ids["tola"], team.ids["femi"]]},
        {"title": "Edit", "tag_id": team.tags["Video Editor"]["id"]},
    ])
    tola = db.scalar(select(User).where(User.email == "tola@example.com"))
    ctx = room_service.get_room_context(db, uuid.UUID(team.room["id"]), tola)
    orphaned = lifecycle_service.leave_room(db, ctx)
    assert sorted(s.title for s in orphaned) == ["Edit", "Solo"]
    assert task["id"]


# =========================================================== transfer

def test_transfer_headship(client):
    team = make_team(client)
    mid = membership_id_for(client, team.room["id"], team.head, team.ids["tola"])
    r = client.post(url(team, "/transfer-head"), json={"membership_id": mid}, headers=team.head)
    assert r.status_code == 200
    body = r.json()
    assert body["my_role"] == "member" and "join.manage" not in body["permissions"]  # the old head's view

    assert client.get(url(team), headers=team.tola).json()["my_role"] == "head"
    assert last_event(client, team) == ("head_transferred", "Ada", "Tola", "Ada made Tola the head")
    assert client.post(url(team, "/leave"), headers=team.head).status_code == 204  # the old head can now leave


def test_transfer_ends_the_targets_temp_head_grant(client, db):
    team = make_team(client)
    db.add(TempHead(room_id=uuid.UUID(team.room["id"]), user_id=uuid.UUID(team.ids["tola"]),
                    granted_by=uuid.UUID(team.ids["head"]), expires_at=utcnow() + timedelta(days=1)))
    db.commit()
    mid = membership_id_for(client, team.room["id"], team.head, team.ids["tola"])
    client.post(url(team, "/transfer-head"), json={"membership_id": mid}, headers=team.head)
    room = client.get(url(team), headers=team.tola).json()
    assert (room["my_role"], room["temp_head_expires_at"]) == ("head", None)


def test_transfer_rules(client, db):
    team = make_team(client)
    head_mid = membership_id_for(client, team.room["id"], team.head, team.ids["head"])
    tola_mid = membership_id_for(client, team.room["id"], team.head, team.ids["tola"])
    kemi = auth_headers(client, email="kemi@example.com", name="Kemi")
    pending = request_join(client, kemi, team.room["invite_code"]).json()["membership_id"]

    for target in (head_mid, pending, str(uuid.uuid4())):
        r = client.post(url(team, "/transfer-head"), json={"membership_id": target}, headers=team.head)
        assert "membership_id" in err(r, 422)["fields"]
    err(client.post(url(team, "/transfer-head"), json={"membership_id": tola_mid}, headers=team.femi), 403)
    db.add(TempHead(room_id=uuid.UUID(team.room["id"]), user_id=uuid.UUID(team.ids["femi"]),
                    granted_by=uuid.UUID(team.ids["head"]), expires_at=utcnow() + timedelta(days=1)))
    db.commit()
    err(client.post(url(team, "/transfer-head"), json={"membership_id": tola_mid}, headers=team.femi), 403)  # temp head


def test_transfer_to_someone_in_another_room_is_422(client):
    team = make_team(client)
    other = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other, "Elsewhere")
    foreign = membership_id_for(client, other_room["id"], other, client.get(f"{API}/me", headers=other).json()["id"])
    r = client.post(url(team, "/transfer-head"), json={"membership_id": foreign}, headers=team.head)
    assert "membership_id" in err(r, 422)["fields"]


# =========================================================== delete

def everything_in(db, room_id):
    rid = uuid.UUID(room_id)
    task_ids = select(Task.id).where(Task.room_id == rid)
    return {
        "rooms": db.scalar(select(func.count()).select_from(Room).where(Room.id == rid)),
        "memberships": db.scalar(select(func.count()).select_from(Membership).where(Membership.room_id == rid)),
        "tags": db.scalar(select(func.count()).select_from(Tag).where(Tag.room_id == rid)),
        "tasks": db.scalar(select(func.count()).select_from(Task).where(Task.room_id == rid)),
        "stages": db.scalar(select(func.count()).select_from(Stage).where(Stage.task_id.in_(task_ids))),
        "messages": db.scalar(select(func.count()).select_from(Message).where(Message.room_id == rid)),
        "templates": db.scalar(select(func.count()).select_from(TaskTemplate).where(TaskTemplate.room_id == rid)),
        "updates": db.scalar(select(func.count()).select_from(ProgressUpdate).where(ProgressUpdate.task_id.in_(task_ids))),
    }


def test_delete_removes_everything_in_the_room_only(client, db):
    team = make_team(client)
    task = create_task(client, team, stages=[{"title": "A", "assignee_ids": [team.ids["femi"]]}])
    client.post(url(team, f"/tasks/{task['id']}/stages/{task['stages'][0]['id']}/updates"), json={"note": "x"}, headers=team.femi)
    client.post(url(team, "/templates"), json={"name": "T", "stages": [{"title": "S"}]}, headers=team.head)
    send(client, team, team.femi, "hello")
    other = auth_headers(client, email="other@example.com", name="Other")
    keep = create_room(client, other, "Keep me")
    join_and_approve(client, keep, other, team.femi)

    r = client.request("DELETE", url(team), json={"confirm_name": "  studio ALPHA "}, headers=team.head)
    assert r.status_code == 204
    assert set(everything_in(db, team.room["id"]).values()) == {0}
    assert db.scalar(select(func.count()).select_from(TemplateStage)) == 0
    assert client.get(url(team), headers=team.head).status_code == 404
    assert [x["name"] for x in client.get(f"{API}/me", headers=team.femi).json()["rooms"]] == ["Keep me"]
    assert everything_in(db, keep["id"])["rooms"] == 1


def test_delete_needs_the_right_name_and_the_head(client):
    team = make_team(client)
    r = client.request("DELETE", url(team), json={"confirm_name": "Studio Beta"}, headers=team.head)
    assert "confirm_name" in err(r, 422)["fields"]
    err(client.request("DELETE", url(team), json={"confirm_name": "Studio Alpha"}, headers=team.femi), 403)
    assert client.request("DELETE", url(team), json={}, headers=team.head).status_code == 422
    assert client.get(url(team), headers=team.head).status_code == 200


# =========================================================== live events

@pytest.fixture
def lc(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def drain(ws):
    import time
    time.sleep(0.05)
    ws.send_json({"type": "ping"})
    out = []
    while True:
        m = ws.receive_json()
        if m["type"] == "pong":
            return out
        out.append(m)


def socket(client, headers):
    ws = client.websocket_connect(f"{API}/ws")
    s = ws.__enter__()
    s.send_json({"type": "auth", "token": headers["Authorization"].split()[1]})
    assert s.receive_json()["type"] == "ready"
    return ws, s


def test_live_events_for_leave_and_delete(lc):
    team = make_team(lc)
    tola_cm, tola = socket(lc, team.tola)
    femi_cm, femi = socket(lc, team.femi)
    try:
        lc.post(url(team, "/leave"), headers=team.tola)
        lost = [m for m in drain(tola) if m["type"] == "room_access_lost"]
        assert [(m["reason"], m["room_id"]) for m in lost] == [("left", team.room["id"])]
        assert "room_changed" in [m["type"] for m in drain(femi)]

        lc.request("DELETE", url(team), json={"confirm_name": "Studio Alpha"}, headers=team.head)
        lost = [m for m in drain(femi) if m["type"] == "room_access_lost"]
        assert [m["reason"] for m in lost] == ["room_deleted"]
    finally:
        tola_cm.__exit__(None, None, None)
        femi_cm.__exit__(None, None, None)


def test_removal_now_says_why(lc):
    team = make_team(lc)
    cm, tola = socket(lc, team.tola)
    try:
        mid = membership_id_for(lc, team.room["id"], team.head, team.ids["tola"])
        lc.delete(url(team, f"/members/{mid}"), headers=team.head)
        lost = [m for m in drain(tola) if m["type"] == "room_access_lost"]
        assert [m["reason"] for m in lost] == ["removed"]
    finally:
        cm.__exit__(None, None, None)
