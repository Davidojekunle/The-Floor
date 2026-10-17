from pydantic import BaseModel

from app.core.errors import Forbidden


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_unknown_route_uses_error_format(client):
    r = client.get("/api/v1/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_app_error_uses_error_format(app, client):
    def boom():
        raise Forbidden("You can't do that here.")

    app.add_api_route("/boom", boom)
    r = client.get("/boom")
    assert r.status_code == 403
    assert r.json() == {"error": {"code": "FORBIDDEN", "message": "You can't do that here."}}


def test_validation_error_lists_fields(app, client):
    class Body(BaseModel):
        email: str

    def create(body: Body):
        return body

    app.add_api_route("/echo", create, methods=["POST"])
    r = client.post("/echo", json={})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert "email" in err["fields"]


def test_unexpected_error_is_500_in_our_format(app, client):
    def crash():
        raise RuntimeError("secret internals")

    app.add_api_route("/crash", crash)
    r = client.get("/crash")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "SERVER_ERROR"
    assert "secret internals" not in r.text


def test_cors_allows_frontend_origin(client):
    r = client.options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
