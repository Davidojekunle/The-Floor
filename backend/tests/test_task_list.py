from tests.conftest import auth_headers, create_room, create_tag, create_task, make_team, put_status

API = "/api/v1"


def listing(client, team, headers=None, **params):
    r = client.get(f"{API}/rooms/{team.room['id']}/tasks", params=params, headers=headers or team.head)
    assert r.status_code == 200, r.text
    return r.json()


def titles(page):
    return [t["title"] for t in page["items"]]


ONE = [{"title": "Only stage"}]


# ---------- shape, sorting, paging ----------

def test_list_item_shape_is_exactly_the_calendar_item(client):
    team = make_team(client)
    create_task(client, team)
    item = listing(client, team)["items"][0]
    assert set(item) == {
        "id", "title", "start_date", "due_date", "approval_status", "status", "progress", "stages_done",
        "stages_total", "current_stage_title", "is_overdue", "is_blocked", "involves_me",
        "created_by", "submitted_at", "decided_at", "rejection_reason",  # phase 4
    }
    assert item["current_stage_title"] == "Script" and item["progress"] == 0 and item["stages_total"] == 3


def test_sorted_by_due_date_then_paged_with_a_true_total(client):
    team = make_team(client)
    for title, due in [("C", "2099-03-03T00:00:00Z"), ("A", "2099-03-01T00:00:00Z"), ("B", "2099-03-02T00:00:00Z"),
                       ("E", "2099-03-05T00:00:00Z"), ("D", "2099-03-04T00:00:00Z")]:
        create_task(client, team, title=title, due_date=due, stages=ONE)

    page = listing(client, team)
    assert titles(page) == ["A", "B", "C", "D", "E"] and page["total"] == 5 and page["limit"] == 20

    page2 = listing(client, team, limit=2, page=2)
    assert titles(page2) == ["C", "D"] and page2["total"] == 5


def test_limit_up_to_500_is_allowed_and_above_is_422(client):
    team = make_team(client)
    create_task(client, team, stages=ONE)
    assert listing(client, team, limit=500)["limit"] == 500
    r = client.get(f"{API}/rooms/{team.room['id']}/tasks", params={"limit": 501}, headers=team.head)
    assert r.status_code == 422 and "limit" in r.json()["error"]["fields"]


def test_every_member_sees_every_task(client):
    team = make_team(client)
    create_task(client, team, title="One", stages=ONE)
    create_task(client, team, title="Two", stages=ONE)
    assert sorted(titles(listing(client, team, team.femi))) == ["One", "Two"]


def test_rooms_never_mix(client):
    team = make_team(client)
    create_task(client, team, title="Mine", stages=ONE)
    other_head = auth_headers(client, email="other@example.com", name="Other")
    other_room = create_room(client, other_head, "Other room")
    client.post(f"{API}/rooms/{other_room['id']}/tasks", headers=other_head,
                json={"title": "Theirs", "due_date": "2099-01-01T00:00:00Z", "stages": ONE})
    assert titles(listing(client, team)) == ["Mine"]


# ---------- calendar window: [from, to) ----------

def calendar_tasks(client, team):
    create_task(client, team, title="point", due_date="2099-03-10T12:00:00Z", stages=ONE)
    create_task(client, team, title="span", start_date="2099-03-05T00:00:00Z", due_date="2099-03-20T00:00:00Z", stages=ONE)
    create_task(client, team, title="late", due_date="2099-04-01T00:00:00Z", stages=ONE)


def test_window_from_is_inclusive_and_to_is_exclusive(client):
    team = make_team(client)
    calendar_tasks(client, team)
    got = listing(client, team, **{"from": "2099-03-10T12:00:00Z", "to": "2099-04-01T00:00:00Z"})
    assert titles(got) == ["point", "span"]  # 'point' sits exactly on from; 'late' sits exactly on to


def test_window_includes_spans_that_overlap_it(client):
    team = make_team(client)
    calendar_tasks(client, team)
    got = listing(client, team, **{"from": "2099-03-12T00:00:00Z", "to": "2099-03-15T00:00:00Z"})
    assert titles(got) == ["span"]  # starts before the window and ends after it


def test_window_with_nothing_in_it(client):
    team = make_team(client)
    calendar_tasks(client, team)
    assert listing(client, team, **{"from": "2099-03-21T00:00:00Z", "to": "2099-04-01T00:00:00Z"})["items"] == []


def test_window_with_only_from_or_only_to(client):
    team = make_team(client)
    calendar_tasks(client, team)
    assert titles(listing(client, team, **{"from": "2099-03-20T00:00:00Z"})) == ["span", "late"]
    assert titles(listing(client, team, to="2099-03-06T00:00:00Z")) == ["span"]


def test_window_dates_need_a_timezone(client):
    team = make_team(client)
    r = client.get(f"{API}/rooms/{team.room['id']}/tasks", params={"from": "2099-03-01T00:00:00"}, headers=team.head)
    assert r.status_code == 422 and "from" in r.json()["error"]["fields"]


def test_window_accepts_offsets(client):
    team = make_team(client)
    create_task(client, team, title="point", due_date="2099-03-10T12:00:00Z", stages=ONE)
    got = listing(client, team, **{"from": "2099-03-10T13:00:00+01:00", "to": "2099-03-10T14:00:00+01:00"})
    assert titles(got) == ["point"]  # 13:00+01:00 is exactly 12:00Z


# ---------- filters ----------

def test_filter_by_status(client):
    team = make_team(client)
    fresh = create_task(client, team, title="fresh", stages=ONE)
    started = create_task(client, team, title="started", stages=[{"title": "A"}, {"title": "B"}])
    finished = create_task(client, team, title="finished", stages=ONE)
    put_status(client, team, started, started["stages"][0], "in_progress", team.head)
    put_status(client, team, finished, finished["stages"][0], "done", team.head)

    assert titles(listing(client, team, status="not_started")) == ["fresh"]
    assert titles(listing(client, team, status="in_progress")) == ["started"]
    assert titles(listing(client, team, status="done")) == ["finished"]
    r = client.get(f"{API}/rooms/{team.room['id']}/tasks", params={"status": "bogus"}, headers=team.head)
    assert r.status_code == 422


def test_a_task_with_one_stage_done_and_one_not_is_in_progress(client):
    team = make_team(client)
    t = create_task(client, team, title="half", stages=[{"title": "A"}, {"title": "B"}])
    put_status(client, team, t, t["stages"][0], "done", team.head)
    assert titles(listing(client, team, status="in_progress")) == ["half"]
    assert titles(listing(client, team, status="not_started")) == []


def test_filter_overdue(client):
    team = make_team(client)
    create_task(client, team, title="late", due_date="2020-01-01T00:00:00Z", stages=ONE)
    done_late = create_task(client, team, title="late but done", due_date="2020-01-01T00:00:00Z", stages=ONE)
    create_task(client, team, title="future", stages=ONE)
    put_status(client, team, done_late, done_late["stages"][0], "done", team.head)

    assert titles(listing(client, team, overdue="true")) == ["late"]


def test_filter_by_assignee_me_uses_tags_and_assignments(client):
    team = make_team(client)
    create_task(client, team, title="default", due_date="2099-01-01T00:00:00Z")  # Femi=Script tag, Tola=Edit tag
    create_task(client, team, title="tola only", due_date="2099-01-02T00:00:00Z",
                stages=[{"title": "X", "assignee_ids": [team.ids["tola"]]}])
    create_task(client, team, title="nobody", due_date="2099-01-03T00:00:00Z", stages=ONE)

    assert titles(listing(client, team, team.femi, assignee="me")) == ["default"]
    assert titles(listing(client, team, team.tola, assignee="me")) == ["default", "tola only"]
    assert titles(listing(client, team, team.head, assignee="me")) == []  # the head is not a participant by default
    assert titles(listing(client, team, team.head, assignee=team.ids["tola"])) == ["default", "tola only"]


def test_assignee_filter_edge_cases(client):
    team = make_team(client)
    create_task(client, team, stages=ONE)
    import uuid
    assert listing(client, team, assignee=str(uuid.uuid4()))["items"] == []  # not a member: nothing, no error
    r = client.get(f"{API}/rooms/{team.room['id']}/tasks", params={"assignee": "nonsense"}, headers=team.head)
    assert r.status_code == 422 and "assignee" in r.json()["error"]["fields"]


def test_filter_by_tag(client):
    team = make_team(client)
    create_task(client, team, title="has videographer")
    create_task(client, team, title="no tags", stages=ONE)
    assert titles(listing(client, team, tag=team.tags["Videographer"]["id"])) == ["has videographer"]

    import uuid
    r = client.get(f"{API}/rooms/{team.room['id']}/tasks", params={"tag": str(uuid.uuid4())}, headers=team.head)
    assert r.status_code == 404


def test_filters_combine(client):
    team = make_team(client)
    create_task(client, team, title="a", due_date="2099-03-10T00:00:00Z")
    create_task(client, team, title="b", due_date="2099-05-10T00:00:00Z")
    got = listing(client, team, team.femi, assignee="me", **{"from": "2099-03-01T00:00:00Z", "to": "2099-04-01T00:00:00Z"})
    assert titles(got) == ["a"]


def test_involves_me_flag_on_list_items(client):
    team = make_team(client)
    create_task(client, team, title="default", due_date="2099-01-01T00:00:00Z")
    create_task(client, team, title="nobody", due_date="2099-01-02T00:00:00Z", stages=ONE)
    flags = {t["title"]: t["involves_me"] for t in listing(client, team, team.femi)["items"]}
    assert flags == {"default": True, "nobody": False}


def test_removed_members_stop_showing_as_assignees(client):
    team = make_team(client)
    create_task(client, team, title="tola only", stages=[{"title": "X", "assignee_ids": [team.ids["tola"]]}])
    from tests.conftest import membership_id_for
    mid = membership_id_for(client, team.room["id"], team.head, team.ids["tola"])
    client.delete(f"{API}/rooms/{team.room['id']}/members/{mid}", headers=team.head)
    assert listing(client, team, assignee=team.ids["tola"])["items"] == []
