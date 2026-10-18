"""GET /me/tasks, the blocked filter, and mine_actionable on rooms."""
import uuid
from datetime import timedelta
from types import SimpleNamespace

from app.models.room import TempHead
from app.utils.time import utcnow
from tests.conftest import (
    auth_headers, create_room, create_tag, create_task, join_and_approve, make_team, membership_id_for,
    put_status, request_join,
)

API = "/api/v1"


def setup(client):
    """Room A (Studio Alpha): Ada head, Femi = Content Writer, Tola = Video Editor.
    Room B (Side project): Bola head, Femi = Writer there. Tola is not in B."""
    team = make_team(client)
    bola = auth_headers(client, email="bola@example.com", name="Bola")
    room_b = create_room(client, bola, "Side project")
    join_and_approve(client, room_b, bola, team.femi)
    writer = create_tag(client, room_b["id"], bola, "Writer")
    femi_mid_b = membership_id_for(client, room_b["id"], bola, team.ids["femi"])
    client.patch(f"{API}/rooms/{room_b['id']}/members/{femi_mid_b}", json={"tag_ids": [writer["id"]]}, headers=bola)

    promo = create_task(client, team, due_date="2099-01-10T00:00:00Z")  # Script(CW) Shoot(Videographer) Edit(VE)
    tola_only = create_task(client, team, title="Not Femi's", due_date="2099-01-11T00:00:00Z",
                            stages=[{"title": "X", "assignee_ids": [team.ids["tola"]]}])
    r = client.post(f"{API}/rooms/{room_b['id']}/tasks", headers=bola, json={
        "title": "Blog post", "due_date": "2099-01-12T00:00:00Z",
        "stages": [{"title": "Draft", "tag_id": writer["id"]}, {"title": "Review", "assignee_ids": [team.ids["femi"]]}],
    })
    assert r.status_code == 201, r.text
    team_b = SimpleNamespace(head=bola, room=room_b, tags={"Writer": writer}, ids=team.ids)
    return SimpleNamespace(team=team, bola=bola, room_b=room_b, team_b=team_b, promo=promo, tola_only=tola_only, blog=r.json())


def mine(client, headers, **params):
    r = client.get(f"{API}/me/tasks", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def titles(page):
    return [t["title"] for t in page["items"]]


# ---------- scope ----------

def test_default_scope_is_my_tasks_across_all_my_rooms(client):
    s = setup(client)
    page = mine(client, s.team.femi)
    assert titles(page) == ["Product promo video", "Blog post"]
    assert [t["room"]["name"] for t in page["items"]] == ["Studio Alpha", "Side project"]
    assert all(t["involves_me"] for t in page["items"])
    assert page["total"] == 2


def test_item_is_the_room_list_item_plus_room_and_my_stages(client):
    s = setup(client)
    item = mine(client, s.team.femi)["items"][0]
    room_item = client.get(f"{API}/rooms/{s.team.room['id']}/tasks", headers=s.team.femi).json()["items"][0]
    extra = set(item) - set(room_item)
    assert extra == {"room", "my_stages"}
    assert {k: item[k] for k in room_item} == room_item  # identical shared fields


def test_my_stages_carry_tag_assignment_and_permissions(client):
    s = setup(client)
    promo, blog = mine(client, s.team.femi)["items"]

    (script,) = promo["my_stages"]
    assert (script["title"], script["status"], script["step"]) == ("Script", "todo", 1)
    assert script["tag"]["name"] == "Content Writer" and script["assigned_to_me"] is False
    assert script["allowed_statuses"] == ["in_progress", "done"]
    assert script["blocked_reason"] is None and script["is_overdue"] is False

    draft, review = blog["my_stages"]
    assert (draft["title"], draft["tag"]["name"], draft["assigned_to_me"]) == ("Draft", "Writer", False)
    assert (review["title"], review["tag"], review["assigned_to_me"], review["status"]) == ("Review", None, True, "locked")
    assert review["allowed_statuses"] == []  # locked, and Femi is a plain member in B


def test_a_stage_can_be_both_assigned_to_me_and_carry_my_tag(client):
    team = make_team(client)
    create_task(client, team, stages=[{"title": "Both", "tag_id": team.tags["Content Writer"]["id"], "assignee_ids": [team.ids["femi"]]}])
    (stage,) = mine(client, team.femi)["items"][0]["my_stages"]
    assert stage["assigned_to_me"] is True and stage["tag"]["name"] == "Content Writer"


def test_scope_all_includes_every_task_in_my_rooms(client):
    s = setup(client)
    page = mine(client, s.team.femi, scope="all")
    assert titles(page) == ["Product promo video", "Not Femi's", "Blog post"]
    not_mine = page["items"][1]
    assert not_mine["involves_me"] is False and not_mine["my_stages"] == []


def test_head_with_no_stages_has_an_empty_my_tasks(client):
    s = setup(client)
    assert mine(client, s.team.head)["items"] == []
    assert titles(mine(client, s.team.head, scope="all")) == ["Product promo video", "Not Femi's"]  # not room B


# ---------- actionable ----------

def test_actionable_means_one_of_my_stages_is_todo_in_progress_or_blocked(client):
    s = setup(client)
    assert titles(mine(client, s.team.femi, actionable="true")) == ["Product promo video", "Blog post"]
    # Tola: 'X' is todo (actionable); Edit is locked (not yet)
    assert titles(mine(client, s.team.tola)) == ["Product promo video", "Not Femi's"]
    assert titles(mine(client, s.team.tola, actionable="true")) == ["Not Femi's"]

    put_status(client, s.team, s.promo, s.promo["stages"][0], "done", s.team.femi)  # Femi's only stage in promo
    assert titles(mine(client, s.team.femi, actionable="true")) == ["Blog post"]
    assert titles(mine(client, s.team.femi)) == ["Product promo video", "Blog post"]  # still hers, just not waiting on her


def test_blocked_stages_count_as_actionable(client):
    s = setup(client)
    script = s.promo["stages"][0]
    put_status(client, s.team, s.promo, script, "in_progress", s.team.femi)
    put_status(client, s.team, s.promo, script, "blocked", s.team.femi, reason="Need the brief")
    item = mine(client, s.team.femi, actionable="true")["items"][0]
    assert item["title"] == "Product promo video"
    assert item["my_stages"][0]["blocked_reason"] == "Need the brief"


# ---------- room filter and isolation ----------

def test_room_filter_and_rooms_i_am_not_active_in(client):
    s = setup(client)
    assert titles(mine(client, s.team.femi, room=s.room_b["id"])) == ["Blog post"]

    r = client.get(f"{API}/me/tasks", params={"room": str(uuid.uuid4())}, headers=s.team.femi)
    assert r.status_code == 404
    # Tola asks to join B but isn't approved yet: still 404, and nothing from B leaks
    request_join(client, s.team.tola, s.room_b["invite_code"])
    assert client.get(f"{API}/me/tasks", params={"room": s.room_b["id"]}, headers=s.team.tola).status_code == 404
    assert "Blog post" not in titles(mine(client, s.team.tola, scope="all"))


def test_removal_from_a_room_removes_its_tasks_from_my_tasks(client):
    s = setup(client)
    mid = membership_id_for(client, s.room_b["id"], s.bola, s.team.ids["femi"])
    client.delete(f"{API}/rooms/{s.room_b['id']}/members/{mid}", headers=s.bola)
    assert titles(mine(client, s.team.femi)) == ["Product promo video"]
    assert titles(mine(client, s.team.femi, scope="all")) == ["Product promo video", "Not Femi's"]


def test_allowed_statuses_use_my_permissions_in_each_room(client, db):
    s = setup(client)
    # Femi is a member in A but temp head in B
    db.add(TempHead(room_id=uuid.UUID(s.room_b["id"]), user_id=uuid.UUID(s.team.ids["femi"]),
                    granted_by=uuid.UUID(s.team.ids["head"]), expires_at=utcnow() + timedelta(hours=1)))
    db.commit()
    create_task(client, s.team, title="Second in A", due_date="2099-01-13T00:00:00Z",
                stages=[{"title": "First"}, {"title": "Second", "assignee_ids": [s.team.ids["femi"]]}])

    items = {t["title"]: t for t in mine(client, s.team.femi)["items"]}
    assert items["Second in A"]["my_stages"][0]["allowed_statuses"] == []  # locked, member in A
    review = items["Blog post"]["my_stages"][1]
    assert review["status"] == "locked" and review["allowed_statuses"] == ["todo", "in_progress"]  # temp head in B


# ---------- filters ----------

def test_window_status_overdue_and_blocked_filters(client):
    s = setup(client)
    window = {"from": "2099-01-12T00:00:00Z", "to": "2099-01-13T00:00:00Z"}
    assert titles(mine(client, s.team.femi, **window)) == ["Blog post"]

    put_status(client, s.team, s.promo, s.promo["stages"][0], "in_progress", s.team.femi)
    assert titles(mine(client, s.team.femi, status="in_progress")) == ["Product promo video"]
    assert titles(mine(client, s.team.femi, status="not_started")) == ["Blog post"]

    late = create_task(client, s.team, title="Late", due_date="2020-01-01T00:00:00Z",
                       stages=[{"title": "S", "tag_id": s.team.tags["Content Writer"]["id"]}])
    assert titles(mine(client, s.team.femi, overdue="true")) == ["Late"]

    draft = s.blog["stages"][0]
    put_status(client, s.team_b, s.blog, draft, "in_progress", s.team.femi)
    put_status(client, s.team_b, s.blog, draft, "blocked", s.team.femi, reason="Waiting on Bola")
    assert titles(mine(client, s.team.femi, blocked="true")) == ["Blog post"]
    assert late["id"]  # used


def test_blocked_filter_on_the_room_list(client):
    s = setup(client)
    draft = s.blog["stages"][0]
    put_status(client, s.team_b, s.blog, draft, "in_progress", s.bola)
    put_status(client, s.team_b, s.blog, draft, "blocked", s.bola, reason="x")
    got = client.get(f"{API}/rooms/{s.room_b['id']}/tasks", params={"blocked": "true"}, headers=s.bola).json()
    assert [t["title"] for t in got["items"]] == ["Blog post"]
    got_a = client.get(f"{API}/rooms/{s.team.room['id']}/tasks", params={"blocked": "true"}, headers=s.team.head).json()
    assert got_a["items"] == []


def test_validation_and_auth(client):
    s = setup(client)
    for params in ({"scope": "bogus"}, {"limit": 501}, {"from": "2099-01-01T00:00:00"}, {"status": "nope"}):
        r = client.get(f"{API}/me/tasks", params=params, headers=s.team.femi)
        assert r.status_code == 422, params
    assert client.get(f"{API}/me/tasks").status_code == 401
    assert mine(client, s.team.femi, limit=500)["limit"] == 500


def test_paging_reports_the_true_total(client):
    s = setup(client)
    page = mine(client, s.team.femi, limit=1, page=2)
    assert titles(page) == ["Blog post"] and page["total"] == 2


# ---------- mine_actionable badges ----------

def badges(client, headers):
    return {r["name"]: r["mine_actionable"] for r in client.get(f"{API}/me", headers=headers).json()["rooms"]}


def test_mine_actionable_per_room_on_me_and_rooms(client):
    s = setup(client)
    assert badges(client, s.team.femi) == {"Side project": 1, "Studio Alpha": 1}
    assert badges(client, s.team.tola) == {"Studio Alpha": 1}  # 'X' todo; Edit is still locked
    assert badges(client, s.team.head) == {"Studio Alpha": 0}

    put_status(client, s.team, s.promo, s.promo["stages"][0], "done", s.team.femi)
    assert badges(client, s.team.femi) == {"Side project": 1, "Studio Alpha": 0}

    rooms = client.get(f"{API}/rooms", headers=s.team.femi).json()["items"]
    assert {r["name"]: r["mine_actionable"] for r in rooms} == {"Side project": 1, "Studio Alpha": 0}


def test_mine_actionable_counts_tasks_not_stages(client):
    team = make_team(client)
    create_task(client, team, stages=[
        {"title": "A", "assignee_ids": [team.ids["femi"]]},
        {"title": "B", "assignee_ids": [team.ids["femi"]], "parallel_with_previous": True},
    ])
    assert badges(client, team.femi) == {"Studio Alpha": 1}  # two actionable stages, one task


def test_a_stage_unlocking_makes_it_actionable(client):
    s = setup(client)
    assert badges(client, s.team.tola)["Studio Alpha"] == 1
    for stage in s.promo["stages"][:2]:  # finish Script and Shoot, so Edit (Tola's tag) unlocks
        put_status(client, s.team, s.promo, stage, "done", s.team.head)
    assert badges(client, s.team.tola)["Studio Alpha"] == 2
