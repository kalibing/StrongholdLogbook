"""成就档案：归一化、token 解析与接口层的离线测试（不联网）。"""

import json
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from logbook import achievements, hypergryph, storage
from logbook.api import app
from logbook.security import hasher

ORIGIN = "http://localhost:8080"
PASSWORD = "local-test-password"
HEADERS = {"Origin": ORIGIN}
TOKEN = "A" * 580

SUMMARY = {
    "player": {"uid": "10000000", "level": 120, "nickname": "示例博士",
               "nickNumber": "2268", "avatar": "char_4182_oblvns#1", "nameCard": "nc_6d5_1"},
    "trophy": 470, "trophyLevel": 8,
    "careerTrophy": {"act3autochess": {"value": 470, "iconId": "trophy_level8_icon", "level": 8}},
    "beLike": 149,
    "teammate": {"maxPlay": {"uid": "128130101", "value": 68}, "maxWin": {"uid": "128130101", "value": 39}},
    "teammatePlayers": {"128130101": {"uid": "128130101", "level": 120, "nickname": "黍勿",
                                     "nickNumber": "1487", "avatar": "avatar_special_43", "nameCard": "nc_avemujica_1_2"}},
    "friend": {"friendList": ["1", "2", "3"], "starFriendList": ["128130101"]},
    "title": {
        "achievements": {"BOND": 79, "KILL": 23, "EQUIP": 43, "COIN": 49, "CHAR": 74, "DAMAGE": 37},
        "list": [{"id": "comment_2", "value": 8}, {"id": "comment_3", "value": 71}],
        "specialList": [{"id": "comment_1", "value": 0}],
    },
    "max": {"coinCost": 727, "sync": 80, "defeat": 473, "singleWin": 1, "multiWin": 5, "help": 135, "dmg": 100},
    "mode": {"single": {"battle": 7, "win": 3, "hardModeId": "mode_single_14", "hardWin": 0,
                        "hardModeName": "规程等级14"},
             "multi": {"battle": 103, "win": 53, "hardWin": 47, "secondHardWin": 4}},
    "band": {"top": [{"id": "band_mech", "name": "森蚺", "value": 14, "winningRate": 50}],
             "pass": [{"id": "band_mech", "name": "森蚺", "masterVictor": True},
                      {"id": "band_pith", "name": "Pith", "masterVictor": False}]},
    "season": {
        "versionInfo": {"versionId": "V3_1", "activityId": "act3autochess", "seasonName": "规程",
                        "seasonYear": "year#1", "startTime": 1794124800, "endTime": 4092580799,
                        "isOffseason": False},
        "titles": {
            "comment_1": {"id": "comment_1", "type": "BOND", "point": 0, "rank": 0,
                          "picId": "comment_icon_1_0", "txt": "百花齐放"},
            "comment_2": {"id": "comment_2", "type": "BOND", "point": 1, "rank": 1,
                          "picId": "comment_icon_1_1", "txt": "坚实盟约"},
            "comment_3": {"id": "comment_3", "type": "BOND", "point": 1, "rank": 2,
                          "picId": "comment_icon_1_2", "txt": "不朽盟约"},
        },
        "bands": {
            "band_mech": {"id": "band_mech", "name": "森蚺", "type": "GENERAL", "effectName": "暴躁铁皮",
                          "image": {"icon": "https://example.invalid/band_mech.png"}},
            "band_pith": {"id": "band_pith", "name": "Pith", "type": "GENERAL", "effectName": "优等生",
                          "image": {"icon": "https://example.invalid/band_pith.png"}},
        },
    },
}


def test_normalize_core_fields():
    profile = achievements.normalize(SUMMARY)
    assert profile["player"]["nickname"] == "示例博士"
    assert profile["trophy"] == {"total": 470, "level": 8, "icon": "trophy_level8_icon"}
    assert profile["likes"] == 149
    assert profile["season"]["version"] == "V3_1"
    scores = {row["key"]: row["score"] for row in profile["dimensions"]}
    assert scores == {"BOND": 79, "KILL": 23, "CHAR": 74, "EQUIP": 43, "COIN": 49, "DAMAGE": 37}


def test_normalize_titles_and_bands():
    profile = achievements.normalize(SUMMARY)
    names = {row["id"]: row["name"] for row in profile["titles"]}
    assert names == {"comment_1": "百花齐放", "comment_2": "坚实盟约", "comment_3": "不朽盟约"}
    bond = next(row for row in profile["dimensions"] if row["key"] == "BOND")
    assert [row["rank"] for row in bond["titles"]] == [0, 1, 2]

    bands = profile["bands"]
    assert bands["summary"] == {"total": 2, "mastered": 1, "pending": 1}
    assert [row["variant"] for row in bands["badges"]] == ["master", "base"]
    assert bands["badges"][0]["obtained"] is True
    assert bands["top"][0]["effect"] == "暴躁铁皮"


def test_normalize_tolerates_missing_fields():
    profile = achievements.normalize({"player": {"uid": "1"}})
    assert profile["likes"] == 0
    assert profile["bands"]["summary"] == {"total": 0, "mastered": 0, "pending": 0}
    assert len(profile["dimensions"]) == 6


def test_teammate_cards_keep_each_metric_with_its_owner():
    players = {"a": {"nickname": "甲"}, "b": {"nickname": "乙"}}
    play = {"uid": "a", "value": 15}
    win = {"uid": "b", "value": 12}

    def metrics(teammate):
        social = achievements.social_of({"teammate": teammate, "teammatePlayers": players})
        return [(row["nickname"], row["plays"], row["wins"]) for row in social["top_teammates"]]

    assert metrics({"maxPlay": play, "maxWin": win}) == [("甲", 15, None), ("乙", None, 12)]
    assert metrics({"maxPlay": play, "maxWin": {**win, "uid": "a"}}) == [("甲", 15, None), ("甲", None, 12)]
    assert metrics({"maxWin": win}) == [("乙", None, 12)]
    assert metrics({}) == []


def test_extract_code_from_forms():
    raw = "F" * 64
    assert hypergryph.extract_code(raw) == raw
    assert hypergryph.extract_code("?code=" + raw) == raw
    assert hypergryph.extract_code("https://ak-webview.hypergryph.com/autoChess/index?lang=zh-cn&u8_token=" + raw) == raw
    assert hypergryph.extract_code(f"GET /api/autoChess/act3autochess/playerSummary?code={raw} HTTP/2") == raw
    with pytest.raises(hypergryph.CredentialError):
        hypergryph.extract_code("short")


def test_player_summary_rejects_error_payload(monkeypatch):
    monkeypatch.setattr(hypergryph, "_request",
                        lambda *args, **kwargs: (200, json.dumps({"status": 10008, "msg": "找不到玩家角色"})))
    with pytest.raises(hypergryph.CredentialError) as error:
        hypergryph.player_summary("A" * 64)
    assert "找不到玩家角色" in str(error.value)


def test_password_login_wires_token_chain(monkeypatch):
    calls = []

    def fake_request(method, url, body=None, headers=None):
        calls.append((url, body))
        if url.endswith("/user/auth/v1/token_by_phone_password"):
            return 200, json.dumps({"status": 0, "data": {"token": "abc", "uid": "1001"}})
        assert url.endswith("/u8/user/v1/getToken")
        extension = json.loads(body["extension"])
        assert extension == {"uid": "1001", "access_token": "abc"}
        assert body["sign"]
        return 200, json.dumps({"data": {"uid": "10000000", "token": "u8-token"}})

    monkeypatch.setattr(hypergryph, "_request", fake_request)
    monkeypatch.setattr(hypergryph, "player_summary", lambda code: {"player": {"uid": "10000000"}})
    uid, code, data, warnings = hypergryph.connect_with_password("13800000000", "pw")
    assert (uid, code, data, warnings) == ("10000000", "u8-token", {"player": {"uid": "10000000"}}, [])
    assert len(calls) == 2


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    monkeypatch.setenv("LOGBOOK_SQLITE", str(tmp_path / "logbook.sqlite3"))
    with TestClient(app) as test_client:
        with storage.connect() as database:
            database.execute("INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
                             (uuid4(), "tester", hasher.hash(PASSWORD)))
        assert test_client.post("/api/session", json={"username": "tester", "password": PASSWORD},
                                headers=HEADERS).status_code == 200
        yield test_client


def test_api_connect_and_read(client, monkeypatch):
    monkeypatch.setattr(hypergryph, "player_summary", lambda code: json.loads(json.dumps(SUMMARY)))
    assert client.get("/api/achv/status").json()["connected"] is False
    assert client.get("/api/achv/summary").status_code == 404

    response = client.post("/api/achv/session", json={"token": "code=" + TOKEN}, headers=HEADERS)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["data"]["player"]["uid"] == "10000000"

    status = client.get("/api/achv/status").json()
    assert status["connected"] is True and status["source"] == "token"
    summary = client.get("/api/achv/summary").json()
    assert summary["data"]["bands"]["summary"]["mastered"] == 1
    assert summary["warning"] is None

    assert client.delete("/api/achv/session", headers=HEADERS).status_code == 204
    assert client.get("/api/achv/status").json()["connected"] is False


def test_api_connect_reports_credential_errors(client, monkeypatch):
    def boom(code):
        raise hypergryph.CredentialError("成就接口拒绝：找不到玩家角色")

    monkeypatch.setattr(hypergryph, "player_summary", boom)
    response = client.post("/api/achv/session", json={"token": TOKEN}, headers=HEADERS)
    assert response.status_code == 424
    assert "找不到玩家角色" in response.json()["detail"]


def test_api_requires_login(tmp_path, monkeypatch):
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    monkeypatch.setenv("LOGBOOK_SQLITE", str(tmp_path / "anon.sqlite3"))
    with TestClient(app) as test_client:
        assert test_client.get("/api/achv/status").status_code == 401


def test_summary_refreshes_when_stale(client, monkeypatch):
    monkeypatch.setattr(hypergryph, "player_summary", lambda code: json.loads(json.dumps(SUMMARY)))
    assert client.post("/api/achv/session", json={"token": "code=" + TOKEN}, headers=HEADERS).status_code == 200

    stale = dict(SUMMARY)
    stale["beLike"] = 200

    monkeypatch.setattr(hypergryph, "player_summary", lambda code: json.loads(json.dumps(stale)))
    with storage.connect() as database:
        database.execute("UPDATE achv_links SET fetched_at = %s",
                         (datetime(2020, 1, 1, tzinfo=timezone.utc),))
    body = client.get("/api/achv/summary").json()
    assert body["data"]["likes"] == 200
    assert body["state"]["stale"] is False


# ---------------------------------------------------------------- 网页登录代理

from logbook import hgproxy  # noqa: E402


def test_rewrite_text_maps_hosts_and_cdn():
    source = ('<script src="https://web.hycdn.cn/user-center/index.1.js"></script>'
              'fetch("https://as.hypergryph.com/user/auth/v1/token_by_phone_password")'
              'fetch("https://u8.hypergryph.com/u8/user/v1/getToken")')
    result = hgproxy.rewrite_text(source)
    assert "/hg/cdn/user-center/index.1.js" in result
    assert "/hg/as/user/auth" in result and "/hg/u8/u8/user" in result
    assert "https://as.hypergryph.com" not in result and "https://u8.hypergryph.com" not in result


def test_rewrite_cookie_strips_domain_and_secure():
    value = "u8_token=abc; Domain=.hypergryph.com; Path=/; Secure; SameSite=None"
    rewritten = hgproxy.rewrite_cookie(value)
    assert "Domain" not in rewritten and "Secure" not in rewritten
    assert "SameSite=Lax" in rewritten and "u8_token=abc" in rewritten


def test_remember_keeps_access_token_per_browser():
    hgproxy.CAPTURES.clear()
    hgproxy.remember("nonce0000000000aa", {"status": 0, "data": {"token": "x" * 40, "uid": "1001"}})
    assert hgproxy.CAPTURES["nonce0000000000aa"]["access_token"] == "x" * 40
    assert hgproxy.CAPTURES["nonce0000000000aa"]["uid"] == "1001"
    hgproxy.remember("nonce0000000000aa", {"status": 100, "msg": "账号或密码错误"})
    assert hgproxy.CAPTURES["nonce0000000000aa"]["access_token"] == "x" * 40
    hgproxy.CAPTURES.clear()


def test_connect_with_access_token_uses_account_info_uid(monkeypatch):
    seen = {}

    def fake_request(method, url, body=None, headers=None):
        if "/user/info/v1/basic" in url:
            return 200, json.dumps({"status": 0, "data": {"hgId": "1001234", "phone": "138****0000"}})
        seen["url"] = url
        extension = json.loads(body["extension"])
        seen["extension"] = extension
        return 200, json.dumps({"data": {"uid": "10000000", "token": "u8-token"}})

    monkeypatch.setattr(hypergryph, "_request", fake_request)
    monkeypatch.setattr(hypergryph, "player_summary", lambda code: {"player": {"uid": "10000000"}})
    uid, code, data, warnings = hypergryph.connect_with_access_token("access-token")
    assert (uid, code) == ("10000000", "u8-token")
    assert seen["extension"] == {"uid": "1001234", "access_token": "access-token"}
    assert warnings == []


def test_connect_with_access_token_falls_back_to_channel_token(monkeypatch):
    def fake_request(method, url, body=None, headers=None):
        if "/user/info/v1/basic" in url:
            return 200, json.dumps({"status": 0, "data": {"hgId": "1001234"}})
        if "channel_token" in url:
            return 200, json.dumps({"status": 0, "data": {"channelToken": "channel-token"}})
        return 400, json.dumps({"message": "verify fail"})

    monkeypatch.setattr(hypergryph, "_request", fake_request)
    monkeypatch.setattr(hypergryph, "player_summary", lambda code: {"player": {"uid": "10000000"}, "code": code})
    uid, code, data, _ = hypergryph.connect_with_access_token("access-token")
    assert code == "channel-token"
    assert data["player"]["uid"] == "10000000"


def test_api_connect_with_access_token(client, monkeypatch):
    monkeypatch.setattr(hypergryph, "connect_with_access_token",
                        lambda token, uid="": ("10000000", "u8-token", json.loads(json.dumps(SUMMARY)), []))
    response = client.post("/api/achv/session", json={"access_token": "a" * 32}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["player"]["uid"] == "10000000"
    assert client.get("/api/achv/status").json()["source"] == "hypergryph"


def test_hg_proxy_requires_no_origin(client):
    """代理路由不受本站 Origin 校验影响（请求来自官方页面）。"""
    response = client.get("/hg/", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/hg/user/login"


# ---------------------------------------------------------------- 抓包导入

from logbook import capture  # noqa: E402

HAR = ('{"entries":[{"request":{"url":"https://ak-webview.hypergryph.com/api/autoChess/'
       'act3autochess/playerSummary?code=' + "B" * 60 + '%2Btail"}}]}')


def test_capture_ingest_and_candidates():
    capture.RECENT.clear()
    tokens = capture.ingest(HAR)
    assert tokens and tokens[0] == "B" * 60 + "+tail"
    assert capture.candidate_tokens()[0][1] == "reqable-report"
    capture.RECENT.clear()


def test_report_endpoint_rejects_foreign_client(client):
    """Reqable 上报只接受本机回环；TestClient 的 client.host 是 testclient。"""
    capture.RECENT.clear()
    response = client.post("/api/hg/report", content=HAR.encode(),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 403
    assert capture.recent() == []


def test_api_import_capture(client, monkeypatch):
    capture.RECENT.clear()
    capture.ingest(HAR)
    seen = {}

    def fake_summary(code):
        seen["code"] = code
        return json.loads(json.dumps(SUMMARY))

    monkeypatch.setattr(hypergryph, "player_summary", fake_summary)
    response = client.post("/api/achv/import-capture", json={}, headers=HEADERS)
    assert response.status_code == 200, response.text
    assert response.json()["source_file"] == "reqable-report"
    assert seen["code"].endswith("+tail")
    assert client.get("/api/achv/status").json()["connected"] is True
    capture.RECENT.clear()
