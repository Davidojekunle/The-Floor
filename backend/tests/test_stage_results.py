"""Stage results: a link to the finished work, set when marking done or afterwards, handed to the next stage."""
import pytest

from app.models.notification import Notification
from app.services import notification_email
from tests.conftest import create_task, get_task, make_team, put_status, stage_url

API = "/api/v1"
VIDEO = "https://youtu.be/dQw4w9WgXcQ"


@pytest.fixture
def team(client):
    return make_team(client)


def done_with(client, team, task, stage, headers, url=VIDEO, note=None):
    body = {"status": "done", "result_url": url, **({"result_note": note} if note else {})}
    return client.put(stage_url(team, task, stage) + "/status", json=body, headers=headers)


def test_mark_done_with_a_result(client, team):
    task = create_task(client, team)
    r = done_with(client, team, task, task["stages"][0], team.femi, note="  Final script, v3  ")
    assert r.status_code == 200, r.text
    s = r.json()["stages"][0]
    assert s["status"] == "done"
    assert s["result"]["url"] == VIDEO
    assert s["result"]["note"] == "Final script, v3"
    assert s["result"]["by"]["name"] == "Femi"
    assert s["can_set_result"] is True


def test_everyone_in_the_room_sees_the_result(client, team):
    task = create_task(client, team)
    done_with(client, team, task, task["stages"][0], team.femi)
    stage = get_task(client, team, task, team.tola)["stages"][0]
    assert stage["result"]["url"] == VIDEO
    assert stage["can_set_result"] is False  # Tola isn't on the script stage


def test_done_without_a_result_still_works(client, team):
    task = create_task(client, team)
    r = put_status(client, team, task, task["stages"][0], "done", team.femi)
    assert r.status_code == 200
    assert r.json()["stages"][0]["result"] is None


def test_only_web_links(client, team):
    task = create_task(client, team)
    r = done_with(client, team, task, task["stages"][0], team.femi, url="javascript:alert(1)")
    assert r.status_code == 422
    assert "result_url" in r.json()["error"]["fields"]
    assert get_task(client, team, task)["stages"][0]["status"] == "todo"  # nothing changed


def test_add_change_and_remove_later(client, team):
    task = create_task(client, team)
    script = task["stages"][0]
    put_status(client, team, task, script, "done", team.femi)
    url = stage_url(team, task, script) + "/result"

    r = client.put(url, json={"url": "https://drive.google.com/file/d/abc123/view", "note": "Doc"}, headers=team.femi)
    assert r.status_code == 200, r.text
    assert r.json()["stages"][0]["result"]["url"].startswith("https://drive.google.com/")

    r = client.put(url, json={"url": VIDEO}, headers=team.head)  # heads can fix it too
    assert r.json()["stages"][0]["result"] == {**r.json()["stages"][0]["result"], "url": VIDEO, "note": None}
    assert r.json()["stages"][0]["result"]["by"]["name"] == "Ada"

    r = client.put(url, json={"url": None}, headers=team.femi)
    assert r.json()["stages"][0]["result"] is None


def test_result_needs_a_done_stage(client, team):
    task = create_task(client, team)
    r = client.put(stage_url(team, task, task["stages"][0]) + "/result", json={"url": VIDEO}, headers=team.femi)
    assert r.status_code == 409


def test_result_needs_someone_on_the_stage(client, team):
    task = create_task(client, team)
    put_status(client, team, task, task["stages"][0], "done", team.femi)
    r = client.put(stage_url(team, task, task["stages"][0]) + "/result", json={"url": VIDEO}, headers=team.tola)
    assert r.status_code == 403


def test_done_again_with_a_link_saves_it(client, team):
    task = create_task(client, team)
    put_status(client, team, task, task["stages"][0], "done", team.femi)
    r = done_with(client, team, task, task["stages"][0], team.femi)
    assert r.status_code == 200 and r.json()["stages"][0]["result"]["url"] == VIDEO


def test_next_person_gets_the_result_with_their_turn(client, db, team):
    task = create_task(client, team, stages=[
        {"title": "Script", "tag_id": team.tags["Content Writer"]["id"]},
        {"title": "Edit", "tag_id": team.tags["Video Editor"]["id"]},
    ])
    done_with(client, team, task, task["stages"][0], team.femi)
    ready = db.query(Notification).filter_by(type="stage_ready", stage_title="Edit").one()
    assert ready.data == {"result_url": VIDEO, "result_stage": "Script"}
    assert notification_email._detail(ready) == [f"The result of “Script”: {VIDEO}"]


def test_chat_message_carries_the_link(client, team):
    task = create_task(client, team)
    done_with(client, team, task, task["stages"][0], team.femi)
    msgs = client.get(f"{API}/rooms/{team.room['id']}/messages", headers=team.head).json()["items"]
    done = next(m for m in msgs if m.get("event_type") == "stage_done" or (m.get("event") or {}).get("type") == "stage_done")
    assert VIDEO in str(done)


def test_result_survives_a_reopen(client, team):
    task = create_task(client, team)
    done_with(client, team, task, task["stages"][0], team.femi)
    r = put_status(client, team, task, task["stages"][0], "in_progress", team.head)
    assert r.status_code == 200, r.text
    s = r.json()["stages"][0]
    assert s["result"]["url"] == VIDEO and s["can_set_result"] is False
