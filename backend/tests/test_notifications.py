"""L4: the bell, notification emails, settings, mutes, unsubscribe, digest, retention."""
import time
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.models.email import OutboxEmail
from app.models.notification import Notification
from app.models.task import Task
from app.models.user import User
from app.services import notification_email
from app.utils.time import utcnow
from tests.conftest import (
    auth_headers, create_room, create_task, join_and_approve, make_team, membership_id_for, put_status,
    request_join, stage_url,
)

API = "/api/v1"
LATER = timedelta(minutes=3)  # past the 2-minute grouping window


def bell(client, headers, **params):
    """Unread only, unless asked: the team fixture leaves some read items behind."""
    params.setdefault("unread", True)
    r = client.get(f"{API}/me/notifications", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def types(client, headers, **params):
    return [n["type"] for n in bell(client, headers, **params)["items"]]


def clear(client, headers):
    assert client.post(f"{API}/me/notifications/read", headers=headers).status_code == 204


def unread(client, headers):
    return client.get(f"{API}/me", headers=headers).json()["unread_notifications"]


def outbox(db, category=None):
    q = select(OutboxEmail).order_by(OutboxEmail.created_at)
    if category:
        q = q.where(OutboxEmail.category == category)
    return list(db.scalars(q))


def settings(client, headers, **changes):
    r = client.patch(f"{API}/me/notification-settings", json=changes, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def mute(client, headers, room_id):
    return client.put(f"{API}/me/notification-settings/muted-rooms/{room_id}", headers=headers)


@pytest.fixture
def team(client):
    t = make_team(client)
    for h in (t.head, t.femi, t.tola):
        clear(client, h)
    return t


# =========================================================== join requests

def test_join_request_notifies_the_head(client):
    head = auth_headers(client, email="head@example.com", name="Ada")
    room = create_room(client, head)
    bisi = auth_headers(client, email="bisi@example.com", name="Bisi")
    request_join(client, bisi, room["invite_code"])

    (n,) = bell(client, head)["items"]
    assert n["type"] == "join_requested" and n["title"] == "Bisi asked to join Studio Alpha"
    assert n["room"] == {"id": room["id"], "name": "Studio Alpha"} and n["actor"]["name"] == "Bisi"
    assert n["read"] is False and n["task"] is None
    assert unread(client, head) == 1
    assert bell(client, bisi)["items"] == []


def test_approval_notifies_the_requester(client):
    head = auth_headers(client, email="head@example.com", name="Ada")
    room = create_room(client, head)
    bisi = auth_headers(client, email="bisi@example.com", name="Bisi")
    join_and_approve(client, room, head, bisi)
    (n,) = bell(client, bisi)["items"]
    assert n["type"] == "join_approved" and "Ada approved your request to join Studio Alpha" in n["title"]


# =========================================================== proposals

def propose(client, team, headers, **kw):
    from tests.conftest import post_task
    r = post_task(client, team, headers, **kw)
    assert r.status_code == 201, r.text
    return r.json()


def task_url(team, task):
    return f"{API}/rooms/{team.room['id']}/tasks/{task['id']}"


def test_proposals_notify_approvers_then_the_proposer(client, team):
    task = propose(client, team, team.femi, title="Behind the scenes reel")
    (n,) = bell(client, team.head)["items"]
    assert n["type"] == "proposal_submitted" and n["task"]["title"] == "Behind the scenes reel"
    assert types(client, team.femi) == []  # nothing for your own action
    assert types(client, team.tola) == []  # proposals stay private, stages don't notify yet

    r = client.post(task_url(team, task) + "/reject", json={"reason": "Not this month"}, headers=team.head)
    assert r.status_code == 200, r.text
    (n,) = bell(client, team.femi)["items"]
    assert n["type"] == "proposal_rejected" and n["data"] == {"reason": "Not this month"}

    client.post(task_url(team, task) + "/resubmit", headers=team.femi)
    assert types(client, team.head)[0] == "proposal_submitted"
    client.post(task_url(team, task) + "/approve", headers=team.head)
    # approved, and Femi holds the first stage's tag, so her work can start too
    assert sorted(types(client, team.femi)) == ["proposal_approved", "proposal_rejected", "stage_ready"]


def test_temp_heads_also_hear_about_proposals(client, team):
    mid = membership_id_for(client, team.room["id"], team.head, team.ids["tola"])
    expires = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    r = client.put(f"{API}/rooms/{team.room['id']}/members/{mid}/temp-head", json={"expires_at": expires}, headers=team.head)
    assert r.status_code == 200, r.text
    (granted,) = bell(client, team.tola)["items"]
    assert granted["type"] == "temp_head_granted" and granted["data"]["expires_at"]
    clear(client, team.tola)
    propose(client, team, team.femi)
    assert types(client, team.tola) == ["proposal_submitted"]
    assert types(client, team.head) == ["proposal_submitted"]


# =========================================================== stages

def test_stage_ready_goes_to_tag_holders_as_work_reaches_them(client, team):
    task = create_task(client, team)  # Script (Femi's tag) -> Shoot (nobody) -> Edit (Tola's tag)
    (n,) = bell(client, team.femi)["items"]
    assert n["type"] == "stage_ready" and n["title"] == "“Script” on “Product promo video” is ready for you"
    assert n["stage"]["title"] == "Script" and n["task"]["id"] == task["id"]
    assert types(client, team.tola) == []  # Edit is still locked

    stages = task["stages"]
    put_status(client, team, task, stages[0], "done", team.femi)
    put_status(client, team, task, stages[1], "done", team.head)  # Shoot: the head steps in
    assert types(client, team.tola) == ["stage_ready"]
    assert types(client, team.head) == []  # the head did it


def test_newly_assigned_people_hear_once(client, team):
    task = create_task(client, team)
    clear(client, team.femi)
    shoot = task["stages"][1]
    r = client.patch(stage_url(team, task, shoot), json={"assignee_ids": [team.ids["femi"], team.ids["tola"]]},
                     headers=team.head)
    assert r.status_code == 200, r.text
    assert types(client, team.femi) == ["stage_assigned"] and types(client, team.tola) == ["stage_assigned"]
    assert "Ada assigned you to “Shoot”" in bell(client, team.tola)["items"][0]["title"]
    # saving the same assignees again tells nobody anything new
    client.patch(stage_url(team, task, shoot), json={"assignee_ids": [team.ids["femi"], team.ids["tola"]]},
                 headers=team.head)
    assert len(bell(client, team.tola)["items"]) == 1


def test_assigned_to_a_ready_stage_gets_one_notification(client, team):
    task = create_task(client, team, stages=[{"title": "Script", "assignee_ids": [team.ids["tola"]],
                                               "tag_id": team.tags["Video Editor"]["id"]}])
    assert types(client, team.tola) == ["stage_ready"]  # not stage_ready + stage_assigned


def test_assigning_yourself_tells_nobody(client, team):
    create_task(client, team, stages=[{"title": "Solo", "assignee_ids": [team.ids["head"]]}])
    assert types(client, team.head) == []


# =========================================================== room lifecycle

def test_transfer_remove_and_delete(app, client, team):
    room = team.room["id"]
    femi_mid = membership_id_for(client, room, team.head, team.ids["femi"])
    tola_mid = membership_id_for(client, room, team.head, team.ids["tola"])

    assert client.delete(f"{API}/rooms/{room}/members/{tola_mid}", headers=team.head).status_code == 204
    assert types(client, team.tola) == ["removed_from_room"]

    r = client.post(f"{API}/rooms/{room}/transfer-head", json={"membership_id": femi_mid}, headers=team.head)
    assert r.status_code == 200, r.text
    assert types(client, team.femi) == ["head_transferred"]

    r = client.request("DELETE", f"{API}/rooms/{room}", json={"confirm_name": "Studio Alpha"}, headers=team.femi)
    assert r.status_code == 204, r.text
    (n,) = bell(client, team.head)["items"]
    assert n["type"] == "room_deleted" and n["room"]["name"] == "Studio Alpha"  # still readable afterwards
    assert types(client, team.femi) == ["head_transferred"]  # the deleter gets nothing


def test_leaving_tells_the_head_about_stages_with_nobody(client, team):
    task = create_task(client, team)
    r = client.post(f"{API}/rooms/{team.room['id']}/leave", headers=team.tola)
    assert r.status_code == 204, r.text
    (n,) = bell(client, team.head)["items"]
    assert n["type"] == "stages_unassigned"
    assert n["title"] == "Tola left Studio Alpha. 1 unfinished stage has nobody on it"
    assert n["data"]["stages"] == [{"task_id": task["id"], "task_title": "Product promo video",
                                    "stage_id": task["stages"][2]["id"], "stage_title": "Edit"}]
    assert n["task"]["id"] == task["id"] and n["stage"]["title"] == "Edit"


def test_leaving_with_nothing_orphaned_tells_nobody(client, team):
    client.post(f"{API}/rooms/{team.room['id']}/leave", headers=team.tola)
    assert types(client, team.head) == []


# =========================================================== muted rooms

def test_muted_room_is_silent_on_the_bell(client, team):
    assert mute(client, team.femi, team.room["id"]).json()["muted_rooms"] == [team.room["id"]]
    assert mute(client, team.femi, team.room["id"]).status_code == 200  # safe to repeat
    create_task(client, team)
    assert types(client, team.femi) == []
    r = client.delete(f"{API}/me/notification-settings/muted-rooms/{team.room['id']}", headers=team.femi)
    assert r.json()["muted_rooms"] == []
    create_task(client, team, title="Second")
    assert types(client, team.femi) == ["stage_ready"]


def test_mute_needs_membership(client, team):
    outsider = auth_headers(client, email="out@example.com", name="Out")
    assert mute(client, outsider, team.room["id"]).status_code == 404


def test_muted_rooms_still_show_chat_badges(client, team):
    badge = lambda: client.get(f"{API}/me", headers=team.femi).json()["rooms"][0]["unread_messages"]  # noqa: E731
    mute(client, team.femi, team.room["id"])
    before = badge()
    client.post(f"{API}/rooms/{team.room['id']}/messages", json={"body": "hi"}, headers=team.head)
    assert badge() == before + 1


# =========================================================== listing and reading

def make_many(client, team, n):
    for i in range(n):
        create_task(client, team, title=f"Task {i}", stages=[{"title": "Do", "assignee_ids": [team.ids["femi"]]}])


def test_paging_newest_first(client, team):
    make_many(client, team, 5)
    first = bell(client, team.femi, limit=2)
    assert [n["task"]["title"] for n in first["items"]] == ["Task 4", "Task 3"] and first["has_more"]
    second = bell(client, team.femi, limit=2, before=first["items"][-1]["id"])
    assert [n["task"]["title"] for n in second["items"]] == ["Task 2", "Task 1"]
    last = bell(client, team.femi, limit=2, before=second["items"][-1]["id"])
    assert [n["task"]["title"] for n in last["items"]] == ["Task 0"] and not last["has_more"]


def test_list_validation(client, team):
    import uuid
    assert client.get(f"{API}/me/notifications", params={"limit": 101}, headers=team.femi).status_code == 422
    r = client.get(f"{API}/me/notifications", params={"before": str(uuid.uuid4())}, headers=team.femi)
    assert r.status_code == 422 and "before" in r.json()["error"]["fields"]


def test_marking_read(client, team):
    make_many(client, team, 4)
    items = bell(client, team.femi)["items"]
    assert unread(client, team.femi) == 4

    assert client.post(f"{API}/me/notifications/{items[0]['id']}/read", headers=team.femi).status_code == 204
    assert unread(client, team.femi) == 3
    assert client.post(f"{API}/me/notifications/{items[0]['id']}/read", headers=team.tola).status_code == 404

    # up_to: that one and everything older
    r = client.post(f"{API}/me/notifications/read", json={"up_to": items[2]["id"]}, headers=team.femi)
    assert r.status_code == 204
    assert [n["task"]["title"] for n in bell(client, team.femi, unread=True)["items"]] == ["Task 2"]
    clear(client, team.femi)
    assert unread(client, team.femi) == 0 and bell(client, team.femi, unread=True)["items"] == []
    everything = bell(client, team.femi, unread=False)["items"]
    assert len(everything) == 5 and all(n["read"] for n in everything)  # still listed (with join_approved), just read


def test_others_cannot_use_my_ids_as_cursors(client, team):
    make_many(client, team, 1)
    mine = bell(client, team.femi)["items"][0]["id"]
    assert client.get(f"{API}/me/notifications", params={"before": mine}, headers=team.tola).status_code == 422
    r = client.post(f"{API}/me/notifications/read", json={"up_to": mine}, headers=team.tola)
    assert r.status_code == 422


@pytest.fixture
def lc(app):
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_live_event(lc):
    team = make_team(lc)
    femi_token = team.femi["Authorization"].split()[1]
    with lc.websocket_connect(f"{API}/ws") as ws:
        ws.send_json({"type": "auth", "token": femi_token})
        assert ws.receive_json()["type"] == "ready"
        create_task(lc, team)
        time.sleep(0.05)
        ws.send_json({"type": "ping"})
        got = []
        while (m := ws.receive_json())["type"] != "pong":
            got.append(m)
    (event,) = [m for m in got if m["type"] == "notification_created"]
    newest = bell(lc, team.femi)["items"][0]
    assert event["room_id"] == team.room["id"] and event["notification_id"] == newest["id"]
    assert set(event) == {"type", "room_id", "notification_id", "at"}


def test_old_notifications_are_cleaned_up_after_90_days(client, db, team):
    make_many(client, team, 2)
    femi = db.scalar(select(User).where(User.email == "femi@example.com"))
    oldest = db.scalars(select(Notification).where(Notification.user_id == femi.id)
                        .order_by(Notification.created_at)).first()
    oldest.created_at = utcnow() - timedelta(days=91)
    db.commit()
    assert notification_email.purge_old(db) == 1
    assert len(bell(client, team.femi, unread=False)["items"]) == 2  # the oldest (join_approved) went


# =========================================================== settings

def test_settings_default_on_and_partial_updates(client, team):
    r = client.get(f"{API}/me/notification-settings", headers=team.femi).json()
    assert r == {"email_enabled": True, "requests": True, "decisions": True, "assignments": True,
                 "daily_digest": True, "mentions": True, "all_messages": False, "muted_rooms": []}
    assert settings(client, team.femi, daily_digest=False)["daily_digest"] is False
    after = settings(client, team.femi, assignments=False)
    assert (after["daily_digest"], after["assignments"], after["requests"]) == (False, False, True)
    r = client.patch(f"{API}/me/notification-settings", json={"requests": None}, headers=team.femi)
    assert r.status_code == 422


# =========================================================== emails

def test_nothing_is_emailed_before_the_window_closes(client, db, team):
    create_task(client, team)
    assert notification_email.flush_due(db) == 0
    assert outbox(db, "assignments") == []


def test_one_email_after_the_window(client, db, team):
    create_task(client, team)
    assert notification_email.flush_due(db, utcnow() + LATER) == 1
    (email,) = outbox(db, "assignments")
    assert email.to_address == "femi@example.com"
    assert email.subject == "“Script” on “Product promo video” is ready for you"
    task_id = db.scalar(select(Task.id))
    assert f"http://localhost:5173/rooms/{team.room['id']}/tasks/{task_id}" in email.text_body
    assert email.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert email.headers["List-Unsubscribe"].startswith("<http://localhost:8000/api/v1/unsubscribe?token=")
    assert "Turn them off" in email.html_body
    assert notification_email.flush_due(db, utcnow() + LATER) == 0  # never twice


def test_requests_within_the_window_are_grouped(client, db):
    head = auth_headers(client, email="head@example.com", name="Ada")
    room = create_room(client, head)
    for name in ("Bisi", "Chidi", "Dayo"):
        request_join(client, auth_headers(client, email=f"{name.lower()}@example.com", name=name), room["invite_code"])
    assert notification_email.flush_due(db, utcnow() + LATER) == 1
    (email,) = outbox(db, "requests")
    assert email.subject == "3 new requests on The Floor"
    for name in ("Bisi", "Chidi", "Dayo"):
        assert f"{name} asked to join Studio Alpha" in email.text_body
    assert f"http://localhost:5173/rooms/{room['id']}" in email.text_body


def test_seen_in_the_bell_means_no_email(client, db, team):
    create_task(client, team)
    clear(client, team.femi)
    notification_email.flush_due(db, utcnow() + LATER)
    assert outbox(db, "assignments") == []


def test_switched_off_category_still_rings_the_bell(client, db, team):
    settings(client, team.femi, assignments=False)
    create_task(client, team)
    assert types(client, team.femi) == ["stage_ready"]
    notification_email.flush_due(db, utcnow() + LATER)
    assert outbox(db, "assignments") == []


def test_master_switch_and_changes_during_the_window(client, db, team):
    create_task(client, team)
    settings(client, team.femi, email_enabled=False)  # switched off after it was queued
    notification_email.flush_due(db, utcnow() + LATER)
    assert outbox(db, "assignments") == []


def test_muting_during_the_window_stops_the_email(client, db, team):
    create_task(client, team)
    mute(client, team.femi, team.room["id"])
    notification_email.flush_due(db, utcnow() + LATER)
    assert outbox(db, "assignments") == []


def test_rejection_reason_is_in_the_email(client, db, team):
    task = propose(client, team, team.femi)
    client.post(task_url(team, task) + "/reject", json={"reason": "Budget"}, headers=team.head)
    notification_email.flush_due(db, utcnow() + LATER)
    (email,) = outbox(db, "decisions")
    assert "Reason: Budget" in email.text_body


# =========================================================== unsubscribe

def unsub_token(db, email="femi@example.com", category="assignments"):
    user = db.scalar(select(User).where(User.email == email))
    return notification_email.unsubscribe_token(user.id, category)


def test_opening_the_link_changes_nothing(client, db, team):
    r = client.get(f"{API}/unsubscribe", params={"token": unsub_token(db)})
    assert r.status_code == 200 and "text/html" in r.headers["content-type"]
    assert "stages assigned to you" in r.text and 'method="post"' in r.text
    assert client.get(f"{API}/me/notification-settings", headers=team.femi).json()["assignments"] is True


def test_confirming_turns_the_category_off(client, db, team):
    r = client.post(f"{API}/unsubscribe", params={"token": unsub_token(db)})
    assert r.status_code == 200 and "Done" in r.text
    s = client.get(f"{API}/me/notification-settings", headers=team.femi).json()
    assert (s["assignments"], s["requests"], s["email_enabled"]) == (False, True, True)
    assert client.post(f"{API}/unsubscribe", params={"token": unsub_token(db)}).status_code == 200  # repeatable


def test_mail_app_one_click(client, db, team):
    r = client.post(f"{API}/unsubscribe", params={"token": unsub_token(db, category="daily_digest")},
                    data={"List-Unsubscribe": "One-Click"})
    assert r.status_code == 200
    assert client.get(f"{API}/me/notification-settings", headers=team.femi).json()["daily_digest"] is False


def test_bad_unsubscribe_tokens(client, team):
    assert client.get(f"{API}/unsubscribe", params={"token": "garbage"}).status_code == 400
    access = team.femi["Authorization"].split()[1]  # a real signed token, but not an unsubscribe one
    assert client.post(f"{API}/unsubscribe", params={"token": access}).status_code == 400


# =========================================================== daily digest

# 08:05 in Lagos (UTC+1), today: "overdue" and "due soon" are judged against the real clock
LAGOS_0805 = datetime.combine(datetime.now(timezone.utc).date(), datetime.min.time().replace(hour=7, minute=5),
                              tzinfo=timezone.utc)


def digest_emails(db):
    return outbox(db, "daily_digest")


def overdue_task(client, db, team):
    task = create_task(client, team)
    import uuid
    db.execute(update(Task).where(Task.id == uuid.UUID(task["id"])).values(due_date=utcnow() - timedelta(days=1)))
    db.commit()
    return task


def test_digest_lists_overdue_work_once_a_day_at_eight_local(client, db, team):
    overdue_task(client, db, team)  # Femi's Script stage is todo
    assert notification_email.send_digests(db, LAGOS_0805 - timedelta(hours=1)) == 0  # 07:05 in Lagos
    assert notification_email.send_digests(db, LAGOS_0805) == 1  # only Femi has anything
    (email,) = digest_emails(db)
    assert email.to_address == "femi@example.com" and email.subject.startswith("Your day on The Floor:")
    assert "Overdue" in email.text_body and "Product promo video (Studio Alpha)" in email.text_body
    assert "http://localhost:5173/my-tasks" in email.text_body
    assert notification_email.send_digests(db, LAGOS_0805 + timedelta(hours=3)) == 0  # once a day
    assert notification_email.send_digests(db, LAGOS_0805 + timedelta(days=1)) == 1  # next day again


def test_digest_lists_work_due_soon(client, db, team):
    import uuid
    task = create_task(client, team)
    db.execute(update(Task).where(Task.id == uuid.UUID(task["id"])).values(due_date=utcnow() + timedelta(days=1)))
    db.commit()
    notification_email.send_digests(db, LAGOS_0805)
    (email,) = digest_emails(db)
    assert "Due in the next two days" in email.text_body and "Overdue" not in email.text_body


def test_digest_tells_heads_about_waiting_requests(client, db, team):
    outsider = auth_headers(client, email="bisi@example.com", name="Bisi")
    request_join(client, outsider, team.room["invite_code"])
    propose(client, team, team.femi)
    notification_email.send_digests(db, LAGOS_0805)
    (email,) = [e for e in digest_emails(db) if e.to_address == "head@example.com"]
    assert "1 join request in Studio Alpha" in email.text_body
    assert "1 proposal waiting in Studio Alpha" in email.text_body


def test_digest_respects_switches_and_mutes(client, db, team):
    overdue_task(client, db, team)
    settings(client, team.femi, daily_digest=False)
    assert notification_email.send_digests(db, LAGOS_0805) == 0
    settings(client, team.femi, daily_digest=True)
    mute(client, team.femi, team.room["id"])
    assert notification_email.send_digests(db, LAGOS_0805 + timedelta(days=1)) == 0


def test_digest_uses_each_persons_timezone(client, db, team):
    overdue_task(client, db, team)
    db.execute(update(User).where(User.email == "femi@example.com").values(timezone="America/New_York"))
    db.commit()
    assert notification_email.send_digests(db, LAGOS_0805) == 0  # 02:05 in New York
    assert notification_email.send_digests(db, LAGOS_0805 + timedelta(hours=6)) == 1  # 08:05 there


# =========================================================== the loop

def test_tick_runs_everything(client, db, team):
    create_task(client, team)
    db.execute(update(Notification).values(email_due_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    notification_email._last.update(digest=0.0, purge=0.0)
    notification_email.tick(db)
    assert len(outbox(db, "assignments")) == 1
