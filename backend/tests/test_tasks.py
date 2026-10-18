import uuid

from sqlalchemy import func, select

from app.models.task import Stage, StageAssignee, Task
from tests.conftest import (
    FAR_FUTURE, auth_headers, create_room, create_tag, create_task, get_task, make_team, post_task, task_body,
)

API = "/api/v1"


def tasks_url(team):
    return f"{API}/rooms/{team.room['id']}/tasks"


# ---------- create ----------

def test_create_task_returns_full_detail(client):
    team = make_team(client)
    task = create_task(client, team)

    assert task["title"] == "Product promo video"
    assert task["description"] == "30s cut for Instagram"
    assert task["due_date"] == FAR_FUTURE
    assert task["start_date"] is None
    assert task["approval_status"] == "approved"
    assert task["status"] == "not_started"
    assert (task["progress"], task["stages_done"], task["stages_total"]) == (0, 0, 3)
    assert task["current_stage_title"] == "Script"
    assert task["current_stage_ids"] == [task["stages"][0]["id"]]
    assert task["is_overdue"] is False and task["is_blocked"] is False
    assert task["created_by"]["name"] == "Ada"
    assert task["completed_at"] is None

    stages = task["stages"]
    assert [s["title"] for s in stages] == ["Script", "Shoot", "Edit"]
    assert [s["position"] for s in stages] == [1, 2, 3]
    assert [s["step"] for s in stages] == [1, 2, 3]
    assert [s["status"] for s in stages] == ["todo", "locked", "locked"]
    assert stages[0]["tag"]["name"] == "Content Writer"
    assert all(s["parallel_with_previous"] is False for s in stages)


def test_head_sees_manager_controls_but_is_not_a_participant(client):
    team = make_team(client)
    stages = create_task(client, team)["stages"]
    assert stages[0]["allowed_statuses"] == ["in_progress", "done"]
    assert stages[1]["allowed_statuses"] == ["todo", "in_progress"]  # locked: head may unlock early
    assert all(s["involves_me"] is False for s in stages)
    assert all(s["can_update_status"] is True for s in stages)


def test_participants_by_tag_see_only_their_stage_as_theirs(client):
    team = make_team(client)
    task = create_task(client, team)
    as_femi = get_task(client, team, task, team.femi)["stages"]
    assert [s["involves_me"] for s in as_femi] == [True, False, False]
    assert as_femi[0]["allowed_statuses"] == ["in_progress", "done"]
    assert as_femi[1]["allowed_statuses"] == [] and as_femi[1]["can_update_status"] is False

    as_tola = get_task(client, team, task, team.tola)["stages"]
    assert [s["involves_me"] for s in as_tola] == [False, False, True]
    assert as_tola[2]["allowed_statuses"] == []  # locked, and participants can't unlock


def test_participants_by_assignment_without_tag(client):
    team = make_team(client)
    stages = [{"title": "Review", "assignee_ids": [team.ids["femi"], team.ids["tola"]]}]
    task = create_task(client, team, stages=stages)
    s = task["stages"][0]
    assert [a["name"] for a in s["assignees"]] == ["Femi", "Tola"]  # sorted by name
    assert s["tag"] is None
    assert get_task(client, team, task, team.tola)["stages"][0]["involves_me"] is True


def test_parallel_stages_share_a_step_and_unlock_together(client):
    team = make_team(client)
    stages = [
        {"title": "Shoot"},
        {"title": "Graphics"},
        {"title": "Music", "parallel_with_previous": True},
        {"title": "Export"},
    ]
    task = create_task(client, team, stages=stages)
    s = task["stages"]
    assert [x["step"] for x in s] == [1, 2, 2, 3]
    assert [x["status"] for x in s] == ["todo", "locked", "locked", "locked"]
    assert [x["parallel_with_previous"] for x in s] == [False, False, True, False]


def test_create_with_start_date_and_stage_dates(client):
    team = make_team(client)
    task = create_task(
        client, team, start_date="2099-10-01T09:00:00Z",
        stages=[{"title": "Script", "due_date": "2099-10-10T17:00:00Z"}],
    )
    assert task["start_date"] == "2099-10-01T09:00:00Z"
    assert task["stages"][0]["due_date"] == "2099-10-10T17:00:00Z"


def test_dates_with_offsets_are_normalised_to_utc(client):
    team = make_team(client)
    task = create_task(client, team, due_date="2099-10-30T18:00:00+01:00")
    assert task["due_date"] == "2099-10-30T17:00:00Z"


def test_create_cleans_title_and_empty_description(client):
    team = make_team(client)
    task = create_task(client, team, title="  Product   promo  ", description="   ")
    assert task["title"] == "Product promo"
    assert task["description"] is None


# ---------- create: validation ----------

def fields_of(r):
    assert r.status_code == 422, r.text
    return r.json()["error"]["fields"]


def test_missing_and_blank_task_fields(client):
    team = make_team(client)
    r = client.post(tasks_url(team), json={"title": "   ", "stages": task_body(team)["stages"]}, headers=team.head)
    f = fields_of(r)
    assert "title" in f and "due_date" in f


def test_naive_datetime_is_rejected_with_a_helpful_message(client):
    team = make_team(client)
    f = fields_of(post_task(client, team, due_date="2099-10-30T17:00:00"))
    assert "timezone" in f["due_date"]


def test_stage_count_errors_are_under_fields_stages(client):
    team = make_team(client)
    assert "stages" in fields_of(post_task(client, team, stages=[]))
    assert "stages" in fields_of(post_task(client, team, stages=[{"title": f"S{i}"} for i in range(31)]))


def test_thirty_stages_is_allowed(client):
    team = make_team(client)
    task = create_task(client, team, stages=[{"title": f"S{i}"} for i in range(30)])
    assert task["stages_total"] == 30


def test_stage_errors_use_zero_based_indices(client):
    team = make_team(client)
    f = fields_of(post_task(client, team, stages=[{"title": "Ok"}, {"title": "   "}, {"title": "Fine"}]))
    assert "stages.1.title" in f and "stages.0.title" not in f


def test_start_after_due_and_stage_due_after_task_due(client):
    team = make_team(client)
    f = fields_of(
        post_task(
            client, team, start_date="2099-12-01T00:00:00Z",
            stages=[{"title": "A"}, {"title": "B", "due_date": "2100-01-01T00:00:00Z"}],
        )
    )
    assert "start_date" in f
    assert "stages.1.due_date" in f


def test_first_stage_cannot_be_parallel(client):
    team = make_team(client)
    f = fields_of(post_task(client, team, stages=[{"title": "A", "parallel_with_previous": True}]))
    assert "stages.0.parallel_with_previous" in f


def test_tag_and_assignee_must_belong_to_this_room(client):
    team = make_team(client)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    foreign_tag = create_tag(client, other_room["id"], other_head, "Foreign")
    pending = auth_headers(client, email="pending@example.com", name="Pending")
    from tests.conftest import request_join, user_id_of
    request_join(client, pending, team.room["invite_code"])  # pending is NOT an active member

    f = fields_of(
        post_task(
            client, team,
            stages=[
                {"title": "A", "tag_id": foreign_tag["id"]},
                {"title": "B", "assignee_ids": [user_id_of(client, pending)]},
                {"title": "C", "assignee_ids": [user_id_of(client, other_head)]},
                {"title": "D", "tag_id": str(uuid.uuid4())},
            ],
        )
    )
    assert {"stages.0.tag_id", "stages.1.assignee_ids", "stages.2.assignee_ids", "stages.3.tag_id"} <= set(f)


def test_several_errors_are_reported_together(client):
    team = make_team(client)
    f = fields_of(
        post_task(
            client, team, start_date="2100-01-01T00:00:00Z",
            stages=[{"title": "A", "parallel_with_previous": True, "due_date": "2100-06-01T00:00:00Z"}],
        )
    )
    assert {"start_date", "stages.0.parallel_with_previous", "stages.0.due_date"} <= set(f)


# ---------- create: permissions ----------

def test_a_member_creating_a_task_makes_a_pending_proposal(client):
    team = make_team(client)
    r = post_task(client, team, headers=team.femi)
    assert r.status_code == 201
    assert r.json()["approval_status"] == "pending"  # phase 4: proposals (see test_proposals.py)


def test_non_member_gets_404(client):
    team = make_team(client)
    stranger = auth_headers(client, email="stranger@example.com", name="Stranger")
    assert post_task(client, team, headers=stranger).status_code == 404
    assert client.get(tasks_url(team), headers=stranger).status_code == 404


# ---------- read ----------

def test_any_member_can_read_a_task(client):
    team = make_team(client)
    task = create_task(client, team)
    assert get_task(client, team, task, team.femi)["id"] == task["id"]


def test_unknown_task_and_task_from_another_room_are_404(client):
    team = make_team(client)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other = make_other_room_task(client, other_head)

    assert client.get(f"{tasks_url(team)}/{uuid.uuid4()}", headers=team.head).status_code == 404
    assert client.get(f"{tasks_url(team)}/{other['id']}", headers=team.head).status_code == 404  # not leaked


def make_other_room_task(client, other_head):
    room = create_room(client, other_head, "Other room")
    r = client.post(
        f"{API}/rooms/{room['id']}/tasks",
        json={"title": "Secret", "due_date": FAR_FUTURE, "stages": [{"title": "Only"}]},
        headers=other_head,
    )
    assert r.status_code == 201, r.text
    return r.json()


# ---------- update ----------

def patch(client, team, task, headers=None, **body):
    return client.patch(f"{tasks_url(team)}/{task['id']}", json=body, headers=headers or team.head)


def test_update_title_description_and_dates(client):
    team = make_team(client)
    task = create_task(client, team)

    r = patch(client, team, task, title="  New   title ", description="Updated", start_date="2099-10-02T08:00:00Z")
    assert r.status_code == 200
    body = r.json()
    assert (body["title"], body["description"], body["start_date"]) == ("New title", "Updated", "2099-10-02T08:00:00Z")
    assert body["stages_total"] == 3  # full detail comes back

    r = patch(client, team, task, description=None, start_date=None)
    assert r.json()["description"] is None and r.json()["start_date"] is None


def test_update_only_changes_what_is_sent(client):
    team = make_team(client)
    task = create_task(client, team)
    r = patch(client, team, task, title="Only the title")
    assert r.json()["description"] == "30s cut for Instagram"
    assert r.json()["due_date"] == FAR_FUTURE


def test_update_validation(client):
    team = make_team(client)
    task = create_task(client, team, stages=[{"title": "A", "due_date": "2099-10-20T00:00:00Z"}])

    assert "due_date" in fields_of(patch(client, team, task, due_date="2099-10-10T00:00:00Z"))  # earlier than a stage's due
    assert "due_date" in fields_of(patch(client, team, task, due_date=None))
    assert "title" in fields_of(patch(client, team, task, title=None))
    assert "start_date" in fields_of(patch(client, team, task, start_date="2100-01-01T00:00:00Z"))


def test_member_cannot_update_or_delete(client):
    team = make_team(client)
    task = create_task(client, team)
    assert patch(client, team, task, headers=team.femi, title="Hacked").status_code == 403
    assert client.delete(f"{tasks_url(team)}/{task['id']}", headers=team.femi).status_code == 403
    assert get_task(client, team, task)["title"] == "Product promo video"


# ---------- delete ----------

def test_delete_task_removes_stages_and_assignments(client, db):
    team = make_team(client)
    task = create_task(client, team, stages=[{"title": "A", "assignee_ids": [team.ids["femi"]]}, {"title": "B"}])
    other = create_task(client, team, title="Keep me")

    assert client.delete(f"{tasks_url(team)}/{task['id']}", headers=team.head).status_code == 204
    assert client.get(f"{tasks_url(team)}/{task['id']}", headers=team.head).status_code == 404

    assert db.scalar(select(func.count()).select_from(Task)) == 1
    assert db.scalar(select(func.count()).select_from(Stage)) == 3  # only the kept task's stages remain
    assert db.scalar(select(func.count()).select_from(StageAssignee)) == 0
    assert get_task(client, team, other)["title"] == "Keep me"


def test_delete_unknown_or_foreign_task_is_404(client):
    team = make_team(client)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other = make_other_room_task(client, other_head)
    assert client.delete(f"{tasks_url(team)}/{other['id']}", headers=team.head).status_code == 404
    assert client.delete(f"{tasks_url(team)}/{uuid.uuid4()}", headers=team.head).status_code == 404


# ---------- overdue ----------

def test_overdue_task_and_stage_flags(client):
    team = make_team(client)
    task = create_task(client, team, due_date="2020-01-10T00:00:00Z", stages=[{"title": "A", "due_date": "2020-01-05T00:00:00Z"}])
    assert task["is_overdue"] is True
    assert task["stages"][0]["is_overdue"] is True

    from tests.conftest import put_status
    done = put_status(client, team, task, task["stages"][0], "done", team.head).json()
    assert done["is_overdue"] is False  # finished work is never overdue
    assert done["stages"][0]["is_overdue"] is False
