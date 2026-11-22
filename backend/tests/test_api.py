from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from logbook.api import app, current_user, queue_import, require_role

ORIGIN = "http://localhost:8080"


@pytest.fixture()
def client():
    """不进入 lifespan，因此测试不依赖真实数据库连接。"""
    return TestClient(app)


@pytest.fixture()
def authorized():
    app.dependency_overrides[current_user] = lambda: {"id": uuid4(), "username": "tester"}
    app.dependency_overrides[require_role] = lambda: uuid4()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_cross_origin_write_is_rejected(client):
    response = client.post("/api/session", json={"username": "tester", "password": "x"})
    assert response.status_code == 403
    assert response.json() == {"detail": "请求来源无效"}
    assert response.headers["cache-control"] == "no-store"


def test_foreign_origin_write_is_rejected(client):
    response = client.post(
        "/api/session", json={"username": "tester", "password": "x"},
        headers={"Origin": "https://evil.example"},
    )
    assert response.status_code == 403


def test_login_payload_is_validated(client):
    response = client.post(
        "/api/session", json={"username": "AB", "password": ""},
        headers={"Origin": ORIGIN},
    )
    assert response.status_code == 422


def test_anonymous_reads_are_unauthorized(client):
    for path in ("/api/session", "/api/roles", f"/api/roles/{uuid4()}/overview",
                 f"/api/roles/{uuid4()}/matches", f"/api/roles/{uuid4()}/operators",
                 f"/api/roles/{uuid4()}/imports"):
        response = client.get(path)
        assert response.status_code == 401, path
        assert response.headers["cache-control"] == "no-store"


def test_anonymous_upload_is_unauthorized(client):
    response = client.post(
        f"/api/roles/{uuid4()}/imports", content=b"{}",
        headers={"Origin": ORIGIN, "Content-Type": "application/json"},
    )
    assert response.status_code == 401


def test_logout_without_session_is_idempotent(client):
    response = client.delete("/api/session", headers={"Origin": ORIGIN})
    assert response.status_code == 204


def test_upload_requires_json_media_type(authorized):
    response = authorized.post(
        f"/api/roles/{uuid4()}/imports", content=b"{}",
        headers={"Origin": ORIGIN, "Content-Type": "text/plain"},
    )
    assert response.status_code == 415
    assert "JSON" in response.json()["detail"]


def test_upload_rejects_oversized_body(authorized):
    response = authorized.post(
        f"/api/roles/{uuid4()}/imports", content=b"0" * (8 * 1024 * 1024 + 1),
        headers={"Origin": ORIGIN, "Content-Type": "application/json"},
    )
    assert response.status_code == 413


@pytest.mark.parametrize("payload", [b"not json", b"{}", b'{"matches": []}', b'{"matches": [{"x": 1}]}'])
def test_queue_import_validates_before_writing(payload):
    with pytest.raises(HTTPException) as error:
        queue_import(None, uuid4(), payload)
    assert error.value.status_code == 422


def test_health_route_exists(client):
    routes = {route.path for route in app.routes}
    assert {"/api/health", "/api/roles/{role_id}/overview", "/api/roles/{role_id}/matches",
            "/api/roles/{role_id}/matches/{match_id}", "/api/roles/{role_id}/operators",
            "/api/roles/{role_id}/imports"} <= routes


def test_unknown_route_is_not_found(client):
    assert client.get("/api/nope").status_code == 404
