from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from logbook import api
from logbook.limits import FailureThrottle, RequestSizeLimit


def small_app(limit=16):
    application = FastAPI()
    application.add_middleware(RequestSizeLimit, limit=limit)

    @application.post("/echo")
    async def echo(request: Request):
        return {"size": len(await request.body())}

    return TestClient(application)


def test_declared_oversize_body_is_rejected():
    response = small_app().post("/echo", content=b"x" * 17)
    assert response.status_code == 413


def test_chunked_oversize_body_is_rejected():
    def chunks():
        for _ in range(4):
            yield b"x" * 8

    response = small_app().post("/echo", content=chunks())
    assert response.status_code == 413


def test_body_within_limit_passes():
    response = small_app().post("/echo", content=b"x" * 16)
    assert response.json() == {"size": 16}


def test_throttle_blocks_after_limit_and_window_expires(monkeypatch):
    clock = [1000.0]
    monkeypatch.setattr("logbook.limits.time.monotonic", lambda: clock[0])
    throttle = FailureThrottle(limit=3, window=60)
    for _ in range(3):
        assert not throttle.blocked("1.2.3.4")
        throttle.failed("1.2.3.4")
    assert throttle.blocked("1.2.3.4")
    assert not throttle.blocked("5.6.7.8")
    clock[0] += 61
    assert not throttle.blocked("1.2.3.4")


def test_throttle_memory_is_bounded():
    throttle = FailureThrottle(limit=3, window=60, max_keys=5)
    for index in range(50):
        throttle.failed(f"10.0.0.{index}")
    assert len(throttle._failures) <= 5


def test_login_is_throttled_per_client(monkeypatch):
    throttle = FailureThrottle(limit=1)
    throttle.failed("testclient")
    monkeypatch.setattr(api, "login_throttle", throttle)
    response = TestClient(api.app).post(
        "/api/session", json={"username": "tester", "password": "x"},
        headers={"Origin": api.settings.public_origin},
    )
    assert response.status_code == 429
