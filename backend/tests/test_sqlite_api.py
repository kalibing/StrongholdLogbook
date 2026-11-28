"""SQLite 后端的完整链路：登录 → 上传 → worker 写库 → 查询。"""

from datetime import datetime, timedelta, timezone
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from logbook import api, daily_card, skland, storage
from logbook.api import app
from logbook.records import CHINA
from logbook.security import hasher
from logbook.worker import process_one

ORIGIN = "http://localhost:8080"
PASSWORD = "local-test-password"
HEADERS = {"Origin": ORIGIN}


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    monkeypatch.setenv("LOGBOOK_SQLITE", str(tmp_path / "logbook.sqlite3"))
    with TestClient(app) as test_client:
        with storage.connect() as database:
            database.execute(
                "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
                (uuid4(), "tester", hasher.hash(PASSWORD)),
            )
        response = test_client.post("/api/session", json={"username": "tester", "password": PASSWORD}, headers=HEADERS)
        assert response.status_code == 200
        yield test_client


def upload(client, fixtures):
    payload = (fixtures / "sample-snapshot.json").read_bytes()
    return client.post("/api/imports", content=payload, headers={**HEADERS, "Content-Type": "application/json"})


def drain():
    with storage.connect() as database:
        while process_one(database):
            pass


def test_skland_token_can_be_reused_after_login(client, fixtures, monkeypatch):
    # 这条用例连续同步多次，放宽每日额度（额度本身在 test_registration.py 里单独测）
    monkeypatch.setattr(api.user_quotas["skland"][0], "limit", 100)
    snapshot = json.loads((fixtures / "sample-snapshot.json").read_bytes())
    accepted_tokens = {"initial-test-token", "replacement-test-token"}
    exchanged = []

    def exchange(token):
        exchanged.append(token)
        if token not in accepted_tokens:
            raise skland.AccessTokenRejected("token rejected")
        return "test-cred", "test-signature"

    monkeypatch.setattr(skland, "cred_from_token", exchange)
    monkeypatch.setattr(skland, "api_get", lambda *_: {"data": {"list": [{
        "appCode": "arknights",
        "bindingList": [{"uid": "test-id", "nickName": "测试博士"}],
    }]}})
    monkeypatch.setattr(skland, "history", lambda *_: ["test-record"])
    monkeypatch.setattr(skland, "to_snapshot", lambda _: snapshot)

    token_path = "/api/imports/skland/token"
    import_path = "/api/imports/skland"
    reuse = {"use_saved_token": True}
    assert client.get(token_path).json() == {"saved": False}
    assert client.post(import_path, json=reuse, headers=HEADERS).status_code == 404
    first = client.post(import_path, json={"token": "initial-test-token"}, headers=HEADERS)
    assert first.status_code == 202
    assert first.json()["token_saved"] is True
    assert "initial-test-token" not in first.text
    with storage.connect() as database:
        stored = database.execute("SELECT access_token FROM skland_import_tokens").fetchone()["access_token"]
        assert stored.startswith("logbook:aesgcm:v1:")
        assert "initial-test-token" not in stored
    drain()
    names = []

    def render(card):
        names.append(card.username)
        return b"png"

    monkeypatch.setattr(daily_card, "render", render)
    assert client.get("/api/daily-review/image?day=2026-11-22").status_code == 200
    assert names == ["测试博士"]

    assert client.delete("/api/session", headers=HEADERS).status_code == 204
    assert client.get(token_path).status_code == 401
    login = client.post("/api/session", json={"username": "tester", "password": PASSWORD}, headers=HEADERS)
    assert login.status_code == 200
    assert client.get(token_path).json() == {"saved": True}
    assert client.post(import_path, json={"token": "bad-test-token"}, headers=HEADERS).status_code == 424
    assert client.post(import_path, json=reuse, headers=HEADERS).status_code == 202
    assert exchanged == ["initial-test-token", "bad-test-token", "initial-test-token"]
    drain()

    accepted_tokens.remove("initial-test-token")
    expired = client.post(import_path, json=reuse, headers=HEADERS)
    assert expired.status_code == 424
    assert "更换" in expired.json()["detail"]
    assert client.post(import_path, json={"token": "replacement-test-token"}, headers=HEADERS).status_code == 202
    assert client.post(import_path, json=reuse, headers=HEADERS).status_code == 202
    assert exchanged[-2:] == ["replacement-test-token", "replacement-test-token"]

    with storage.connect() as database:
        database.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
            (uuid4(), "other", hasher.hash(PASSWORD)),
        )
    other = TestClient(app)
    login = other.post("/api/session", json={"username": "other", "password": PASSWORD}, headers=HEADERS)
    assert login.status_code == 200
    assert other.get(token_path).json() == {"saved": False}
    assert other.post(import_path, json=reuse, headers=HEADERS).status_code == 404
    assert other.delete(token_path, headers=HEADERS).status_code == 204

    assert client.get(token_path).json() == {"saved": True}
    assert client.delete(token_path, headers=HEADERS).status_code == 204
    assert client.get(token_path).json() == {"saved": False}
    assert client.post(import_path, json=reuse, headers=HEADERS).status_code == 404


def test_import_and_query_flow(client, fixtures):
    assert client.get("/api/facets").json() == []

    response = upload(client, fixtures)
    assert response.status_code == 202, response.text
    assert response.json()["total"] == 6
    assert client.get("/api/imports").json()[0]["status"] == "pending"

    drain()

    jobs = client.get("/api/imports").json()
    assert jobs[0]["status"] == "done"
    assert jobs[0]["processed"] == 6
    finished = datetime.fromisoformat(jobs[0]["completed_at"])
    assert datetime.now(timezone.utc) - finished < timedelta(hours=1)

    facets = client.get("/api/facets").json()
    assert {(item["protocol"], item["play"]) for item in facets} == {
        ("V3_1", "独立模拟"), ("V3_1", "联合模拟"),
    }

    overview = client.get("/api/overview?scope=all").json()
    assert overview["matches"] == 5
    assert overview["wins"] == 3
    assert overview["excluded"] == 1
    assert overview["max_layers"] == 11
    assert overview["trophy_change"] == 70
    assert len(overview["points"]) == 5

    filtered = client.get("/api/overview?scope=recent&start=2026-11-20&end=2026-11-20").json()
    assert filtered["matches"] == 2
    assert filtered["bond_layers"] == [
        {"name": "伊比利亚", "layers": 8}, {"name": "维多利亚", "layers": 6}, {"name": "奥术", "layers": 3},
    ]

    with_exits = client.get("/api/overview?scope=all&include_exits=true").json()
    assert with_exits["matches"] == 6
    assert with_exits["total_coins"] == 451

    page = client.get("/api/matches?limit=4").json()
    assert page["total"] == 5 and page["pages"] == 2 and len(page["matches"]) == 4
    assert [point["match_id"] for point in reversed(overview["points"][-4:])] == [
        match["id"] for match in page["matches"]
    ]
    first = page["matches"][0]
    assert first["result"] == "loss"
    assert first["scenario"] == "伊比利亚分队"
    assert first["bond_layers"] == 6
    assert first["played_at"].startswith("2026-11-20T13:44:18")
    assert datetime.fromisoformat(first["played_at"]).astimezone(CHINA).hour == 21

    detail = client.get(f"/api/matches/{first['id']}").json()
    assert detail["bonds"] == [{"name": "伊比利亚", "layers": 5}, {"name": "奥术", "layers": 1}]
    assert [unit["name"] for unit in detail["squad"]] == ["斯卡蒂", "阿米娅"]
    assert detail["bosses"] == ["霜星"]

    operators = client.get("/api/operators").json()
    assert operators["with_squad"] == 5

    strategies = client.get("/api/strategies").json()
    assert strategies["with_strategy"] == sum(row["count"] for row in strategies["strategies"])
    assert all(row["wins"] + row["losses"] == row["count"] for row in strategies["strategies"])
    assert abs(sum(row["usage_rate"] for row in strategies["strategies"]) - 1) < 1e-9


def test_duplicate_import_is_idempotent(client, fixtures):
    assert upload(client, fixtures).status_code == 202
    drain()
    assert upload(client, fixtures).status_code == 202
    drain()

    totals = client.get("/api/overview?scope=all&include_exits=true").json()
    assert totals["matches"] == 6
    assert client.get("/api/matches?include_exits=true&limit=50").json()["total"] == 6


def test_sparse_skland_sync_preserves_existing_match_fields(client, monkeypatch):
    started = 1795290440
    match = {
        "external_id": "sync-match", "played_at": datetime.fromtimestamp(started, CHINA).isoformat(),
        "play": "联合模拟", "difficulty": "终极模拟", "result": "win",
        "initiator": "发起者", "scenario": "分队", "trophies": 42, "kills": 60,
        "bonds": [{"name": "炎", "layers": 5}], "bosses": ["boss_1"],
        "squad": [{"id": "char_002_amiya", "name": "阿米娅", "items": ["装备"], "elite": True, "evolve": 2}],
    }
    assert client.post("/api/imports", json={"matches": [match]}, headers=HEADERS).status_code == 202
    drain()
    match_id = client.get("/api/matches").json()["matches"][0]["id"]

    record = {
        "id": "sync-match", "gameStartTs": started, "completeState": 1, "killCnt": 65,
        "chessSquad": [{"chessInfo": {"charId": "char_002_amiya"}}],
    }
    monkeypatch.setattr(skland, "arknights_role", lambda *_: ("test-role", "测试博士"))
    monkeypatch.setattr(skland, "history", lambda *_: [record])
    def sync():
        response = client.post("/api/imports/skland", json={"cred": "test-cred", "sign_token": "test-signature"},
                               headers=HEADERS)
        assert response.status_code == 202, response.text
        drain()
        assert client.get("/api/matches").json()["total"] == 1
        return client.get(f"/api/matches/{match_id}").json()

    detail = sync()
    for field in ("initiator", "scenario", "trophies", "play", "difficulty", "squad", "bonds", "bosses"):
        assert detail[field] == match[field], field
    assert detail["kills"] == 65
    assert client.get("/api/operators").json()["operators"][0]["name"] == "阿米娅"

    # A pending job from the old API cannot tell absent data from generated defaults.
    with storage.connect() as database:
        owner = database.execute("SELECT id FROM users WHERE username = 'tester'").fetchone()["id"]
        legacy = {**match, "trophies": 0, "bonds": [], "bosses": [], "squad": [], "operators": []}
        database.execute("""
            INSERT INTO import_jobs (id, user_id, status, payload, total)
            VALUES (%s, %s, 'pending', %s, 1)
        """, (uuid4(), owner, storage.json_param([legacy])))
    drain()
    detail = client.get(f"/api/matches/{match_id}").json()
    for field in ("trophies", "squad", "bonds", "bosses"):
        assert detail[field] == match[field], field

    record.update(trophyBefore=20, trophyAfter=20, acBossInfo=[])
    detail = sync()
    assert detail["trophies"] == 0
    assert detail["bosses"] == []
    assert client.get("/api/overview").json()["trophy_total"] == {"total": 20, "source": "match"}


def test_distribution_uses_prts_levels_and_keeps_unknown_matches(client):
    entries = [
        ("独立模拟", "规程等级20"), ("独立模拟", "规程等级 4"), ("独立模拟", "极速模拟"),
        ("独立模拟", "规程等级10"), ("独立模拟", "规程等级 4"),
        ("独立模拟", "绝境模拟"), ("联合模拟", "终极模拟"), ("联合模拟", "标准模拟"),
        ("联合模拟", "未来难度"), ("未知", "未知"),
    ]
    matches = [
        {"external_id": f"tier-{index}", "played_at": "2026-11-22T22:00:00+08:00",
         "play": play, "difficulty": difficulty, "result": "win"}
        for index, (play, difficulty) in enumerate(entries)
    ]
    assert client.post("/api/imports", json=matches, headers=HEADERS).status_code == 202
    drain()
    groups = client.get("/api/distribution").json()
    buckets = {group["play"]: [(row["label"], row["total"]) for row in group["buckets"]] for group in groups}
    assert buckets == {
        "联合模拟": [("标准模拟", 1), ("终极模拟", 1), ("其他难度", 1)],
        "独立模拟": [("极速模拟", 1), ("规程等级 4", 2), ("规程等级 10", 1), ("规程等级 20", 1), ("绝境模拟", 1)],
        "其他模拟方式": [("其他难度", 1)],
    }
    assert sum(total for group in buckets.values() for _, total in group) == client.get("/api/overview").json()["matches"]


def test_career_follows_filters_and_profile_has_no_secrets(client):
    matches = [
        {"external_id": "p-1", "played_at": "2026-11-20T21:00:00+08:00", "play": "联合模拟",
         "difficulty": "绝境模拟", "result": "win", "kills": 90},
        {"external_id": "p-2", "played_at": "2026-11-21T21:00:00+08:00", "play": "独立模拟",
         "difficulty": "规程等级 6", "result": "loss", "kills": 30},
    ]
    assert client.post("/api/imports", json=matches, headers=HEADERS).status_code == 202
    drain()
    career = client.get("/api/career").json()
    assert career["career"]["matches"] == 2 and career["career"]["wins"] == 1
    assert career["best"] == {"union": "绝境模拟", "solo": None}
    assert career["activity"]["days"]
    solo = client.get("/api/career", params={"play": "独立模拟"}).json()
    assert solo["career"]["matches"] == 1 and solo["best"] == {"union": None, "solo": None}

    identity = client.get("/api/profile").json()
    assert identity == {"username": "tester", "display_name": None, "avatar_url": None, "username_editable": False, "needs_password": False, "is_admin": False, "account": None}


def test_display_name_is_separate_from_username(client):
    assert client.get("/api/session").json() == {"username": "tester", "display_name": None, "avatar_url": None, "username_editable": False, "needs_password": False, "is_admin": False}
    updated = client.patch("/api/profile", json={"display_name": "  夜  莺 "}, headers=HEADERS)
    assert updated.status_code == 200 and updated.json()["display_name"] == "夜 莺"
    assert client.get("/api/session").json()["username"] == "tester"
    assert client.get("/api/profile").json()["display_name"] == "夜 莺"
    assert client.patch("/api/profile", json={"display_name": "x" * 17}, headers=HEADERS).status_code == 422
    assert client.patch("/api/profile", json={"display_name": "x"}).status_code == 403
    cleared = client.patch("/api/profile", json={"display_name": ""}, headers=HEADERS).json()
    assert cleared["display_name"] is None and cleared["username"] == "tester"


def test_avatar_upload_serve_and_delete(client):
    from io import BytesIO
    from PIL import Image
    source = BytesIO()
    Image.new("RGB", (300, 120), (10, 200, 120)).save(source, format="JPEG")
    upload_headers = {**HEADERS, "Content-Type": "image/jpeg"}
    assert client.put("/api/profile/avatar", content=b"x", headers={**HEADERS, "Content-Type": "text/plain"}).status_code == 415
    assert client.put("/api/profile/avatar", content=b"junk", headers=upload_headers).status_code == 422
    assert client.put("/api/profile/avatar", content=b"x" * (2 * 1024 * 1024 + 1), headers=upload_headers).status_code == 413

    saved = client.put("/api/profile/avatar", content=source.getvalue(), headers=upload_headers)
    assert saved.status_code == 200
    url = saved.json()["avatar_url"]
    assert url.startswith("/api/profile/avatar?v=")
    assert client.get("/api/session").json()["avatar_url"] == url
    image = client.get(url)
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert "max-age" in image.headers["cache-control"] and image.headers["x-content-type-options"] == "nosniff"
    assert Image.open(BytesIO(image.content)).size == (256, 256)
    assert client.get("/api/session").headers["cache-control"] == "no-store"

    removed = client.delete("/api/profile/avatar", headers=HEADERS).json()
    assert removed["avatar_url"] is None
    assert client.get("/api/profile/avatar").status_code == 404


def test_distribution_counts_boss_ids_and_names_once_per_match(client):
    matches = [
        ("win", ["boss_8", "boss_14", "boss_1"], False),
        ("loss", ["假想敌：胄（隐藏）"], False),
        ("loss", ["boss_11"], False),
        ("loss", [], False),
        ("loss", ["boss_16"], True),
    ]
    rows = [
        {
            "external_id": str(index), "played_at": "2026-11-20T21:44:18+08:00",
            "play": "联合模拟", "difficulty": "终极模拟", "result": result,
            "bosses": bosses, "suspected_exit": suspected_exit,
        }
        for index, (result, bosses, suspected_exit) in enumerate(matches)
    ]
    assert client.post("/api/imports", json={"matches": rows}, headers=HEADERS).status_code == 202
    drain()

    url = "/api/distribution?play=联合模拟&difficulty=终极模拟"
    response = client.get(url)
    assert response.status_code == 200
    bucket = next(row for row in response.json()[0]["buckets"] if row["label"] == "终极模拟")
    assert bucket == {
        "label": "终极模拟", "wins": 1, "losses": 3, "total": 4,
        "hidden": 2, "normal_boss": 2, "boss_losses": 2,
    }
    assert client.get(url + "&include_exits=true").json()[0]["buckets"][-1]["hidden"] == 3


def test_daily_review_uses_whole_day_and_sends_only_aggregate_data(client, monkeypatch):
    import io
    import json

    from logbook import daily_review

    rows = [
        ("2026-11-21T23:59:59+08:00", "win", 99, [], False),
        ("2026-11-22T00:00:00+08:00", "win", 14, ["boss_1", "假想敌：胄", "boss_8"], False),
        ("2026-11-22T08:00:00+08:00", "loss", 7, ["boss_1"], False),
        ("2026-11-22T09:00:00+08:00", "loss", 0, [], True),
        ("2026-11-23T00:00:00+08:00", "loss", 99, [], False),
    ]
    snapshot = {"matches": [
        {"external_id": f"daily-{index}", "played_at": time, "play": "联合模拟",
         "difficulty": "终极模拟", "result": result, "rounds": rounds, "bosses": bosses,
         "kills": rounds * 10, "duration_seconds": rounds * 60 if result == "win" else None,
         "suspected_exit": exit_match, "bonds": [{"name": "阿戈尔", "layers": rounds * 10},
                                                {"name": "炎", "layers": rounds}]}
        for index, (time, result, rounds, bosses, exit_match) in enumerate(rows)
    ]}
    assert client.post("/api/imports", json=snapshot, headers=HEADERS).status_code == 202
    drain()

    matches_url = "/api/matches?start=2026-11-22&end=2026-11-22&limit=1"
    row = client.get(matches_url).json()["matches"][0]
    assert "bosses" not in row and "bonds" not in row
    expanded = client.get(matches_url + "&include_breakdown=true").json()
    assert expanded["total"] == 2 and expanded["pages"] == 2
    assert expanded["matches"][0]["bosses"] == ["boss_1"]
    assert expanded["matches"][0]["bonds"][0] == {"name": "阿戈尔", "layers": 70}

    url = "/api/daily-review?day=2026-11-22"
    monkeypatch.delenv("LOGBOOK_AI_MODEL", raising=False)
    review = client.get(url).json()
    assert review["ai_available"] is False
    assert review["bonds"] == [{"name": "阿戈尔", "layers": 210}, {"name": "炎", "layers": 21}]
    assert review["wins"] == {"matches": 1, "average_layers": 154, "average_rounds": 14}
    assert review["losses"] == {"matches": 1, "average_layers": 77, "average_rounds": 7}
    assert review["boss_matches"] == 2 and review["hidden_matches"] == 1
    assert review["normal_matches"] == 2
    assert review["bosses"] == [
        {"name": "假想敌：胄", "matches": 2, "hidden": False},
        {"name": "假想敌：胄（隐藏）", "matches": 1, "hidden": True},
    ]
    assert review["latest_loss"]["id"] == row["id"]
    assert review["longest_win_streak"] == 1
    assert review["total_duration_seconds"] == 840
    assert review["most_kills"]["kills"] == 140
    assert review["most_kills"]["id"] != row["id"]
    assert review["most_layers"]["layers"] == 154
    assert review["most_layers"]["id"] == review["most_kills"]["id"]
    assert review["most_coins"] is None

    image = client.get("/api/daily-review/image?day=2026-11-22")
    if image.status_code != 503:  # 没装中文字体的环境返回 503，图片本身由 test_daily_card 覆盖
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/png"
        assert image.content.startswith(b"\x89PNG")
        assert "no-store" in image.headers["cache-control"]
    assert client.post(url, headers=HEADERS).status_code == 503

    def model_response(request, timeout):
        assert request.full_url == "https://model.example/v1/chat/completions"
        payload = json.loads(request.data)
        data = json.loads(payload["messages"][1]["content"])
        assert payload["model"] == "test-model" and data["recorded_bond_layers"] == 231
        assert data["latest_loss"] == {"play": "联合模拟", "difficulty": "终极模拟", "rounds": 7}
        assert row["id"] not in request.data.decode() and "tester" not in request.data.decode()
        return io.BytesIO(b'{"choices":[{"message":{"content":"Review text"}}]}')

    monkeypatch.setenv("LOGBOOK_AI_MODEL", "test-model")
    monkeypatch.setenv("LOGBOOK_AI_ENDPOINT", "https://model.example/v1/chat/completions")
    monkeypatch.setattr(daily_review, "urlopen", model_response)
    assert client.get(url).json()["ai_available"] is True
    assert client.post(url, headers=HEADERS).json() == {"analysis": "Review text"}


def test_upload_rejects_invalid_payload(client):
    response = client.post("/api/imports", content=b'{"matches": []}', headers={**HEADERS, "Content-Type": "application/json"})
    assert response.status_code == 422
    assert "1–5000" in response.json()["detail"]


def test_session_cookie_is_scoped_and_hardened(client):
    response = client.post("/api/session", json={"username": "tester", "password": PASSWORD}, headers=HEADERS)
    lowered = response.headers["set-cookie"].lower()
    assert "httponly" in lowered
    assert "samesite=strict" in lowered
    assert client.get("/api/session").json()["username"] == "tester"
    assert client.delete("/api/session", headers=HEADERS).status_code == 204
    assert client.get("/api/session").status_code == 401


def test_matches_are_scoped_to_the_owner(client, fixtures):
    drain_after = upload(client, fixtures)
    assert drain_after.status_code == 202
    drain()

    with storage.connect() as database:
        database.execute(
            "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
            (uuid4(), "other", hasher.hash(PASSWORD)),
        )
    other = TestClient(app)
    login = other.post("/api/session", json={"username": "other", "password": PASSWORD}, headers=HEADERS)
    assert login.status_code == 200
    assert other.get("/api/matches").json()["total"] == 0
    assert other.get("/api/overview?scope=all").json()["matches"] == 0
