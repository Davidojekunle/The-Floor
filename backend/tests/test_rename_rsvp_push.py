"""Renaming a room, meeting RSVPs, the Join button on call pushes, and no updates on a locked stage."""
from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import get_settings
from app.services import video
from tests.conftest import auth_headers, join_and_approve, make_team

API = "/api/v1"


@pytest.fixture
def calls(monkeypatch):
    s = get_settings()
    for k, v in {"calls_enabled": True, "video_provider": "fake", "livekit_url": "wss://test.livekit.cloud"}.items():
        monkeypatch.setattr(s, k, v)
    return video.reset_fake()


def test_the_head_renames_the_room(client):
    team = make_team(client)
    url = f"{API}/rooms/{team.room['id']}"
    assert client.patch(url, json={"name": "Studio  Beta "}, headers=team.tola).status_code == 403
    r = client.patch(url, json={"name": "Studio  Beta "}, headers=team.head)
    assert r.status_code == 200 and r.json()["name"] == "Studio Beta"
    assert client.get(f"{API}/me", headers=team.tola).json()["rooms"][0]["name"] == "Studio Beta"
    msg = client.get(f"{url}/messages", params={"limit": 1}, headers=team.tola).json()["items"][0]
    assert msg["body"] == "Ada renamed the room to Studio Beta"
    assert msg["event"]["detail"] == {"old": "Studio Alpha", "new": "Studio Beta"}
    assert client.patch(url, json={"name": "   "}, headers=team.head).status_code == 422


def test_rsvp(client, calls):
    team = make_team(client)
    kemi = auth_headers(client, email="kemi@example.com", name="Kemi")
    join_and_approve(client, team.room, team.head, kemi)
    at = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    m = client.post(f"{API}/rooms/{team.room['id']}/meetings", headers=team.head, json={
        "title": "Weekly review", "starts_at": at, "duration_minutes": 30,
        "invite": {"user_ids": [team.ids["tola"], team.ids["femi"]]}}).json()
    url = f"{API}/rooms/{team.room['id']}/meetings/{m['id']}/rsvp"
    r = client.put(url, json={"response": "going"}, headers=team.tola)
    assert r.status_code == 200 and r.json()["rsvp"]["mine"] == "going"
    client.put(url, json={"response": "declined"}, headers=team.femi)
    view = client.get(f"{API}/rooms/{team.room['id']}/calls/{m['id']}", headers=team.head).json()["rsvp"]
    assert [p["name"] for p in view["going"]] == ["Tola"] and [p["name"] for p in view["declined"]] == ["Femi"]
    assert view["invited"] is False  # the organiser isn't asked
    assert client.put(url, json={"response": "going"}, headers=kemi).status_code == 403  # not invited
    back = client.put(url, json={"response": None}, headers=team.tola).json()["rsvp"]
    assert back["mine"] is None and back["going"] == []


def test_call_pushes_carry_a_join_button(client, db, calls, monkeypatch):
    from app.services import push_service

    sent = []
    monkeypatch.setattr(push_service, "queue", lambda db, uid, **kw: sent.append(kw))
    team = make_team(client)
    sent.clear()  # the team's join requests pushed too
    client.post(f"{API}/rooms/{team.room['id']}/calls", json={}, headers=team.head)
    assert sent and all(kw["actions"] == [{"action": "join", "title": "Join"}] for kw in sent)
    assert all("/calls/" in kw["url"] for kw in sent)
