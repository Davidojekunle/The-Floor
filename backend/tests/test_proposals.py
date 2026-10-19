"""Phase 4: member proposals, visibility, approve / reject / resubmit, and badges."""
import time
import uuid
from datetime import timedelta

from app.models.room import TempHead
from app.utils.time import utcnow
from tests.conftest import (
    FAR_FUTURE, auth_headers, create_room, create_task, get_task, make_team, post_task, put_status, stage_url,
)

API = "/api/v1"


def tasks_url(team):
    return f"{API}/rooms/{team.room['id']}/tasks"


def propose(client, team, headers=None, **overrides):
    r = post_task(client, team, headers or team.femi, **overrides)
    assert r.status_code == 201, r.text
    assert r.json()["approval_status"] == "pending"
    return r.json()


def act(client, team, task, action, headers, **body):
    return client.post(f"{tasks_url(team)}/{task['id']}/{action}", json=body or None, headers=headers)


def listing(client, team, headers, **params):
    r = client.get(tasks_url(team), params=params, headers=headers)
    assert r.status_code == 200, r.text
    return [t["title"] for t in r.json()["items"]]


def err(r, status, code=None):
    assert r.status_code == status, r.text
    if code:
        assert r.json()["error"]["code"] == code, r.text
    return r.json()["error"]


# =========================================================== creating

def test_member_proposes_through_the_normal_create_form(client):
    team = make_team(client)
    p = propose(client, team)
    assert (p["approval_status"], p["created_by"]["name"]) == ("pending", "Femi")
    assert p["submitted_at"] is not None
    assert (p["decided_at"], p["decided_by"], p["approved_by"], p["rejection_reason"]) == (None, None, None, None)
    assert [s["status"] for s in p["stages"]] == ["todo", "locked", "locked"]  # ready for when it's approved
    assert all(s["allowed_statuses"] == [] for s in p["stages"])  # but no work until then


def test_head_creates_directly_and_it_is_approved_at_once(client):
    team = make_team(client)
    t = create_task(client, team)
    assert t["approval_status"] == "approved"
    assert t["approved_by"]["name"] == "Ada" and t["decided_by"] is None and t["decided_at"] is None
    assert t["submitted_at"] == t["created_at"]


def test_validation_is_identical_for_proposals(client):
    team = make_team(client)
    r = post_task(client, team, team.femi, stages=[{"title": "A", "parallel_with_previous": True}])
    assert "stages.0.parallel_with_previous" in err(r, 422)["fields"]


# =========================================================== flags

def test_flags_for_proposer_approver_and_bystander(client):
    team = make_team(client)
    p = propose(client, team)
    as_femi = get_task(client, team, p, team.femi)
    assert (as_femi["can_edit"], as_femi["can_delete"], as_femi["can_resubmit"], as_femi["can_decide"]) == (True, True, False, False)
    as_head = get_task(client, team, p, team.head)
    assert (as_head["can_edit"], as_head["can_delete"], as_head["can_resubmit"], as_head["can_decide"]) == (True, True, False, True)

    approved = act(client, team, p, "approve", team.head).json()
    assert approved["can_decide"] is False
    as_femi = get_task(client, team, p, team.femi)
    assert (as_femi["can_edit"], as_femi["can_delete"], as_femi["can_resubmit"]) == (False, False, False)  # rights end at approval


def test_flags_after_rejection(client):
    team = make_team(client)
    p = propose(client, team)
    act(client, team, p, "reject", team.head, reason="Not now")
    as_femi = get_task(client, team, p, team.femi)
    assert (as_femi["can_edit"], as_femi["can_delete"], as_femi["can_resubmit"]) == (True, True, True)
    assert get_task(client, team, p, team.head)["can_decide"] is True  # approve still offered on rejected


# =========================================================== visibility

def test_only_the_proposer_and_approvers_can_see_a_proposal(client):
    team = make_team(client)
    p = propose(client, team)
    assert get_task(client, team, p, team.femi)["id"] == p["id"]
    assert get_task(client, team, p, team.head)["id"] == p["id"]
    r = client.get(f"{tasks_url(team)}/{p['id']}", headers=team.tola)
    assert r.status_code == 404
    assert r.json() == client.get(f"{tasks_url(team)}/{uuid.uuid4()}", headers=team.tola).json()  # not leaked


def test_other_members_cannot_reach_a_proposal_by_id_through_any_route(client):
    team = make_team(client)
    p = propose(client, team)
    base = f"{tasks_url(team)}/{p['id']}"
    stage = p["stages"][0]
    attempts = [
        client.patch(base, json={"title": "x"}, headers=team.tola),
        client.delete(base, headers=team.tola),
        client.post(base + "/resubmit", headers=team.tola),
        client.post(base + "/stages", json={"title": "x"}, headers=team.tola),
        client.patch(stage_url(team, p, stage), json={"title": "x"}, headers=team.tola),
        client.delete(stage_url(team, p, stage), headers=team.tola),
        client.put(stage_url(team, p, stage) + "/status", json={"status": "done"}, headers=team.tola),
    ]
    assert [a.status_code for a in attempts] == [404] * len(attempts)


def test_lists_default_to_approved_and_members_only_see_their_own_proposals(client):
    team = make_team(client)
    create_task(client, team, title="Live", due_date="2099-01-01T00:00:00Z")
    propose(client, team, title="Femi's idea", due_date="2099-01-02T00:00:00Z")
    propose(client, team, team.tola, title="Tola's idea", due_date="2099-01-03T00:00:00Z")

    for who in (team.head, team.femi, team.tola):
        assert listing(client, team, who) == ["Live"]  # default: approved only, proposals never on calendars
    assert listing(client, team, team.head, approval_status="pending") == ["Femi's idea", "Tola's idea"]
    assert listing(client, team, team.femi, approval_status="pending") == ["Femi's idea"]
    assert listing(client, team, team.tola, approval_status="approved,pending") == ["Live", "Tola's idea"]


def test_approval_status_takes_several_values_and_rejects_unknown_ones(client):
    team = make_team(client)
    a = propose(client, team, title="A", due_date="2099-01-01T00:00:00Z")
    propose(client, team, title="B", due_date="2099-01-02T00:00:00Z")
    act(client, team, a, "reject", team.head)
    assert listing(client, team, team.femi, approval_status="pending,rejected") == ["A", "B"]
    assert listing(client, team, team.femi, approval_status="rejected") == ["A"]
    for bad in ("nope", "pending,nope", ","):
        r = client.get(tasks_url(team), params={"approval_status": bad}, headers=team.femi)
        assert "approval_status" in err(r, 422)["fields"]


def test_proposals_stay_out_of_my_tasks_and_badges_until_approved(client):
    team = make_team(client)
    p = propose(client, team, team.tola)  # Script stage carries Femi's tag
    assert client.get(f"{API}/me/tasks", headers=team.femi).json()["items"] == []
    assert client.get(f"{API}/me", headers=team.femi).json()["rooms"][0]["mine_actionable"] == 0

    act(client, team, p, "approve", team.head)
    assert [t["title"] for t in client.get(f"{API}/me/tasks", headers=team.femi).json()["items"]] == ["Product promo video"]
    assert client.get(f"{API}/me", headers=team.femi).json()["rooms"][0]["mine_actionable"] == 1


def test_my_proposals_across_rooms(client):
    team = make_team(client)
    bola = auth_headers(client, email="bola@example.com", name="Bola")
    room_b = create_room(client, bola, "Side project")
    from tests.conftest import join_and_approve
    join_and_approve(client, room_b, bola, team.femi)
    propose(client, team, title="In A", due_date="2099-01-01T00:00:00Z")
    r = client.post(f"{API}/rooms/{room_b['id']}/tasks", headers=team.femi,
                    json={"title": "In B", "due_date": "2099-01-02T00:00:00Z", "stages": [{"title": "S"}]})
    assert r.json()["approval_status"] == "pending"
    propose(client, team, team.tola, title="Tola's", due_date="2099-01-03T00:00:00Z")

    items = client.get(f"{API}/me/tasks", params={"approval_status": "pending"}, headers=team.femi).json()["items"]
    assert [(t["title"], t["room"]["name"]) for t in items] == [("In A", "Studio Alpha"), ("In B", "Side project")]
    assert all(s["allowed_statuses"] == [] for t in items for s in t["my_stages"])
    # the head of A doesn't see proposals in My Tasks: those live in the room's approvals list
    assert client.get(f"{API}/me/tasks", params={"approval_status": "pending"}, headers=team.head).json()["items"] == []


# =========================================================== no work before approval

def test_no_status_changes_until_approved(client):
    team = make_team(client)
    p = propose(client, team)
    for who in (team.femi, team.head):
        err(put_status(client, team, p, p["stages"][0], "in_progress", who), 409, "TASK_NOT_APPROVED")
    act(client, team, p, "approve", team.head)
    assert put_status(client, team, p, p["stages"][0], "in_progress", team.femi).status_code == 200


# =========================================================== editing and withdrawing

def test_proposer_edits_task_and_stages_while_pending_or_rejected(client):
    team = make_team(client)
    p = propose(client, team)
    base = f"{tasks_url(team)}/{p['id']}"
    assert client.patch(base, json={"title": "Better idea"}, headers=team.femi).json()["title"] == "Better idea"
    assert client.post(base + "/stages", json={"title": "Publish"}, headers=team.femi).status_code == 201
    r = client.patch(stage_url(team, p, p["stages"][0]), json={"assignee_ids": [team.ids["tola"]]}, headers=team.femi)
    assert r.status_code == 200
    assert client.delete(stage_url(team, p, p["stages"][1]), headers=team.femi).status_code == 200

    act(client, team, p, "reject", team.head)
    assert client.patch(base, json={"description": "Revised"}, headers=team.femi).status_code == 200


def test_proposer_loses_edit_rights_once_approved(client):
    team = make_team(client)
    p = propose(client, team)
    act(client, team, p, "approve", team.head)
    base = f"{tasks_url(team)}/{p['id']}"
    err(client.patch(base, json={"title": "x"}, headers=team.femi), 403, "FORBIDDEN")
    err(client.post(base + "/stages", json={"title": "x"}, headers=team.femi), 403, "FORBIDDEN")
    err(client.delete(base, headers=team.femi), 403, "FORBIDDEN")


def test_approvers_can_adjust_a_proposal_before_approving(client):
    team = make_team(client)
    p = propose(client, team)
    r = client.patch(stage_url(team, p, p["stages"][1]), json={"assignee_ids": [team.ids["tola"]]}, headers=team.head)
    assert [a["name"] for a in r.json()["stages"][1]["assignees"]] == ["Tola"]


def test_proposer_withdraws_by_deleting(client):
    team = make_team(client)
    p = propose(client, team)
    assert client.delete(f"{tasks_url(team)}/{p['id']}", headers=team.femi).status_code == 204
    assert client.get(f"{tasks_url(team)}/{p['id']}", headers=team.head).status_code == 404


# =========================================================== approve

def test_approve_turns_a_proposal_into_a_normal_task(client):
    team = make_team(client)
    p = propose(client, team)
    r = act(client, team, p, "approve", team.head)
    assert r.status_code == 200
    t = r.json()
    assert t["approval_status"] == "approved"
    assert (t["approved_by"]["name"], t["decided_by"]["name"]) == ("Ada", "Ada") and t["decided_at"] is not None
    assert t["stages"][0]["allowed_statuses"] == ["in_progress", "done"]  # the head can now move it
    assert listing(client, team, team.tola) == ["Product promo video"]  # everyone sees it now


def test_approve_is_idempotent_and_needs_task_approve(client):
    team = make_team(client)
    p = propose(client, team)
    err(act(client, team, p, "approve", team.femi), 403, "FORBIDDEN")  # not even your own
    first = act(client, team, p, "approve", team.head).json()
    again = act(client, team, p, "approve", team.head)
    assert again.status_code == 200 and again.json()["decided_at"] == first["decided_at"]


def test_temp_head_can_approve(client, db):
    team = make_team(client)
    db.add(TempHead(room_id=uuid.UUID(team.room["id"]), user_id=uuid.UUID(team.ids["tola"]),
                    granted_by=uuid.UUID(team.ids["head"]), expires_at=utcnow() + timedelta(hours=1)))
    db.commit()
    p = propose(client, team)
    assert get_task(client, team, p, team.tola)["can_decide"] is True  # temp heads can see and decide
    assert act(client, team, p, "approve", team.tola).json()["decided_by"]["name"] == "Tola"


def test_a_rejected_proposal_can_be_approved_directly(client):
    team = make_team(client)
    p = propose(client, team)
    act(client, team, p, "reject", team.head, reason="Hmm")
    t = act(client, team, p, "approve", team.head).json()
    assert t["approval_status"] == "approved" and t["rejection_reason"] is None


# =========================================================== reject

def test_reject_with_and_without_a_reason(client):
    team = make_team(client)
    p = propose(client, team)
    t = act(client, team, p, "reject", team.head, reason="  Let's do this next quarter ").json()
    assert (t["approval_status"], t["rejection_reason"], t["decided_by"]["name"]) == ("rejected", "Let's do this next quarter", "Ada")

    q = propose(client, team, title="Another")
    r = client.post(f"{tasks_url(team)}/{q['id']}/reject", headers=team.head)  # no body at all
    assert r.status_code == 200 and r.json()["rejection_reason"] is None


def test_reject_rules(client):
    team = make_team(client)
    p = propose(client, team)
    first = act(client, team, p, "reject", team.head, reason="No").json()
    again = act(client, team, p, "reject", team.head, reason="Different")
    assert again.status_code == 200 and again.json()["rejection_reason"] == "No"  # no-op keeps the original
    assert again.json()["decided_at"] == first["decided_at"]

    live = create_task(client, team, title="Live")
    err(act(client, team, live, "reject", team.head), 409, "ALREADY_APPROVED")
    assert "reason" in err(act(client, team, propose(client, team, title="X"), "reject", team.head, reason="x" * 501), 422)["fields"]
    err(act(client, team, propose(client, team, title="Y"), "reject", team.tola), 403)


def test_rejection_shows_on_list_items(client):
    team = make_team(client)
    p = propose(client, team)
    act(client, team, p, "reject", team.head, reason="Too big")
    (item,) = client.get(tasks_url(team), params={"approval_status": "rejected"}, headers=team.femi).json()["items"]
    assert (item["rejection_reason"], item["created_by"]["name"]) == ("Too big", "Femi")
    assert item["decided_at"] is not None and item["submitted_at"] is not None


# =========================================================== resubmit

def test_resubmit_puts_it_back_in_the_queue_as_new(client):
    team = make_team(client)
    p = propose(client, team)
    act(client, team, p, "reject", team.head, reason="Fix the dates")
    time.sleep(0.01)
    t = act(client, team, p, "resubmit", team.femi).json()
    assert (t["approval_status"], t["rejection_reason"]) == ("pending", None)
    assert t["submitted_at"] > p["submitted_at"]
    assert t["decided_by"]["name"] == "Ada"  # the last decision is still on record


def test_resubmit_rules(client):
    team = make_team(client)
    p = propose(client, team)
    assert act(client, team, p, "resubmit", team.femi).json()["approval_status"] == "pending"  # already pending: no-op
    act(client, team, p, "reject", team.head)
    err(act(client, team, p, "resubmit", team.head), 403, "FORBIDDEN")  # only the proposer
    act(client, team, p, "approve", team.head)
    err(act(client, team, p, "resubmit", team.femi), 409, "ALREADY_APPROVED")


def test_sort_by_submitted_at_puts_resubmitted_proposals_last(client):
    team = make_team(client)
    a = propose(client, team, title="A", due_date="2099-01-01T00:00:00Z")  # A is due first...
    time.sleep(0.01)
    propose(client, team, title="B", due_date="2099-01-03T00:00:00Z")
    act(client, team, a, "reject", team.head)
    time.sleep(0.01)
    act(client, team, a, "resubmit", team.femi)  # ...but was resubmitted last
    assert listing(client, team, team.head, approval_status="pending") == ["A", "B"]  # default: by due date
    assert listing(client, team, team.head, approval_status="pending", sort="submitted_at") == ["B", "A"]  # queue order
    r = client.get(tasks_url(team), params={"sort": "bogus"}, headers=team.head)
    assert r.status_code == 422


# =========================================================== badges

def rooms_of(client, headers):
    return {r["name"]: (r["pending_count"], r["pending_join_requests"], r["pending_proposals"])
            for r in client.get(f"{API}/me", headers=headers).json()["rooms"]}


def test_badges_split_join_requests_and_proposals_by_role(client, db):
    team = make_team(client)
    kemi = auth_headers(client, email="kemi@example.com", name="Kemi")
    from tests.conftest import request_join
    request_join(client, kemi, team.room["invite_code"])
    propose(client, team, title="One")
    propose(client, team, team.tola, title="Two")

    assert rooms_of(client, team.head) == {"Studio Alpha": (3, 1, 2)}
    assert rooms_of(client, team.femi) == {"Studio Alpha": (0, 0, 0)}  # members act on neither

    db.add(TempHead(room_id=uuid.UUID(team.room["id"]), user_id=uuid.UUID(team.ids["femi"]),
                    granted_by=uuid.UUID(team.ids["head"]), expires_at=utcnow() + timedelta(hours=1)))
    db.commit()
    assert rooms_of(client, team.femi) == {"Studio Alpha": (2, 0, 2)}  # temp head: proposals yes, joins no


def test_deciding_clears_the_badge(client):
    team = make_team(client)
    a = propose(client, team, title="A")
    b = propose(client, team, title="B")
    act(client, team, a, "approve", team.head)
    act(client, team, b, "reject", team.head)
    assert rooms_of(client, team.head) == {"Studio Alpha": (0, 0, 0)}


# =========================================================== isolation

def test_proposals_from_another_room_are_unreachable(client):
    team = make_team(client)
    bola = auth_headers(client, email="bola@example.com", name="Bola")
    room_b = create_room(client, bola, "Side project")
    from tests.conftest import join_and_approve
    join_and_approve(client, room_b, bola, team.tola)
    theirs = client.post(f"{API}/rooms/{room_b['id']}/tasks", headers=team.tola,
                         json={"title": "B idea", "due_date": FAR_FUTURE, "stages": [{"title": "S"}]}).json()
    # Ada heads room A only: she can't see or decide room B's proposal through her room
    assert client.get(f"{tasks_url(team)}/{theirs['id']}", headers=team.head).status_code == 404
    assert client.post(f"{tasks_url(team)}/{theirs['id']}/approve", headers=team.head).status_code == 404
    assert rooms_of(client, team.head) == {"Studio Alpha": (0, 0, 0)}
