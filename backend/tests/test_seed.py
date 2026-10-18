from scripts.seed import PASSWORD, PENDING, run
from tests.conftest import login

API = "/api/v1"


def headers_for(client, email):
    token = login(client, email=email, password=PASSWORD).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_seed_creates_a_usable_demo_room(client, db):
    result = run(db)

    head = headers_for(client, "head@example.com")
    rooms = client.get(f"{API}/me", headers=head).json()["rooms"]
    assert [(r["name"], r["my_role"], r["pending_count"]) for r in rooms] == [("Studio Alpha", "head", 2)]  # Kemi + Femi's proposal

    room_id = result["room_id"]
    members = client.get(f"{API}/rooms/{room_id}/members", headers=head).json()["items"]
    assert {m["user"]["name"]: [t["name"] for t in m["tags"]] for m in members} == {
        "Ada": [], "Femi": ["Content Writer"], "Tola": ["Video Editor"],
    }
    tags = client.get(f"{API}/rooms/{room_id}/tags", headers=head).json()["items"]
    assert [t["name"] for t in tags] == ["Content Writer", "Graphic Designer", "Video Editor", "Videographer"]

    pending = client.get(f"{API}/rooms/{room_id}/join-requests", headers=head).json()
    assert [i["user"]["name"] for i in pending["items"]] == [PENDING[0]]


def test_seed_logins_work_for_everyone(client, db):
    run(db)
    for email in ("head@example.com", "femi@example.com", "tola@example.com", "kemi@example.com"):
        assert login(client, email=email, password=PASSWORD).status_code == 200


def test_seed_is_idempotent(client, db):
    first = run(db)
    second = run(db)
    assert first["room_id"] == second["room_id"]
    assert first["invite_code"] == second["invite_code"]

    head = headers_for(client, "head@example.com")
    assert len(client.get(f"{API}/me", headers=head).json()["rooms"]) == 1
    assert client.get(f"{API}/rooms/{first['room_id']}/members", headers=head).json()["total"] == 3
    assert client.get(f"{API}/rooms/{first['room_id']}/tags", headers=head).json()["total"] == 4
    assert client.get(f"{API}/rooms/{first['room_id']}/join-requests", headers=head).json()["total"] == 1


def test_rerun_keeps_manual_tag_changes(client, db):
    result = run(db)
    head = headers_for(client, "head@example.com")
    room_id = result["room_id"]
    members = client.get(f"{API}/rooms/{room_id}/members", headers=head).json()["items"]
    femi = next(m for m in members if m["user"]["name"] == "Femi")
    client.patch(f"{API}/rooms/{room_id}/members/{femi['membership_id']}", json={"tag_ids": []}, headers=head)

    run(db)
    members = client.get(f"{API}/rooms/{room_id}/members", headers=head).json()["items"]
    assert next(m for m in members if m["user"]["name"] == "Femi")["tags"] == []


def test_seed_adds_a_template_and_a_task_in_progress(client, db):
    result = run(db)
    head = headers_for(client, "head@example.com")
    room_id = result["room_id"]

    templates = client.get(f"{API}/rooms/{room_id}/templates", headers=head).json()["items"]
    assert [(t["name"], [s["title"] for s in t["stages"]]) for t in templates] == [("Video shoot", ["Script", "Shoot", "Edit"])]

    tasks = client.get(f"{API}/rooms/{room_id}/tasks", headers=head).json()["items"]
    assert [(t["title"], t["progress"], t["current_stage_title"]) for t in tasks] == [("Product promo video", 33, "Shoot")]

    detail = client.get(f"{API}/rooms/{room_id}/tasks/{tasks[0]['id']}", headers=head).json()
    assert [s["status"] for s in detail["stages"]] == ["done", "todo", "locked"]
    assert detail["stages"][0]["completed_by"]["name"] == "Femi"
    assert [s["tag"]["name"] for s in detail["stages"]] == ["Content Writer", "Videographer", "Video Editor"]


def test_rerunning_the_seed_does_not_duplicate_the_template_or_task(client, db):
    first = run(db)
    run(db)
    head = headers_for(client, "head@example.com")
    assert client.get(f"{API}/rooms/{first['room_id']}/templates", headers=head).json()["total"] == 1
    assert client.get(f"{API}/rooms/{first['room_id']}/tasks", headers=head).json()["total"] == 1


def test_seed_gives_tola_work_waiting_in_my_tasks(client, db):
    run(db)
    tola = headers_for(client, "tola@example.com")
    rooms = client.get(f"{API}/me", headers=tola).json()["rooms"]
    assert [(r["name"], r["mine_actionable"]) for r in rooms] == [("Studio Alpha", 1)]

    (item,) = client.get(f"{API}/me/tasks", headers=tola).json()["items"]
    stages = [(s["title"], s["status"], s["assigned_to_me"], s["tag"]["name"]) for s in item["my_stages"]]
    assert stages == [("Shoot", "todo", True, "Videographer"), ("Edit", "locked", False, "Video Editor")]


def test_seed_has_a_pending_proposal_for_the_approvals_screen(client, db):
    result = run(db)
    head = headers_for(client, "head@example.com")
    (room,) = client.get(f"{API}/me", headers=head).json()["rooms"]
    assert (room["pending_join_requests"], room["pending_proposals"]) == (1, 1)

    queue = client.get(f"{API}/rooms/{result['room_id']}/tasks", params={"approval_status": "pending"}, headers=head).json()
    assert [(t["title"], t["created_by"]["name"]) for t in queue["items"]] == [("Behind-the-scenes reel", "Femi")]

    femi = headers_for(client, "femi@example.com")
    mine = client.get(f"{API}/me/tasks", params={"approval_status": "pending"}, headers=femi).json()["items"]
    assert [t["title"] for t in mine] == ["Behind-the-scenes reel"]
    tola = headers_for(client, "tola@example.com")  # not hers: invisible
    assert client.get(f"{API}/me/tasks", params={"approval_status": "pending"}, headers=tola).json()["items"] == []


def test_seed_room_chat_tells_the_story_so_far(client, db):
    result = run(db)
    head = headers_for(client, "head@example.com")
    page = client.get(f"{API}/rooms/{result['room_id']}/messages", headers=head).json()
    oldest_first = [(m["type"], m["event"]["type"] if m["event"] else None, m["body"]) for m in reversed(page["items"])]
    assert oldest_first == [
        ("system", "member_joined", "Femi joined the room"),
        ("system", "member_joined", "Tola joined the room"),
        ("system", "task_created", "Ada created Product promo video"),
        ("system", "stage_done", "Femi finished Script on Product promo video"),
        ("user", None, "Shooting starts tomorrow at 9"),
    ]  # the pending proposal posts nothing
    assert page["items"][0]["stage"]["title"] == "Shoot"
