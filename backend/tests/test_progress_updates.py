"""Phase 6b: progress updates on stages."""
import uuid

from sqlalchemy import func, select

from app.models.progress import ProgressUpdate
from tests.conftest import (
    auth_headers, create_room, create_task, get_task, make_team, messages, post_task, stage_url,
)

API = "/api/v1"


def post(client, team, task, stage, headers, **body):
    body.setdefault("note", "Shot 3 of 5 scenes")
    return client.post(stage_url(team, task, stage) + "/updates", json=body, headers=headers)


def stage_feed(client, team, task, stage, headers, **params):
    r = client.get(stage_url(team, task, stage) + "/updates", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def task_feed(client, team, task, headers, **params):
    r = client.get(f"{API}/rooms/{team.room['id']}/tasks/{task['id']}/updates", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def notes(page):
    return [u["note"] for u in page["items"]]


def err(r, status, code=None):
    assert r.status_code == status, r.text
    if code:
        assert r.json()["error"]["code"] == code
    return r.json()["error"]


# =========================================================== posting

def test_participant_posts_an_update(client):
    team = make_team(client)
    task = create_task(client, team)
    r = post(client, team, task, task["stages"][0], team.femi, note="  Draft one done ", link_url="https://docs.example.com/x")
    assert r.status_code == 201
    u = r.json()
    assert (u["note"], u["link_url"], u["author"]["name"], u["stage"]["title"]) == (
        "Draft one done", "https://docs.example.com/x", "Femi", "Script")
    assert u["can_delete"] is True
    assert get_task(client, team, task)["stages"][0]["update_count"] == 1


def test_updates_can_be_posted_on_locked_stages_by_their_people(client):
    team = make_team(client)
    task = create_task(client, team)
    assert post(client, team, task, task["stages"][2], team.tola, note="Prepping the edit").status_code == 201


def test_who_may_post(client):
    team = make_team(client)
    task = create_task(client, team)
    err(post(client, team, task, task["stages"][0], team.tola), 403, "FORBIDDEN")  # not her stage
    assert post(client, team, task, task["stages"][0], team.head).status_code == 201  # stage.edit
    stranger = auth_headers(client, email="stranger@example.com", name="Stranger")
    assert post(client, team, task, task["stages"][0], stranger).status_code == 404


def test_no_updates_on_proposals(client):
    team = make_team(client)
    p = post_task(client, team, team.femi).json()
    err(post(client, team, p, p["stages"][0], team.femi), 409, "TASK_NOT_APPROVED")
    err(post(client, team, p, p["stages"][0], team.tola), 404)  # not even visible to her


def test_validation(client):
    team = make_team(client)
    task = create_task(client, team)
    s = task["stages"][0]
    for note in ("", "   ", "x" * 2001):
        assert "note" in err(post(client, team, task, s, team.femi, note=note), 422)["fields"]
    for link in ("javascript:alert(1)", "ftp://x.com/a", "not a link", "https://"):
        assert "link_url" in err(post(client, team, task, s, team.femi, link_url=link), 422)["fields"]
    assert post(client, team, task, s, team.femi, link_url="   ").json()["link_url"] is None


def test_unknown_stage_or_stage_from_another_task_is_404(client):
    team = make_team(client)
    one, two = create_task(client, team, title="One"), create_task(client, team, title="Two")
    r = client.post(f"{API}/rooms/{team.room['id']}/tasks/{one['id']}/stages/{two['stages'][0]['id']}/updates",
                    json={"note": "x"}, headers=team.head)
    assert r.status_code == 404
    r = client.post(f"{API}/rooms/{team.room['id']}/tasks/{one['id']}/stages/{uuid.uuid4()}/updates",
                    json={"note": "x"}, headers=team.head)
    assert r.status_code == 404


# =========================================================== share to chat

def test_share_to_chat_posts_a_message_referencing_the_stage(client):
    team = make_team(client)
    task = create_task(client, team)
    post(client, team, task, task["stages"][0], team.femi, note="Script is ready", link_url="https://docs.example.com/s", share_to_chat=True)
    m = messages(client, team, team.tola)["items"][0]
    assert (m["type"], m["sender"]["name"], m["body"]) == ("user", "Femi", "Script is ready\nhttps://docs.example.com/s")
    assert (m["task"]["title"], m["stage"]["title"]) == ("Product promo video", "Script")


def test_updates_stay_out_of_chat_by_default(client):
    team = make_team(client)
    task = create_task(client, team)
    before = len(messages(client, team)["items"])
    post(client, team, task, task["stages"][0], team.femi)
    assert len(messages(client, team)["items"]) == before


# =========================================================== feeds and paging

def test_stage_feed_newest_first_with_before_paging(client):
    team = make_team(client)
    task = create_task(client, team)
    s = task["stages"][0]
    for i in range(1, 6):
        post(client, team, task, s, team.femi, note=f"u{i}")
    page = stage_feed(client, team, task, s, team.tola, limit=2)
    assert notes(page) == ["u5", "u4"] and page["has_more"] is True
    page = stage_feed(client, team, task, s, team.tola, limit=2, before=page["items"][-1]["id"])
    assert notes(page) == ["u3", "u2"] and page["has_more"] is True
    page = stage_feed(client, team, task, s, team.tola, limit=2, before=page["items"][-1]["id"])
    assert notes(page) == ["u1"] and page["has_more"] is False
    assert [u["can_delete"] for u in stage_feed(client, team, task, s, team.tola)["items"]] == [False] * 5


def test_task_feed_merges_every_stage(client):
    team = make_team(client)
    task = create_task(client, team)
    post(client, team, task, task["stages"][0], team.femi, note="script")
    post(client, team, task, task["stages"][2], team.tola, note="edit prep")
    post(client, team, task, task["stages"][0], team.femi, note="script v2")
    page = task_feed(client, team, task, team.head)
    assert [(u["note"], u["stage"]["title"]) for u in page["items"]] == [
        ("script v2", "Script"), ("edit prep", "Edit"), ("script", "Script")]
    assert [s["update_count"] for s in get_task(client, team, task)["stages"]] == [2, 0, 1]


def test_cursor_from_elsewhere_is_422(client):
    team = make_team(client)
    task = create_task(client, team)
    other = post(client, team, task, task["stages"][2], team.tola).json()
    r = client.get(stage_url(team, task, task["stages"][0]) + "/updates", params={"before": other["id"]}, headers=team.head)
    assert "before" in err(r, 422)["fields"]


def test_feeds_of_proposals_are_hidden_from_others(client):
    team = make_team(client)
    p = post_task(client, team, team.femi).json()
    r = client.get(f"{API}/rooms/{team.room['id']}/tasks/{p['id']}/updates", headers=team.tola)
    assert r.status_code == 404
    assert task_feed(client, team, p, team.femi)["items"] == []


# =========================================================== delete

def test_author_or_stage_editor_deletes(client):
    team = make_team(client)
    task = create_task(client, team)
    s = task["stages"][0]
    mine = post(client, team, task, s, team.femi, note="mine").json()
    other = post(client, team, task, s, team.femi, note="other").json()
    url = lambda u: stage_url(team, task, s) + f"/updates/{u['id']}"  # noqa: E731
    err(client.delete(url(mine), headers=team.tola), 403, "FORBIDDEN")
    assert client.delete(url(mine), headers=team.femi).status_code == 204
    assert client.delete(url(mine), headers=team.femi).status_code == 204  # repeat
    assert client.delete(url(other), headers=team.head).status_code == 204
    assert stage_feed(client, team, task, s, team.head)["items"] == []
    assert get_task(client, team, task)["stages"][0]["update_count"] == 0


def test_deleting_a_stage_or_task_removes_its_updates(client, db):
    team = make_team(client)
    task = create_task(client, team)
    post(client, team, task, task["stages"][1], team.head)
    post(client, team, task, task["stages"][0], team.femi)
    client.delete(stage_url(team, task, task["stages"][1]), headers=team.head)
    assert db.scalar(select(func.count()).select_from(ProgressUpdate)) == 1
    client.delete(f"{API}/rooms/{team.room['id']}/tasks/{task['id']}", headers=team.head)
    assert db.scalar(select(func.count()).select_from(ProgressUpdate)) == 0


def test_updates_from_another_room_are_unreachable(client):
    team = make_team(client)
    bola = auth_headers(client, email="bola@example.com", name="Bola")
    room_b = create_room(client, bola, "Side project")
    theirs = client.post(f"{API}/rooms/{room_b['id']}/tasks", headers=bola,
                         json={"title": "B", "due_date": "2099-01-01T00:00:00Z", "stages": [{"title": "S"}]}).json()
    r = client.get(f"{API}/rooms/{team.room['id']}/tasks/{theirs['id']}/updates", headers=team.head)
    assert r.status_code == 404
