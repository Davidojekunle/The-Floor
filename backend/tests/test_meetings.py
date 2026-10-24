"""Calls C2: scheduled meetings and the call log (contract v4). The video provider is faked."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.core.config import get_settings
from app.models.call import Call
from app.models.email import OutboxEmail
from app.services import call_service, video
from app.utils.time import utcnow
from tests.conftest import auth_headers, join_and_approve, make_team

API = "/api/v1"


@pytest.fixture
def fake(monkeypatch):
    s = get_settings()
    for k, v in {"calls_enabled": True, "video_provider": "fake", "livekit_url": "wss://test.livekit.cloud"}.items():
        monkeypatch.setattr(s, k, v)
    return video.reset_fake()


def soon(hours=24):
    return (datetime.now(timezone.utc) + timedelta(hours=hours)).replace(microsecond=0)


def meet(client, team, headers, **over):
    body = {"title": "Weekly review", "starts_at": soon().isoformat(), "duration_minutes": 45,
            "invite": {"everyone": True}}
    body.update(over)
    return client.post(f"{API}/rooms/{team.room['id']}/meetings", json=body, headers=headers)


def bell(client, headers, kind):
    return [n for n in client.get(f"{API}/me/notifications", headers=headers).json()["items"] if n["type"] == kind]


def set_start(db, call_id, at):
    db.execute(update(Call).where(Call.id == uuid.UUID(call_id))
               .values(starts_at=at, ends_at_planned=at + timedelta(minutes=45)))
    db.commit()


def test_only_heads_and_temp_heads_schedule(client, fake):
    team = make_team(client)
    r = meet(client, team, team.femi)
    assert r.status_code == 403
    assert meet(client, team, team.head).status_code == 201


def test_scheduling_tells_invitees_with_a_calendar_file(client, db, fake):
    team = make_team(client)
    r = meet(client, team, team.head, description="Go through the cut")
    assert r.status_code == 201, r.text
    m = r.json()
    assert (m["kind"], m["status"], m["duration_minutes"]) == ("scheduled", "scheduled", 45)
    assert m["invite"] == {"everyone": True, "users": [], "tags": []} and m["can_edit"] is True
    assert [n["title"] for n in bell(client, team.tola, "meeting_scheduled")] == ["Ada invited you to Weekly review"]
    assert bell(client, team.head, "meeting_scheduled") == []  # not for your own actions
    mails = db.scalars(select(OutboxEmail).where(OutboxEmail.category == "calls")).all()
    assert sorted(e.to_address for e in mails) == ["femi@example.com", "tola@example.com"]
    ics = mails[0].attachments[0]
    assert ics["filename"] == "invite.ics" and "BEGIN:VEVENT" in ics["content"] and "SUMMARY:Weekly review" in ics["content"]
    msg = client.get(f"{API}/rooms/{team.room['id']}/messages", params={"limit": 1}, headers=team.tola).json()["items"][0]
    assert msg["body"] == "Ada scheduled Weekly review" and msg["event"]["detail"]["call_id"] == m["id"]


def test_invite_by_tag_tells_only_its_holders(client, fake):
    team = make_team(client)
    r = meet(client, team, team.head, invite={"tag_ids": [team.tags["Video Editor"]["id"]]})
    assert r.status_code == 201, r.text
    assert len(bell(client, team.tola, "meeting_scheduled")) == 1
    assert bell(client, team.femi, "meeting_scheduled") == []
    assert r.json()["invite"]["tags"] == [{"id": team.tags["Video Editor"]["id"], "name": "Video Editor"}]


def test_bad_meetings_are_refused(client, fake):
    team = make_team(client)
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    assert meet(client, team, team.head, starts_at=past).json()["error"]["fields"]["starts_at"]
    assert meet(client, team, team.head, external_url="meet.google.com/x").status_code == 422
    assert meet(client, team, team.head, invite={}).status_code == 422
    outsider = auth_headers(client, email="out@example.com", name="Out")
    oid = client.get(f"{API}/me", headers=outsider).json()["id"]
    assert meet(client, team, team.head, invite={"user_ids": [oid]}).status_code == 422


def test_repeating_meetings_and_cancelling_the_rest(client, db, fake):
    team = make_team(client)
    first = soon(48)
    until = (first + timedelta(days=21)).date().isoformat()
    r = meet(client, team, team.head, starts_at=first.isoformat(), repeat={"every": "week", "until": until})
    assert r.status_code == 201, r.text
    series = db.scalars(select(Call).where(Call.series_id.is_not(None)).order_by(Call.starts_at)).all()
    assert len(series) == 4 and r.json()["repeats"] is True
    second = series[1]
    d = client.delete(f"{API}/rooms/{team.room['id']}/meetings/{second.id}", params={"following": "true"},
                      headers=team.head)
    assert d.status_code == 204
    db.expire_all()
    assert [c.status for c in db.scalars(select(Call).where(Call.series_id.is_not(None)).order_by(Call.starts_at))] \
        == ["scheduled", "cancelled", "cancelled", "cancelled"]
    assert len(bell(client, team.femi, "meeting_cancelled")) == 1  # one notice for the series


def test_joining_opens_ten_minutes_before(client, db, fake):
    team = make_team(client)
    m = meet(client, team, team.head).json()
    early = client.post(f"{API}/rooms/{team.room['id']}/calls/{m['id']}/join", headers=team.tola)
    assert early.status_code == 409 and early.json()["error"]["code"] == "CALL_NOT_OPEN"
    set_start(db, m["id"], utcnow() + timedelta(minutes=5))
    j = client.post(f"{API}/rooms/{team.room['id']}/calls/{m['id']}/join", headers=team.tola)
    assert j.status_code == 200 and j.json()["provider"] == "livekit"
    got = client.get(f"{API}/rooms/{team.room['id']}/calls/{m['id']}", headers=team.tola).json()
    assert got["status"] == "live" and len(fake.rooms) == 1
    assert client.post(f"{API}/rooms/{team.room['id']}/calls", json={}, headers=team.femi).status_code == 201  # beside it


def test_a_pasted_link_meeting_opens_the_link(client, db, fake):
    team = make_team(client)
    m = meet(client, team, team.head, external_url="https://meet.google.com/abc-defg-hij").json()
    set_start(db, m["id"], utcnow())
    j = client.post(f"{API}/rooms/{team.room['id']}/calls/{m['id']}/join", headers=team.tola).json()
    assert j == {"provider": "link", "url": "https://meet.google.com/abc-defg-hij", "server_url": None,
                 "token": None, "expires_at": None}


def test_changing_the_time_tells_invitees_and_new_invitees_get_an_invite(client, db, fake):
    team = make_team(client)
    m = meet(client, team, team.head, invite={"user_ids": [team.ids["tola"]]}).json()
    later = soon(30).isoformat()
    r = client.patch(f"{API}/rooms/{team.room['id']}/meetings/{m['id']}",
                     json={"starts_at": later, "invite": {"user_ids": [team.ids["tola"], team.ids["femi"]]}},
                     headers=team.head)
    assert r.status_code == 200, r.text
    assert [n["title"] for n in bell(client, team.tola, "meeting_updated")] == ["Ada changed Weekly review"]
    assert len(bell(client, team.femi, "meeting_scheduled")) == 1
    updated = [e for e in db.scalars(select(OutboxEmail)) if e.subject.startswith("Updated:")]
    assert "SEQUENCE:1" in updated[0].attachments[0]["content"]
    assert client.patch(f"{API}/rooms/{team.room['id']}/meetings/{m['id']}", json={"title": "x"},
                        headers=team.tola).status_code == 403


def test_clash_notes(client, fake):
    team = make_team(client)
    at = soon(50)
    meet(client, team, team.head, starts_at=at.isoformat(), invite={"user_ids": [team.ids["tola"]]})
    r = client.post(f"{API}/rooms/{team.room['id']}/meetings/check", headers=team.head, json={
        "starts_at": (at + timedelta(minutes=30)).isoformat(), "duration_minutes": 30, "invite": {"everyone": True}})
    clashes = r.json()["clashes"]
    assert [(c["user"]["name"], c["title"]) for c in clashes] == [("Tola", "Weekly review")]
    clear = client.post(f"{API}/rooms/{team.room['id']}/meetings/check", headers=team.head, json={
        "starts_at": (at + timedelta(hours=2)).isoformat(), "duration_minutes": 30, "invite": {"everyone": True}})
    assert clear.json()["clashes"] == []


def test_reminders_and_missed_meetings(client, db, fake):
    team = make_team(client)
    m = meet(client, team, team.head).json()
    set_start(db, m["id"], utcnow() + timedelta(minutes=8))
    call_service.check_calls(db)
    assert [n["title"] for n in bell(client, team.tola, "meeting_reminder")] == ["Weekly review starts in 10 minutes"]
    assert any(e.subject == "Starting soon: Weekly review" for e in db.scalars(select(OutboxEmail)))
    call_service.check_calls(db)
    assert len(bell(client, team.tola, "meeting_reminder")) == 1  # once
    set_start(db, m["id"], utcnow() - timedelta(hours=2))
    call_service.check_calls(db)
    got = client.get(f"{API}/rooms/{team.room['id']}/calls/{m['id']}", headers=team.head).json()
    assert got["status"] == "ended" and got["missed"] is True


def test_my_calendar_lists_only_my_meetings(client, fake):
    team = make_team(client)
    kemi = auth_headers(client, email="kemi@example.com", name="Kemi")
    join_and_approve(client, team.room, team.head, kemi)
    meet(client, team, team.head, invite={"user_ids": [team.ids["tola"]]})
    assert [c["title"] for c in client.get(f"{API}/me/calls", headers=team.tola).json()["items"]] == ["Weekly review"]
    assert client.get(f"{API}/me/calls", headers=kemi).json()["items"] == []


def test_meetings_are_in_the_calendar_feed(client, fake):
    team = make_team(client)
    meet(client, team, team.head)
    links = client.get(f"{API}/me/calendar-feed", headers=team.tola).json()
    feed = client.get(API + links["url"].split("/api/v1", 1)[1])
    assert feed.status_code == 200 and "SUMMARY:Weekly review" in feed.text and "UID:meeting-" in feed.text


def test_the_call_log(client, db, fake):
    team = make_team(client)
    call = client.post(f"{API}/rooms/{team.room['id']}/calls", json={}, headers=team.head).json()
    room = db.get(Call, uuid.UUID(call["id"])).provider_room
    fake.present[room] = [video.Present("s1", str(team.ids["head"]), utcnow()),
                          video.Present("s2", str(team.ids["tola"]), utcnow())]
    call_service.check_calls(db)
    db.execute(update(Call).where(Call.id == uuid.UUID(call["id"])).values(started_at=utcnow() - timedelta(minutes=12)))
    db.commit()
    client.post(f"{API}/rooms/{team.room['id']}/calls/{call['id']}/end", headers=team.head)
    log = client.get(f"{API}/rooms/{team.room['id']}/calls", headers=team.femi).json()["items"]
    assert log[0]["status"] == "ended" and log[0]["duration_minutes"] == 12
    assert [p["name"] for p in log[0]["attended"]] == ["Ada", "Tola"]
