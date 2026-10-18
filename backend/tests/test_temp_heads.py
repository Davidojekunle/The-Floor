"""Phase 5: grant, extend, shorten and revoke temporary head."""
import uuid
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update

from app.models.room import TempHead
from tests.conftest import (
    FAR_FUTURE, auth_headers, create_room, get_task, make_team, membership_id_for, post_task, request_join,
)

API = "/api/v1"
Z = "%Y-%m-%dT%H:%M:%SZ"


def iso(dt):
    return dt.astimezone(timezone.utc).strftime(Z)


def in_days(days):
    return iso(datetime.now(timezone.utc) + timedelta(days=days))


def end_of_day(days_from_today, tz="Africa/Lagos"):
    """What the date picker sends: 23:59:59 on that day in the head's profile timezone."""
    zone = ZoneInfo(tz)
    today = datetime.now(timezone.utc).astimezone(zone).date()
    return iso(datetime.combine(today + timedelta(days=days_from_today), time(23, 59, 59), tzinfo=zone))


def url(team, person):
    mid = membership_id_for(client=team.client, room_id=team.room["id"], headers=team.head, user_id=team.ids[person])
    return f"{API}/rooms/{team.room['id']}/members/{mid}/temp-head"


def setup(client):
    team = make_team(client)
    team.client = client
    return team


def grant(client, team, person, expires_at=None, headers=None):
    return client.put(url(team, person), json={"expires_at": expires_at or in_days(7)}, headers=headers or team.head)


def room_as(client, team, headers):
    return client.get(f"{API}/rooms/{team.room['id']}", headers=headers).json()


def err(r, status, code=None):
    assert r.status_code == status, r.text
    if code:
        assert r.json()["error"]["code"] == code
    return r.json()["error"]


# =========================================================== grant

def test_grant_returns_the_member_and_powers_apply_on_the_next_request(client):
    team = setup(client)
    expires = in_days(7)
    r = grant(client, team, "tola", expires)
    assert r.status_code == 200
    member = r.json()
    assert (member["user"]["name"], member["role"], member["temp_head_expires_at"]) == ("Tola", "temp_head", expires)

    room = room_as(client, team, team.tola)
    assert room["my_role"] == "temp_head" and room["temp_head_expires_at"] == expires
    assert "task.approve" in room["permissions"] and "join.manage" not in room["permissions"]

    created = post_task(client, team, team.tola).json()
    assert created["approval_status"] == "approved"  # creates directly now, no proposal


def test_temp_head_shows_on_the_room_switcher_and_members_list(client):
    team = setup(client)
    expires = in_days(3)
    grant(client, team, "tola", expires)
    (room,) = client.get(f"{API}/me", headers=team.tola).json()["rooms"]
    assert (room["my_role"], room["temp_head_expires_at"]) == ("temp_head", expires)
    (other,) = client.get(f"{API}/me", headers=team.femi).json()["rooms"]
    assert other["temp_head_expires_at"] is None

    rows = {m["user"]["name"]: (m["role"], m["temp_head_expires_at"])
            for m in client.get(f"{API}/rooms/{team.room['id']}/members", headers=team.femi).json()["items"]}
    assert rows == {"Ada": ("head", None), "Femi": ("member", None), "Tola": ("temp_head", expires)}


def test_a_temp_head_can_decide_proposals(client):
    team = setup(client)
    proposal = post_task(client, team, team.femi).json()
    grant(client, team, "tola")
    r = client.post(f"{API}/rooms/{team.room['id']}/tasks/{proposal['id']}/approve", headers=team.tola)
    assert r.status_code == 200 and r.json()["decided_by"]["name"] == "Tola"


# =========================================================== extend, shorten, history

def test_put_again_extends_or_shortens_and_keeps_one_active_grant(client, db):
    team = setup(client)
    grant(client, team, "tola", in_days(7))
    thirty, one = in_days(30), in_days(1)
    assert grant(client, team, "tola", thirty).json()["temp_head_expires_at"] == thirty  # extended
    assert grant(client, team, "tola", one).json()["temp_head_expires_at"] == one  # shortened

    tola = uuid.UUID(team.ids["tola"])
    active = db.scalar(select(func.count()).select_from(TempHead).where(TempHead.user_id == tola, TempHead.revoked_at.is_(None)))
    total = db.scalar(select(func.count()).select_from(TempHead).where(TempHead.user_id == tola))
    assert (active, total) == (1, 3)  # earlier grants are kept as history, ended


# =========================================================== revoke

def test_revoke_takes_effect_immediately_and_is_safe_to_repeat(client):
    team = setup(client)
    grant(client, team, "tola")
    assert client.delete(url(team, "tola"), headers=team.head).status_code == 204
    room = room_as(client, team, team.tola)
    assert (room["my_role"], room["temp_head_expires_at"]) == ("member", None)
    assert post_task(client, team, team.tola).json()["approval_status"] == "pending"  # back to proposing

    assert client.delete(url(team, "tola"), headers=team.head).status_code == 204  # again
    assert client.delete(url(team, "femi"), headers=team.head).status_code == 204  # never was one


def test_work_done_as_temp_head_stays_after_revoke(client):
    team = setup(client)
    grant(client, team, "tola")
    task = post_task(client, team, team.tola).json()
    client.delete(url(team, "tola"), headers=team.head)
    after = get_task(client, team, task, team.femi)
    assert (after["approval_status"], after["created_by"]["name"]) == ("approved", "Tola")


# =========================================================== limits (the 90-day cap is measured by DAY)

def test_the_90th_day_offered_by_a_date_picker_is_accepted(client):
    team = setup(client)
    r = grant(client, team, "tola", end_of_day(90))  # 23:59:59 local on day 90: can be ~24h past now+90d
    assert r.status_code == 200, r.text


def test_the_91st_day_is_refused(client):
    team = setup(client)
    zone = ZoneInfo("Africa/Lagos")
    today = datetime.now(timezone.utc).astimezone(zone).date()
    start_of_day_91 = iso(datetime.combine(today + timedelta(days=91), time(0, 0, 0), tzinfo=zone))
    e = err(grant(client, team, "tola", start_of_day_91), 422)
    assert "90 days" in e["fields"]["expires_at"]


def test_the_cap_follows_the_heads_timezone(client):
    team = setup(client)
    tokyo = auth_headers(client, email="tokyo@example.com", name="Kenji", timezone="Asia/Tokyo")
    room = create_room(client, tokyo, "Tokyo room")
    from tests.conftest import join_and_approve
    join_and_approve(client, room, tokyo, team.tola)
    mid = membership_id_for(client, room["id"], tokyo, team.ids["tola"])
    r = client.put(f"{API}/rooms/{room['id']}/members/{mid}/temp-head",
                   json={"expires_at": end_of_day(90, "Asia/Tokyo")}, headers=tokyo)
    assert r.status_code == 200, r.text


def test_past_missing_and_naive_dates_are_422(client):
    team = setup(client)
    for body in ({"expires_at": in_days(-1)}, {}, {"expires_at": "2099-01-01T00:00:00"}):
        r = client.put(url(team, "tola"), json=body, headers=team.head)
        assert "expires_at" in err(r, 422)["fields"], body


# =========================================================== who may

def test_only_the_head_can_grant_or_revoke(client):
    team = setup(client)
    err(grant(client, team, "femi", headers=team.tola), 403, "FORBIDDEN")  # member
    grant(client, team, "tola")
    err(grant(client, team, "femi", headers=team.tola), 403, "FORBIDDEN")  # temp head can't grant others
    err(grant(client, team, "tola", in_days(60), headers=team.tola), 403, "FORBIDDEN")  # ...or extend themselves
    err(client.delete(url(team, "tola"), headers=team.tola), 403, "FORBIDDEN")


def test_the_head_cannot_be_made_temp_head(client):
    team = setup(client)
    err(grant(client, team, "head"), 409, "ALREADY_HEAD")


def test_unknown_pending_and_foreign_memberships_are_404(client):
    team = setup(client)
    base = f"{API}/rooms/{team.room['id']}/members"
    assert client.put(f"{base}/{uuid.uuid4()}/temp-head", json={"expires_at": in_days(1)}, headers=team.head).status_code == 404

    kemi = auth_headers(client, email="kemi@example.com", name="Kemi")
    pending_mid = request_join(client, kemi, team.room["invite_code"]).json()["membership_id"]
    assert client.put(f"{base}/{pending_mid}/temp-head", json={"expires_at": in_days(1)}, headers=team.head).status_code == 404

    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    other_head_id = client.get(f"{API}/me", headers=other_head).json()["id"]
    foreign = membership_id_for(client, other_room["id"], other_head, other_head_id)
    assert client.put(f"{base}/{foreign}/temp-head", json={"expires_at": in_days(1)}, headers=team.head).status_code == 404
    assert client.delete(f"{base}/{foreign}/temp-head", headers=team.head).status_code == 404


# =========================================================== several at once, role filter

def test_several_temp_heads_at_once_and_the_role_filter(client):
    team = setup(client)
    grant(client, team, "femi")
    grant(client, team, "tola")
    members = f"{API}/rooms/{team.room['id']}/members"
    names = lambda **p: [m["user"]["name"] for m in client.get(members, params=p, headers=team.head).json()["items"]]  # noqa: E731
    assert names(role="temp_head") == ["Femi", "Tola"]
    assert names(role="head") == ["Ada"]
    assert names(role="member") == []
    client.delete(url(team, "femi"), headers=team.head)
    assert names(role="member") == ["Femi"]
    assert client.get(members, params={"role": "boss"}, headers=team.head).status_code == 422


# =========================================================== expiry

def test_expiry_needs_no_action(client, db):
    team = setup(client)
    grant(client, team, "tola")
    db.execute(update(TempHead).where(TempHead.user_id == uuid.UUID(team.ids["tola"])).values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
    db.commit()

    room = room_as(client, team, team.tola)
    assert (room["my_role"], room["temp_head_expires_at"]) == ("member", None)
    (switcher,) = client.get(f"{API}/me", headers=team.tola).json()["rooms"]
    assert switcher["temp_head_expires_at"] is None
    row = next(m for m in client.get(f"{API}/rooms/{team.room['id']}/members", headers=team.head).json()["items"] if m["user"]["name"] == "Tola")
    assert (row["role"], row["temp_head_expires_at"]) == ("member", None)
