"""森空岛（Skland）战绩拉取 → 本站快照格式。

链路（见 SKLAND-API.md，均为实测结论）：

    hgsdk user_token ──▶ POST as.hypergryph.com/user/oauth2/v2/grant
                            appCode=4ca99fa6b56cc2ba（森空岛）, type=0
                          └─ data.code（一次性）
    data.code ──▶ POST zonai.skland.com/web/v1/user/auth/generate_cred_by_code {code, kind:1}
                          └─ data.cred + data.token（sign_token）
    GET zonai.skland.com/api/v1/game/player/binding        → 明日方舟 uid / channelMasterId
    GET zonai.skland.com/api/v1/game/garrison/guide/history-log?seasonId=act3autochess
                          头：cred / sign / timestamp / dId / platform / vName / sk-game-role
                          └─ data.records[]（固定最新 100 条，无分页）

每个业务请求都要现算签名：

    t = int(time.time())
    hdr = {"platform": "3", "timestamp": t, "dId": "", "vName": "1.0.0"}   # 键序固定
    s = path + query + t + json.dumps(hdr, separators=(",", ":"))
    sign = md5(hmac_sha256(sign_token, s))
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

SKLAND_APP_CODE = "4ca99fa6b56cc2ba"
API_BASE = "https://zonai.skland.com"
SEASON = "act3autochess"
CHINA = timezone(timedelta(hours=8))
UA = ("Mozilla/5.0 (Linux; Android 12; SM-A5560 Build/V417IR; wv) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Version/4.0 Chrome/101.0.4951.61 Safari/537.36; SKLand/1.52.1")
SIGN_PLATFORM = "3"
SIGN_VNAME = "1.0.0"

from .bond_names import BOND_NAMES  # noqa: E402


class SklandError(Exception):
    """森空岛链路失败；message 面向用户。"""


class AccessTokenRejected(SklandError):
    """鹰角拒绝了用 access token 换取授权的请求。"""


def _request(method: str, url: str, headers: dict | None = None, body: dict | None = None) -> tuple[int, str]:
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, method=method)
    request.add_header("User-Agent", UA)
    request.add_header("Accept-Encoding", "gzip")
    request.add_header("Connection", "close")
    if data is not None:
        request.add_header("Content-Type", "application/json")
    for key, value in (headers or {}).items():
        request.add_header(key, value)
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw, status = response.read(), response.status
    except urllib.error.HTTPError as error:
        raw, status = error.read(), error.code
    except OSError as error:
        raise SklandError("连接森空岛失败，请稍后重试") from error
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return status, raw.decode("utf-8", "replace")


def sign(sign_token: str, path: str, query: str = "", did: str = "", timestamp: str | None = None) -> tuple[str, str, dict]:
    t = timestamp or str(int(time.time()))
    header = {"platform": SIGN_PLATFORM, "timestamp": t, "dId": did, "vName": SIGN_VNAME}
    source = path + query + t + json.dumps(header, separators=(",", ":"))
    digest = hmac.new(sign_token.encode(), source.encode(), hashlib.sha256).hexdigest()
    return hashlib.md5(digest.encode()).hexdigest(), t, header


def cred_from_token(access_token: str) -> tuple[str, str]:
    """鹰角 token → (cred, sign_token)。access_token 用森空岛 appCode 换 oauth code。"""
    status, text = _request("POST", "https://as.hypergryph.com/user/oauth2/v2/grant",
                            body={"appCode": SKLAND_APP_CODE, "token": access_token, "type": 0})
    if status in (401, 403):
        raise AccessTokenRejected("鹰角未接受此 token，请重新获取后再试。")
    if status != 200:
        raise SklandError(f"换取森空岛 oauth code 失败（HTTP {status}）")
    try:
        payload = json.loads(text)
        code = (payload.get("data") or {}).get("code")
    except (ValueError, AttributeError):
        raise SklandError(f"换取森空岛 oauth code 失败（HTTP {status}）")
    if not code:
        raise AccessTokenRejected("鹰角未接受此 token，请重新获取后再试。")
    status, text = _request("POST", f"{API_BASE}/web/v1/user/auth/generate_cred_by_code",
                            body={"code": code, "kind": 1})
    try:
        data = json.loads(text).get("data") or {}
    except ValueError:
        data = {}
    if status != 200 or not data.get("cred") or not data.get("token"):
        raise SklandError(f"换取森空岛 cred 失败（HTTP {status}）")
    return str(data["cred"]), str(data["token"])


def api_get(cred: str, sign_token: str, path: str, query: str = "", role: str = "") -> dict:
    signature, timestamp, header = sign(sign_token, path, query)
    headers = {
        "cred": cred,
        "sign": signature,
        "timestamp": timestamp,
        "platform": header["platform"],
        "vName": header["vName"],
        "dId": header["dId"],
        "X-Requested-With": "com.hypergryph.skland",
    }
    if role:
        headers["sk-game-role"] = role
    url = API_BASE + path + (("?" + query) if query else "")
    status, text = _request("GET", url, headers=headers)
    try:
        payload = json.loads(text)
    except ValueError:
        raise SklandError(f"森空岛返回无法解析的内容（HTTP {status}）") from None
    if payload.get("code") not in (0, None):
        raise SklandError(f"森空岛拒绝请求，请检查凭据或稍后重试（HTTP {status}）")
    return payload


def arknights_role(cred: str, sign_token: str) -> str:
    payload = api_get(cred, sign_token, "/api/v1/game/player/binding")
    for app in ((payload.get("data") or {}).get("list") or []):
        if app.get("appCode") != "arknights":
            continue
        for item in app.get("bindingList") or []:
            if item.get("isDelete"):
                continue
            return f"{item.get('gameId', 1)}_{item.get('uid')}_{item.get('channelMasterId', '1')}"
    raise SklandError("森空岛账号下没有绑定明日方舟角色")


def history(cred: str, sign_token: str, role: str, season: str = SEASON) -> list[dict]:
    payload = api_get(cred, sign_token, "/api/v1/game/garrison/guide/history-log",
                      f"seasonId={season}", role)
    records = ((payload.get("data") or {}).get("records")) or []
    if not records:
        raise SklandError("森空岛没有返回战绩（可能本季未参与）")
    return records


def to_snapshot(records: list[dict]) -> dict:
    """森空岛记录 → 本站导入快照（与 fixtures/sample-snapshot.json 同构）。"""
    operators: dict[str, dict] = {}
    equipment: dict[str, dict] = {}
    matches = []
    for record in records:
        squad = []
        for chess in record.get("chessSquad") or []:
            info = chess.get("chessInfo") or {}
            char_id = info.get("charId") or ""
            char_name = info.get("charName") or char_id
            chess_id = chess.get("chessId") or info.get("id")
            golden_id = info.get("goldenChessId")
            if char_id:
                operators[char_id] = {"name": char_name}
            items = []
            for equip in chess.get("equips") or []:
                equip_id = equip.get("equipId") or ""
                if equip_id:
                    items.append(equip_id)
                    equipment.setdefault(equip_id, {"name": equip_id})
            unit = {
                "id": char_id,
                "name": char_name,
                "elite": chess_id == golden_id if chess_id and golden_id else None,
                "evolve": info.get("evolvePhase"),
            }
            if isinstance(chess.get("equips"), list):
                unit["items"] = items
            squad.append(unit)
        bonds = [
            {"name": BOND_NAMES.get(bond.get("bondId") or "", bond.get("bondId") or ""),
             "layers": int(bond.get("layer") or 0)}
            for bond in record.get("bondInfo") or []
            if bond.get("activate")
        ]
        bosses = [b.get("bossId") for b in record.get("acBossInfo") or [] if b.get("isKilled")]
        started = int(record.get("gameStartTs") or 0)
        ended = int(record.get("gameEndTs") or 0)
        before, after = record.get("trophyBefore"), record.get("trophyAfter")
        mode = (record.get("modeType") or "").upper()
        match = {
            "external_id": record.get("id"),
            "played_at": datetime.fromtimestamp(started, CHINA).isoformat() if started else None,
            "protocol": record.get("versionId") or "V3_1",
            "play": ("联合模拟" if mode == "MULTI" else "独立模拟") if mode else "未知",
            "difficulty": record.get("mode") or record.get("modeDifficulty") or "未知",
            "result": "win" if int(record.get("completeState") or 0) == 1 else "loss",
            "strategy": BAND_NAMES.get(record.get("bandId") or "", record.get("bandId") or None),
            "rounds": record.get("passRound"),
            "kills": record.get("killCnt"),
            "coins": record.get("coinCost"),
            "sync_count": record.get("syncCnt"),
            "trophies": int(after) - int(before) if before not in (None, "") and after not in (None, "") else None,
            "duration_seconds": (ended - started) if started and ended > started else None,
        }
        if isinstance(record.get("bondInfo"), list):
            match["bonds"] = bonds
        if isinstance(record.get("chessSquad"), list):
            match["squad"] = squad
        if isinstance(record.get("acBossInfo"), list):
            match["bosses"] = [b for b in bosses if b]
        matches.append(match)
    matches = [m for m in matches if m["external_id"] and m["played_at"]]
    # 旧 → 新，方便导入后趋势图从左到右
    matches.sort(key=lambda item: item["played_at"])
    return {"operators": operators, "equipment": equipment, "matches": matches}


# 分队 id → 展示名（策略列用；未收录时退回 id）
BAND_NAMES = {
    "band_mech": "森蚺", "band_egir": "歌蕾蒂娅", "band_mess": "昆图斯", "band_bonus": "复奏",
    "band_gain": "铃兰", "band_amiya": "阿米娅", "band_pith": "Pith", "band_ducklord": "鸭爵",
}
