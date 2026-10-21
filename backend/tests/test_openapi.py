"""The OpenAPI schema is the contract the frontend generates types from, so test it."""
import re


def operations(schema):
    for path, methods in schema["paths"].items():
        for method, op in methods.items():
            yield path, method, op


def test_operation_ids_are_unique_and_clean(app):
    ids = [op["operationId"] for _, _, op in operations(app.openapi())]
    assert len(ids) == len(set(ids)), "duplicate operationId"
    for i in ids:
        assert re.fullmatch(r"[a-z][A-Za-z0-9]*", i), f"ugly operationId: {i}"  # no underscores or paths


def test_known_operation_names(app):
    ids = {op["operationId"] for _, _, op in operations(app.openapi())}
    assert {
        "register", "login", "getMe", "createRoom", "listMyRooms", "getRoom", "previewInvite",
        "requestToJoin", "listJoinRequests", "approveJoinRequest", "rejectJoinRequest",
        "regenerateInvite", "listTags", "createTag", "renameTag", "deleteTag",
        "listMembers", "setMemberTags", "removeMember",
        "createTask", "listTasks", "getTask", "updateTask", "deleteTask",
        "addStage", "updateStage", "putStageStatus", "deleteStage",
        "listTemplates", "createTemplate", "getTemplate", "updateTemplate", "deleteTemplate", "applyTemplate",
        "listMyTasks", "approveTask", "rejectTask", "resubmitTask",
        "setTempHead", "revokeTempHead",
        "listMessages", "sendMessage", "deleteMessage", "markMessagesRead",
        "listStageUpdates", "postStageUpdate", "deleteStageUpdate", "listTaskUpdates",
        "refreshSession", "logout", "logoutAll",
        "leaveRoom", "transferHead", "deleteRoom", "forgotPassword", "resetPassword",
        "updateMe", "changePassword", "changeEmail", "confirmEmail", "cancelEmailChange", "cancelEmailChangeByLink",
        "listNotifications", "markNotificationsRead", "markNotificationRead", "getNotificationSettings",
        "updateNotificationSettings", "muteRoom", "unmuteRoom",
    } <= ids


def test_every_error_response_uses_our_error_schema(app):
    schema = app.openapi()
    for path, method, op in operations(schema):
        for status, response in op["responses"].items():
            if status.startswith(("4", "5")):
                ref = response["content"]["application/json"]["schema"]["$ref"]
                assert ref.endswith("/ErrorResponse"), f"{method} {path} {status} -> {ref}"
    assert "HTTPValidationError" not in schema["components"]["schemas"]  # FastAPI's default 422 shape is gone


def test_every_route_declares_422_and_500(app):
    for path, method, op in operations(app.openapi()):
        assert {"422", "500"} <= set(op["responses"]), f"{method} {path}"


def test_success_status_codes_are_declared(app):
    paths = app.openapi()["paths"]
    assert "201" in paths["/api/v1/rooms"]["post"]["responses"]
    assert "201" in paths["/api/v1/auth/register"]["post"]["responses"]
    assert "201" in paths["/api/v1/join/{invite_code}"]["post"]["responses"]
    assert "204" in paths["/api/v1/rooms/{room_id}/tags/{tag_id}"]["delete"]["responses"]
    assert "204" in paths["/api/v1/rooms/{room_id}/members/{membership_id}"]["delete"]["responses"]


def test_auth_routes_declare_only_errors_they_can_return(app):
    paths = app.openapi()["paths"]
    assert "409" in paths["/api/v1/auth/register"]["post"]["responses"]
    assert "401" not in paths["/api/v1/auth/register"]["post"]["responses"]
    assert "401" in paths["/api/v1/auth/login"]["post"]["responses"]
    assert "409" not in paths["/api/v1/auth/login"]["post"]["responses"]


def test_paginated_lists_have_named_schemas(app):
    names = set(app.openapi()["components"]["schemas"])
    assert {"RoomSummaryPage", "JoinRequestPage", "TagPage", "MemberPage", "TaskPage", "TemplatePage", "MyTaskPage"} <= names
    assert not any(n.startswith("Page_") for n in names)


def test_task_routes_declare_expected_success_codes(app):
    paths = app.openapi()["paths"]
    tasks = "/api/v1/rooms/{room_id}/tasks"
    assert "201" in paths[tasks]["post"]["responses"]
    assert "204" in paths[tasks + "/{task_id}"]["delete"]["responses"]
    stages = tasks + "/{task_id}/stages"
    assert "201" in paths[stages]["post"]["responses"]
    assert "200" in paths[stages + "/{stage_id}"]["delete"]["responses"]  # returns the updated task
    assert "put" in paths[stages + "/{stage_id}/status"]


def test_list_tasks_documents_from_to_and_500_limit(app):
    params = {p["name"]: p for p in app.openapi()["paths"]["/api/v1/rooms/{room_id}/tasks"]["get"]["parameters"]}
    assert {"from", "to", "status", "assignee", "tag", "overdue", "blocked", "approval_status", "sort", "page", "limit"} <= set(params)
    assert params["limit"]["schema"]["maximum"] == 500


def test_stats_endpoint_was_not_built(app):
    assert not any("task-stats" in p for p in app.openapi()["paths"])


def test_my_tasks_documents_its_errors_and_params(app):
    op = app.openapi()["paths"]["/api/v1/me/tasks"]["get"]
    assert {"401", "404", "422"} <= set(op["responses"])
    names = {p["name"] for p in op["parameters"]}
    assert {"scope", "actionable", "from", "to", "status", "overdue", "blocked", "room", "approval_status", "sort", "page", "limit"} <= names


def test_message_event_is_a_discriminated_union(app):
    schemas = app.openapi()["components"]["schemas"]
    event = schemas["MessageOut"]["properties"]["event"]
    union = next(v for v in event["anyOf"] if "oneOf" in v)
    assert union["discriminator"]["propertyName"] == "type"
    assert set(union["discriminator"]["mapping"]) == {
        "member_joined", "task_created", "task_approved", "stage_done", "stage_blocked",
        "stage_reopened", "stage_unlocked", "task_completed", "temp_head_granted", "temp_head_revoked",
        "member_left", "head_transferred",
    }
    assert "reason" in schemas["StageBlockedDetail"]["properties"]
    assert "expires_at" in schemas["TempHeadGrantedDetail"]["properties"]
