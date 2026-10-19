"""Nudges (heads ask for an update on late, stuck or blocked stages) and automatic reminders."""
import uuid
from datetime import timedelta

import pytest

from app.models.task import Stage
from app.services import reminder_service
from app.utils.time import utcnow
from tests.conftest import create_task, get_task, make_team, messages, put_status, stage_url, task_body
from tests.test_notifications import clear

API = "/api/v1"


@pytest.fixture
def team(client):
    t = make_team(client)
    for h in (t.head, t.femi, t.tola):
        clear(client, h)
    return t


def bell(client, headers):
    r = client.get(f"{API}/me/notifications", headers=headers, params={"unread": True})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def age(db, stage_id, **kw):
    """Pretend the stage has been in its status for a while (or move its other timestamps)."""
    s = db.get(Stage, uuid.UUID(stage_id))
    for k, v in kw.items():
        setattr(s, k, v)
    db.commit()


def nudge(client, team, task, stage, headers=None, note=None):
    body = {"note": note} if note is not None else None
    return client.post(stage_url(team, task, stage) + "/nudge", json=body, headers=headers or team.head)


@pytest.fixture
def stuck(client, db, team):
    """A task whose first stage (Script, Femi's via Content Writer) has sat in To do for 4 days."""
    task = create_task(client, team)
    script = task["stages"][0]
    age(db, script["id"], status_since=utcnow() - timedelta(days=4))
    clear(client, team.femi)
    return task, script


# =========================================================== nudging

def test_a_fresh_stage_cannot_be_nudged(client, team):
    task = create_task(client, team)
    s = get_task(client, team, task)["stages"][0]
    assert (s["can_nudge"], s["nudge_kind"]) == (False, None)
    r = nudge(client, team, task, s)
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOT_NUDGEABLE"


def test_a_stuck_stage_can_be_nudged_privately(client, team, stuck):
    task, script = stuck
    s = get_task(client, team, task)["stages"][0]
    assert (s["can_nudge"], s["nudge_kind"]) == (True, "update")
    assert get_task(client, team, task, team.femi)["stages"][0]["can_nudge"] is False  # members can't nudge
    before = len(messages(client, team)["items"])

    r = nudge(client, team, task, script, note="The event is on Friday")
    assert r.status_code == 200, r.text
    (n,) = bell(client, team.femi)
    assert n["type"] == "nudged"
    assert n["title"] == "Ada asked for an update on “Script” on “Product promo video”"
    assert n["data"] == {"kind": "update", "note": "The event is on Friday"}
    mine = get_task(client, team, task, team.femi)["stages"][0]["nudge"]
    assert mine["open"] is True and mine["by"]["name"] == "Ada" and mine["note"] == "The event is on Friday"
    assert get_task(client, team, task, team.tola)["stages"][0]["nudge"] is None  # not Tola's business
    assert len(messages(client, team)["items"]) == before  # never posted in chat
    assert bell(client, team.tola) == []


def test_once_a_day(client, db, team, stuck):
    task, script = stuck
    assert nudge(client, team, task, script).status_code == 200
    r = nudge(client, team, task, script)
    assert r.status_code == 409 and r.json()["error"]["code"] == "ALREADY_NUDGED"
    assert get_task(client, team, task)["stages"][0]["can_nudge"] is False
    age(db, script["id"], last_nudged_at=utcnow() - timedelta(hours=25))
    assert nudge(client, team, task, script).status_code == 200


def test_overdue_stages_can_be_nudged_straight_away(client, db, team):
    task = create_task(client, team)
    script = task["stages"][0]
    age(db, script["id"], due_date=utcnow() - timedelta(hours=2))
    assert nudge(client, team, task, script).status_code == 200


def test_blocked_stages_get_asked_about_the_block(client, team):
    task = create_task(client, team)
    script = task["stages"][0]
    put_status(client, team, task, script, "in_progress", team.femi)
    put_status(client, team, task, script, "blocked", team.femi, reason="Waiting on the brief")
    clear(client, team.femi)
    assert get_task(client, team, task)["stages"][0]["nudge_kind"] == "block"
    assert nudge(client, team, task, script).status_code == 200
    (n,) = bell(client, team.femi)
    assert n["title"] == "Ada asked about the block on “Script” on “Product promo video”"


def test_members_cannot_nudge(client, team, stuck):
    task, script = stuck
    r = nudge(client, team, task, script, headers=team.tola)
    assert r.status_code == 403


def test_locked_and_done_stages_cannot_be_nudged(client, db, team):
    task = create_task(client, team)
    shoot = task["stages"][1]  # locked behind Script
    age(db, shoot["id"], status_since=utcnow() - timedelta(days=9))
    assert nudge(client, team, task, shoot).json()["error"]["code"] == "NOT_NUDGEABLE"


def test_nobody_on_the_stage(client, db, team):
    body = task_body(team, stages=[{"title": "Shoot", "tag_id": team.tags["Videographer"]["id"]}])  # nobody has it
    task = client.post(f"{API}/rooms/{team.room['id']}/tasks", json=body, headers=team.head).json()
    shoot = task["stages"][0]
    age(db, shoot["id"], status_since=utcnow() - timedelta(days=4))
    r = nudge(client, team, task, shoot)
    assert r.status_code == 409 and r.json()["error"]["code"] == "NOBODY_ON_STAGE"


def test_note_is_limited_to_one_line(client, team, stuck):
    task, script = stuck
    assert nudge(client, team, task, script, note="x" * 201).status_code == 422


# =========================================================== answering

def test_starting_the_stage_answers_the_nudge(client, team, stuck):
    task, script = stuck
    nudge(client, team, task, script)
    clear(client, team.head)
    put_status(client, team, task, script, "in_progress", team.femi)
    (n,) = bell(client, team.head)
    assert (n["type"], n["title"]) == ("nudge_answered", "Femi started “Script” on “Product promo video”")
    assert get_task(client, team, task, team.femi)["stages"][0]["nudge"]["open"] is False


def test_im_on_it_starts_a_todo_stage(client, team, stuck):
    task, script = stuck
    nudge(client, team, task, script)
    clear(client, team.head)
    r = client.post(stage_url(team, task, script) + "/nudge/ack", headers=team.femi)
    assert r.status_code == 200 and r.json()["stages"][0]["status"] == "in_progress"
    assert [n["title"] for n in bell(client, team.head)] == ["Femi started “Script” on “Product promo video”"]


def test_im_on_it_on_a_stage_in_progress(client, db, team):
    task = create_task(client, team)
    script = task["stages"][0]
    put_status(client, team, task, script, "in_progress", team.femi)
    age(db, script["id"], status_since=utcnow() - timedelta(days=4))
    nudge(client, team, task, script)
    clear(client, team.head)
    client.post(stage_url(team, task, script) + "/nudge/ack", headers=team.femi)
    assert [n["title"] for n in bell(client, team.head)] == ["Femi is on it: “Script” on “Product promo video”"]
    client.post(stage_url(team, task, script) + "/nudge/ack", headers=team.femi)  # already answered: nothing more
    assert len(bell(client, team.head)) == 1


def test_posting_an_update_answers_the_nudge(client, team, stuck):
    task, script = stuck
    nudge(client, team, task, script)
    clear(client, team.head)
    client.post(stage_url(team, task, script) + "/updates", json={"note": "Draft is half done"}, headers=team.femi)
    assert [n["title"] for n in bell(client, team.head)] == ["Femi posted an update on “Script” on “Product promo video”"]


def test_only_people_on_the_stage_can_say_im_on_it(client, team, stuck):
    task, script = stuck
    nudge(client, team, task, script)
    assert client.post(stage_url(team, task, script) + "/nudge/ack", headers=team.tola).status_code == 403


# =========================================================== automatic reminders

def soon_task(client, db, team, hours):
    task = create_task(client, team, due_date=(utcnow() + timedelta(hours=hours)).isoformat())
    age(db, task["stages"][0]["id"], status_since=utcnow() - timedelta(hours=3))
    clear(client, team.femi)
    return task


def test_due_soon_reminder_once(client, db, team):
    soon_task(client, db, team, hours=20)
    assert reminder_service.send_reminders(db) == 1
    (n,) = bell(client, team.femi)
    assert n["type"] == "stage_due_soon"
    assert n["title"] in ("“Script” on “Product promo video” is due tomorrow", "“Script” on “Product promo video” is due today")
    assert reminder_service.send_reminders(db) == 0
    assert bell(client, team.tola) == []  # Shoot and Edit are locked: not their turn yet


def test_moving_the_due_date_rearms_the_reminder(client, db, team):
    task = soon_task(client, db, team, hours=20)
    reminder_service.send_reminders(db)
    age(db, task["stages"][0]["id"], due_date=utcnow() + timedelta(hours=10))
    assert reminder_service.send_reminders(db) == 1


def test_overdue_reminder_once(client, db, team):
    task = soon_task(client, db, team, hours=20)
    age(db, task["stages"][0]["id"], due_date=utcnow() - timedelta(hours=1))
    assert reminder_service.send_reminders(db) == 1
    (n,) = bell(client, team.femi)
    assert (n["type"], n["title"]) == ("stage_overdue", "“Script” on “Product promo video” is overdue")
    assert reminder_service.send_reminders(db) == 0


def test_no_reminder_in_the_first_hour(client, db, team):
    task = create_task(client, team, due_date=(utcnow() + timedelta(hours=5)).isoformat())
    clear(client, team.femi)
    assert reminder_service.send_reminders(db) == 0  # it only just became Femi's turn
    age(db, task["stages"][0]["id"], status_since=utcnow() - timedelta(hours=2))
    assert reminder_service.send_reminders(db) == 1


def test_blocked_and_done_stages_get_no_reminders(client, db, team):
    task = soon_task(client, db, team, hours=20)
    script = task["stages"][0]
    put_status(client, team, task, script, "in_progress", team.femi)
    put_status(client, team, task, script, "blocked", team.femi, reason="Waiting")
    age(db, script["id"], status_since=utcnow() - timedelta(hours=3))
    assert reminder_service.send_reminders(db) == 0
