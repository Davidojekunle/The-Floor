import uuid

from sqlalchemy import select

from app.models.task import StageAssignee
from tests.conftest import (
    auth_headers, create_room, create_tag, create_task, get_task, make_team, membership_id_for, put_status,
    stage_url,
)

API = "/api/v1"


def statuses(task):
    return [s["status"] for s in task["stages"]]


def titles(task):
    return [s["title"] for s in task["stages"]]


def err(r, status, code=None):
    assert r.status_code == status, r.text
    if code:
        assert r.json()["error"]["code"] == code, r.text
    return r.json()["error"]


# =========================================================== status: the normal flow

def test_participants_move_work_forward_and_unlock_the_next_stage(client):
    team = make_team(client)
    task = create_task(client, team)
    script = task["stages"][0]

    r = put_status(client, team, task, script, "in_progress", team.femi)
    assert r.status_code == 200
    assert statuses(r.json()) == ["in_progress", "locked", "locked"]
    assert r.json()["status"] == "in_progress"

    done = put_status(client, team, task, script, "done", team.femi).json()
    assert statuses(done) == ["done", "todo", "locked"]
    assert (done["progress"], done["stages_done"]) == (33, 1)
    assert done["current_stage_title"] == "Shoot"
    assert done["stages"][0]["completed_by"]["name"] == "Femi"
    assert done["stages"][0]["completed_at"] is not None


def test_finishing_the_last_stage_completes_the_task(client):
    team = make_team(client)
    task = create_task(client, team)
    for stage in task["stages"]:
        r = put_status(client, team, task, stage, "done", team.head)
        assert r.status_code == 200, r.text
    final = r.json()
    assert (final["status"], final["progress"]) == ("done", 100)
    assert final["current_stage_title"] is None and final["current_stage_ids"] == []
    assert final["completed_at"] is not None
    assert final["is_overdue"] is False


def test_progress_after_each_stage_of_three(client):
    team = make_team(client)
    task = create_task(client, team)
    seen = [put_status(client, team, task, s, "done", team.head).json()["progress"] for s in task["stages"]]
    assert seen == [33, 67, 100]


def test_repeating_the_same_status_is_a_safe_no_op(client):
    team = make_team(client)
    task = create_task(client, team)
    first = put_status(client, team, task, task["stages"][0], "in_progress", team.femi).json()
    again = put_status(client, team, task, task["stages"][0], "in_progress", team.femi)
    assert again.status_code == 200
    assert again.json()["stages"][0]["status"] == "in_progress"
    assert again.json()["updated_at"] == first["updated_at"]  # nothing was touched


def test_the_response_is_the_full_task_with_fresh_allowed_statuses(client):
    team = make_team(client)
    task = create_task(client, team)
    r = put_status(client, team, task, task["stages"][0], "in_progress", team.femi).json()
    assert r["stages"][0]["allowed_statuses"] == ["todo", "done", "blocked"]


# =========================================================== status: who may and may not

def test_non_participant_member_gets_403(client):
    team = make_team(client)
    task = create_task(client, team)
    err(put_status(client, team, task, task["stages"][0], "in_progress", team.tola), 403, "FORBIDDEN")


def test_a_locked_stage_cannot_be_started_by_its_own_participant(client):
    team = make_team(client)
    task = create_task(client, team)
    edit = task["stages"][2]  # Tola holds this tag, but it's locked
    err(put_status(client, team, task, edit, "in_progress", team.tola), 403, "FORBIDDEN")
    assert get_task(client, team, task)["stages"][2]["status"] == "locked"


def test_outsiders_get_404(client):
    team = make_team(client)
    task = create_task(client, team)
    stranger = auth_headers(client, email="stranger@example.com", name="Stranger")
    assert put_status(client, team, task, task["stages"][0], "done", stranger).status_code == 404


def test_head_can_move_any_stage_even_without_being_assigned(client):
    team = make_team(client)
    task = create_task(client, team)
    assert put_status(client, team, task, task["stages"][0], "done", team.head).status_code == 200


def test_assignee_without_the_tag_can_act(client):
    team = make_team(client)
    task = create_task(client, team, stages=[{"title": "Review", "assignee_ids": [team.ids["tola"]]}])
    assert put_status(client, team, task, task["stages"][0], "done", team.tola).status_code == 200
    assert put_status(client, team, task, task["stages"][0], "in_progress", team.femi).status_code == 403


# =========================================================== status: transitions

def test_invalid_transitions_are_409_with_a_stable_code(client):
    team = make_team(client)
    task = create_task(client, team)
    script = task["stages"][0]
    error = err(put_status(client, team, task, script, "blocked", team.femi, reason="x"), 409, "INVALID_TRANSITION")
    assert "todo" in error["message"] and "blocked" in error["message"]

    err(put_status(client, team, task, task["stages"][1], "done", team.head), 409, "INVALID_TRANSITION")  # locked -> done


def test_status_values_that_cannot_be_set_are_422(client):
    team = make_team(client)
    task = create_task(client, team)
    for bad in ("locked", "finished", ""):
        r = client.put(stage_url(team, task, task["stages"][0]) + "/status", json={"status": bad}, headers=team.head)
        assert r.status_code == 422 and "status" in r.json()["error"]["fields"]


def test_blocking_needs_a_reason_and_unblocking_clears_it(client):
    team = make_team(client)
    task = create_task(client, team)
    script = task["stages"][0]
    put_status(client, team, task, script, "in_progress", team.femi)

    r = put_status(client, team, task, script, "blocked", team.femi)
    assert "blocked_reason" in err(r, 422, "VALIDATION_ERROR")["fields"]
    r = put_status(client, team, task, script, "blocked", team.femi, reason="   ")
    assert r.status_code == 422

    blocked = put_status(client, team, task, script, "blocked", team.femi, reason="Waiting for the brief").json()
    assert blocked["is_blocked"] is True
    assert blocked["stages"][0]["blocked_reason"] == "Waiting for the brief"
    assert blocked["stages"][0]["allowed_statuses"] == ["in_progress"]
    assert blocked["status"] == "in_progress"

    back = put_status(client, team, task, script, "in_progress", team.femi).json()
    assert back["is_blocked"] is False and back["stages"][0]["blocked_reason"] is None


def test_a_participant_can_step_back_from_in_progress_to_todo(client):
    team = make_team(client)
    task = create_task(client, team)
    put_status(client, team, task, task["stages"][0], "in_progress", team.femi)
    r = put_status(client, team, task, task["stages"][0], "todo", team.femi)
    assert r.json()["stages"][0]["status"] == "todo"
    assert r.json()["status"] == "not_started"


# =========================================================== unlock early and reopen

def test_head_can_unlock_a_locked_stage_early_but_a_participant_cannot(client):
    team = make_team(client)
    task = create_task(client, team)
    shoot = task["stages"][1]
    err(put_status(client, team, task, shoot, "todo", team.femi), 403)

    r = put_status(client, team, task, shoot, "todo", team.head).json()
    assert r["stages"][1]["status"] == "todo" and r["stages"][1]["unlocked_early"] is True


def test_head_can_start_a_locked_stage_directly(client):
    team = make_team(client)
    task = create_task(client, team)
    r = put_status(client, team, task, task["stages"][2], "in_progress", team.head).json()
    assert r["stages"][2]["status"] == "in_progress" and r["stages"][2]["unlocked_early"] is True


def test_reopening_a_done_stage_relocks_what_was_waiting_on_it(client):
    team = make_team(client)
    task = create_task(client, team)
    put_status(client, team, task, task["stages"][0], "done", team.head)
    assert get_task(client, team, task)["stages"][1]["status"] == "todo"

    r = put_status(client, team, task, task["stages"][0], "in_progress", team.head).json()
    assert statuses(r) == ["in_progress", "locked", "locked"]
    assert r["stages"][0]["completed_at"] is None and r["stages"][0]["completed_by"] is None
    assert r["progress"] == 0


def test_participants_cannot_reopen(client):
    team = make_team(client)
    task = create_task(client, team)
    put_status(client, team, task, task["stages"][0], "done", team.femi)
    err(put_status(client, team, task, task["stages"][0], "in_progress", team.femi), 403, "FORBIDDEN")


def test_reopen_is_refused_once_a_later_stage_has_started(client):
    team = make_team(client)
    task = create_task(client, team)
    put_status(client, team, task, task["stages"][0], "done", team.head)
    put_status(client, team, task, task["stages"][1], "in_progress", team.head)

    current = get_task(client, team, task)
    assert current["stages"][0]["allowed_statuses"] == []  # the UI doesn't even offer it
    err(put_status(client, team, task, task["stages"][0], "in_progress", team.head), 409, "LATER_STAGES_STARTED")


def test_early_unlock_survives_the_stage_before_it_being_reopened(client):
    team = make_team(client)
    task = create_task(client, team, stages=[{"title": "A"}, {"title": "B"}, {"title": "C"}])
    a, b, c = task["stages"]
    put_status(client, team, task, c, "todo", team.head)  # unlock C early
    put_status(client, team, task, a, "done", team.head)
    put_status(client, team, task, b, "done", team.head)
    r = put_status(client, team, task, b, "in_progress", team.head).json()  # reopen B
    assert r["stages"][2]["status"] == "todo"  # still unlocked: it was unlocked on purpose


# =========================================================== parallel stages over HTTP

def test_parallel_stages_unlock_together_and_the_next_step_waits_for_all(client):
    team = make_team(client)
    task = create_task(client, team, stages=[
        {"title": "Shoot"}, {"title": "Graphics"}, {"title": "Music", "parallel_with_previous": True}, {"title": "Export"},
    ])
    shoot, graphics, music, export = task["stages"]

    r = put_status(client, team, task, shoot, "done", team.head).json()
    assert statuses(r) == ["done", "todo", "todo", "locked"]
    assert r["current_stage_title"] == "Graphics, Music"
    assert len(r["current_stage_ids"]) == 2

    r = put_status(client, team, task, graphics, "done", team.head).json()
    assert r["stages"][3]["status"] == "locked"  # music isn't finished
    assert r["current_stage_title"] == "Music"

    r = put_status(client, team, task, music, "done", team.head).json()
    assert r["stages"][3]["status"] == "todo"


# =========================================================== isolation

def test_stage_ids_from_other_tasks_or_rooms_are_404(client):
    team = make_team(client)
    one = create_task(client, team, title="One")
    two = create_task(client, team, title="Two")
    # right room, wrong task
    r = client.put(
        f"{API}/rooms/{team.room['id']}/tasks/{one['id']}/stages/{two['stages'][0]['id']}/status",
        json={"status": "done"}, headers=team.head,
    )
    assert r.status_code == 404

    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    theirs = client.post(
        f"{API}/rooms/{other_room['id']}/tasks", headers=other_head,
        json={"title": "Theirs", "due_date": "2099-01-01T00:00:00Z", "stages": [{"title": "S"}]},
    ).json()
    # a real task and stage, but addressed through MY room: must not be reachable
    r = client.put(
        f"{API}/rooms/{team.room['id']}/tasks/{theirs['id']}/stages/{theirs['stages'][0]['id']}/status",
        json={"status": "done"}, headers=team.head,
    )
    assert r.status_code == 404
    assert client.get(f"{API}/rooms/{other_room['id']}/tasks/{theirs['id']}", headers=other_head).json()["stages"][0]["status"] == "todo"


# =========================================================== add a stage

def add(client, team, task, headers=None, **body):
    body.setdefault("title", "New stage")
    return client.post(f"{API}/rooms/{team.room['id']}/tasks/{task['id']}/stages", json=body, headers=headers or team.head)


def test_add_stage_appends_and_starts_locked(client):
    team = make_team(client)
    task = create_task(client, team)
    r = add(client, team, task, title="Publish")
    assert r.status_code == 201
    body = r.json()
    assert titles(body)[-1] == "Publish" and body["stages_total"] == 4
    assert body["stages"][3]["position"] == 4 and body["stages"][3]["status"] == "locked"


def test_add_stage_at_the_front_pushes_the_old_first_stage_back(client):
    team = make_team(client)
    task = create_task(client, team)
    body = add(client, team, task, title="Brief", position=1).json()
    assert titles(body) == ["Brief", "Script", "Shoot", "Edit"]
    assert [s["position"] for s in body["stages"]] == [1, 2, 3, 4]
    assert statuses(body) == ["todo", "locked", "locked", "locked"]  # Script now waits for Brief


def test_add_stage_in_the_middle_and_after_finished_work(client):
    team = make_team(client)
    task = create_task(client, team, stages=[{"title": "A"}, {"title": "B"}])
    put_status(client, team, task, task["stages"][0], "done", team.head)
    put_status(client, team, task, task["stages"][1], "done", team.head)
    body = add(client, team, task, title="C").json()
    assert body["status"] == "in_progress" and body["progress"] == 67  # the task re-opens
    assert body["stages"][2]["status"] == "todo"


def test_add_stage_validation(client):
    team = make_team(client)
    task = create_task(client, team)

    f = err(add(client, team, task, position=1, parallel_with_previous=True), 422)["fields"]
    assert "parallel_with_previous" in f
    assert "position" in err(add(client, team, task, position=9), 422)["fields"]
    assert "due_date" in err(add(client, team, task, due_date="2100-01-01T00:00:00Z"), 422)["fields"]
    assert "tag_id" in err(add(client, team, task, tag_id=str(uuid.uuid4())), 422)["fields"]
    assert "assignee_ids" in err(add(client, team, task, assignee_ids=[str(uuid.uuid4())]), 422)["fields"]
    assert "title" in err(add(client, team, task, title="  "), 422)["fields"]


def test_thirty_one_stages_is_refused(client):
    team = make_team(client)
    task = create_task(client, team, stages=[{"title": f"S{i}"} for i in range(30)])
    assert "stages" in err(add(client, team, task), 422)["fields"]


def test_add_stage_needs_stage_edit(client):
    team = make_team(client)
    task = create_task(client, team)
    assert add(client, team, task, headers=team.femi).status_code == 403


# =========================================================== edit a stage

def patch(client, team, task, stage, headers=None, **body):
    return client.patch(stage_url(team, task, stage), json=body, headers=headers or team.head)


def test_rename_and_retag_and_clear_tag(client):
    team = make_team(client)
    task = create_task(client, team)
    r = patch(client, team, task, task["stages"][0], title="  Write   script ", tag_id=team.tags["Videographer"]["id"])
    assert r.json()["stages"][0]["title"] == "Write script"
    assert r.json()["stages"][0]["tag"]["name"] == "Videographer"
    r = patch(client, team, task, task["stages"][0], tag_id=None)
    assert r.json()["stages"][0]["tag"] is None


def test_assignees_are_replaced_as_a_set(client):
    team = make_team(client)
    task = create_task(client, team)
    s = task["stages"][1]
    r = patch(client, team, task, s, assignee_ids=[team.ids["femi"], team.ids["tola"]]).json()
    assert [a["name"] for a in r["stages"][1]["assignees"]] == ["Femi", "Tola"]
    r = patch(client, team, task, s, assignee_ids=[team.ids["tola"]]).json()
    assert [a["name"] for a in r["stages"][1]["assignees"]] == ["Tola"]
    r = patch(client, team, task, s, assignee_ids=[]).json()
    assert r["stages"][1]["assignees"] == []
    # leaving assignee_ids out does not touch it
    patch(client, team, task, s, assignee_ids=[team.ids["tola"]])
    r = patch(client, team, task, s, title="Renamed").json()
    assert [a["name"] for a in r["stages"][1]["assignees"]] == ["Tola"]


def test_stage_due_date_can_be_set_and_cleared_and_respects_the_task_due_date(client):
    team = make_team(client)
    task = create_task(client, team)
    s = task["stages"][0]
    assert patch(client, team, task, s, due_date="2099-10-01T00:00:00Z").json()["stages"][0]["due_date"] == "2099-10-01T00:00:00Z"
    assert patch(client, team, task, s, due_date=None).json()["stages"][0]["due_date"] is None
    assert "due_date" in err(patch(client, team, task, s, due_date="2100-01-01T00:00:00Z"), 422)["fields"]


def test_toggling_parallel_changes_the_steps_and_unlocking(client):
    team = make_team(client)
    task = create_task(client, team)
    r = patch(client, team, task, task["stages"][1], parallel_with_previous=True).json()
    assert [s["step"] for s in r["stages"]] == [1, 1, 2]
    assert statuses(r) == ["todo", "todo", "locked"]  # Shoot now starts together with Script

    r = patch(client, team, task, task["stages"][1], parallel_with_previous=False).json()
    assert [s["step"] for s in r["stages"]] == [1, 2, 3]
    assert statuses(r) == ["todo", "locked", "locked"]


def test_move_a_stage_renumbers_and_recomputes_locks(client):
    team = make_team(client)
    task = create_task(client, team)
    r = patch(client, team, task, task["stages"][2], position=1).json()  # Edit to the front
    assert titles(r) == ["Edit", "Script", "Shoot"]
    assert [s["position"] for s in r["stages"]] == [1, 2, 3]
    assert statuses(r) == ["todo", "locked", "locked"]


def test_moving_a_parallel_stage_to_the_front_clears_its_flag_silently(client):
    team = make_team(client)
    task = create_task(client, team, stages=[{"title": "A"}, {"title": "B"}, {"title": "C", "parallel_with_previous": True}])
    r = patch(client, team, task, task["stages"][2], position=1)
    assert r.status_code == 200
    body = r.json()
    assert titles(body) == ["C", "A", "B"]
    assert body["stages"][0]["parallel_with_previous"] is False


def test_explicitly_asking_for_parallel_on_the_first_stage_is_422(client):
    team = make_team(client)
    task = create_task(client, team)
    assert "parallel_with_previous" in err(patch(client, team, task, task["stages"][0], parallel_with_previous=True), 422)["fields"]
    assert "parallel_with_previous" in err(
        patch(client, team, task, task["stages"][2], position=1, parallel_with_previous=True), 422
    )["fields"]


def test_edit_validation(client):
    team = make_team(client)
    task = create_task(client, team)
    s = task["stages"][0]
    assert "position" in err(patch(client, team, task, s, position=9), 422)["fields"]
    assert "tag_id" in err(patch(client, team, task, s, tag_id=str(uuid.uuid4())), 422)["fields"]
    assert "title" in err(patch(client, team, task, s, title=None), 422)["fields"]


def test_only_stage_edit_holders_can_edit_structure(client):
    team = make_team(client)
    task = create_task(client, team)
    assert patch(client, team, task, task["stages"][0], headers=team.femi, title="Hacked").status_code == 403


# =========================================================== delete a stage

def delete(client, team, task, stage, headers=None):
    return client.delete(stage_url(team, task, stage), headers=headers or team.head)


def test_delete_a_stage_renumbers_and_recalculates_progress(client):
    team = make_team(client)
    task = create_task(client, team)
    put_status(client, team, task, task["stages"][0], "done", team.head)
    r = delete(client, team, task, task["stages"][1])  # drop Shoot
    assert r.status_code == 200
    body = r.json()
    assert titles(body) == ["Script", "Edit"] and [s["position"] for s in body["stages"]] == [1, 2]
    assert body["progress"] == 50
    assert body["stages"][1]["status"] == "todo"  # Edit now follows a finished stage


def test_deleting_the_last_stage_is_refused(client):
    team = make_team(client)
    task = create_task(client, team, stages=[{"title": "Only"}])
    err(delete(client, team, task, task["stages"][0]), 409, "LAST_STAGE")
    assert get_task(client, team, task)["stages_total"] == 1


def test_deleting_the_stage_above_a_parallel_one_clears_the_flag_silently(client):
    team = make_team(client)
    task = create_task(client, team, stages=[{"title": "A"}, {"title": "B", "parallel_with_previous": True}, {"title": "C"}])
    r = delete(client, team, task, task["stages"][0])
    assert r.status_code == 200
    assert r.json()["stages"][0]["title"] == "B" and r.json()["stages"][0]["parallel_with_previous"] is False


def test_deleting_a_stage_removes_its_assignments(client, db):
    team = make_team(client)
    task = create_task(client, team, stages=[{"title": "A", "assignee_ids": [team.ids["femi"]]}, {"title": "B"}])
    delete(client, team, task, task["stages"][0])
    assert db.scalars(select(StageAssignee)).all() == []


def test_member_cannot_delete_a_stage(client):
    team = make_team(client)
    task = create_task(client, team)
    assert delete(client, team, task, task["stages"][0], headers=team.femi).status_code == 403


# =========================================================== clean-up from earlier phases

def test_deleting_a_tag_leaves_stages_tag_less(client):
    team = make_team(client)
    task = create_task(client, team)
    tag = team.tags["Videographer"]
    assert client.delete(f"{API}/rooms/{team.room['id']}/tags/{tag['id']}", headers=team.head).status_code == 204
    after = get_task(client, team, task)
    assert after["stages"][1]["tag"] is None
    assert after["stages"][0]["tag"]["name"] == "Content Writer"  # others untouched


def test_removing_a_member_releases_their_stage_assignments(client):
    team = make_team(client)
    task = create_task(client, team, stages=[
        {"title": "A", "assignee_ids": [team.ids["femi"], team.ids["tola"]]},
        {"title": "B", "assignee_ids": [team.ids["femi"]]},
    ])
    mid = membership_id_for(client, team.room["id"], team.head, team.ids["femi"])
    assert client.delete(f"{API}/rooms/{team.room['id']}/members/{mid}", headers=team.head).status_code == 204

    after = get_task(client, team, task)
    assert [a["name"] for a in after["stages"][0]["assignees"]] == ["Tola"]
    assert after["stages"][1]["assignees"] == []
    assert after["stages_total"] == 2  # the task and stages themselves are untouched


def test_removing_a_member_in_one_room_keeps_their_assignments_in_another(client):
    team = make_team(client)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    from tests.conftest import join_and_approve
    femi_h = team.femi
    join_and_approve(client, other_room, other_head, femi_h)
    r = client.post(
        f"{API}/rooms/{other_room['id']}/tasks", headers=other_head,
        json={"title": "Elsewhere", "due_date": "2099-01-01T00:00:00Z", "stages": [{"title": "S", "assignee_ids": [team.ids["femi"]]}]},
    )
    assert r.status_code == 201

    mid = membership_id_for(client, team.room["id"], team.head, team.ids["femi"])
    client.delete(f"{API}/rooms/{team.room['id']}/members/{mid}", headers=team.head)

    theirs = client.get(f"{API}/rooms/{other_room['id']}/tasks/{r.json()['id']}", headers=other_head).json()
    assert [a["name"] for a in theirs["stages"][0]["assignees"]] == ["Femi"]
