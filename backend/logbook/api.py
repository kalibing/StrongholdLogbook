from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
from threading import Lock
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout
from pydantic import BaseModel, Field, StringConstraints
from starlette.concurrency import run_in_threadpool

from . import achievements, capture, hgproxy, hypergryph, stats
from .config import settings
from .db import connection_pool
from .errors import UniqueConflict
from .records import Filters, read_snapshot
from .security import COOKIE, SESSION_TTL, USERNAME_PATTERN, dummy_hash, hasher, new_session, session_hash, verify_password
from .storage import json_param

MAX_UPLOAD_BYTES = 8 * 1024 * 1024
MAX_PENDING_IMPORTS = 3
READ_COLUMNS = (
    "id, played_at, protocol, play, difficulty, result, scenario, strategy, initiator, "
    "rounds, kills, coins, suspected_exit"
)


@asynccontextmanager
async def lifespan(application):
    pool = connection_pool()
    pool.open()
    application.state.pool = pool
    try:
        yield
    finally:
        pool.close()


app = FastAPI(title="卫戍协议战绩档案", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)


@app.middleware("http")
async def protect_requests(request: Request, call_next):
    # /hg/* 是鹰角通行证登录页的反向代理，请求由官方页面自己发出，不校验本站 Origin。
    proxied = (request.url.path == "/hg" or request.url.path.startswith("/hg/")
               or request.url.path == "/api/hg/report")
    if (
        not proxied
        and request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.headers.get("origin") != settings.public_origin
    ):
        response = JSONResponse({"detail": "请求来源无效"}, 403)
    else:
        response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


app.include_router(hgproxy.router)
app.include_router(hgproxy.capture_router)


@app.exception_handler(PoolTimeout)
async def database_unavailable(_request, _error):
    return JSONResponse({"detail": "数据库暂不可用，请稍后重试"}, 503)


class Login(BaseModel):
    username: str = Field(pattern=USERNAME_PATTERN)
    password: str = Field(min_length=1, max_length=256)


def current_user(request: Request):
    token = request.cookies.get(COOKIE, "")
    if token and len(token) <= 128:
        with request.app.state.pool.connection() as database:
            user = database.execute("""
                SELECT users.id, users.username FROM users JOIN sessions ON users.id = sessions.user_id
                WHERE sessions.token_hash = %s AND sessions.expires_at > now()
            """, (session_hash(token),)).fetchone()
            if user:
                return user
    raise HTTPException(401, "请先登录")


@app.get("/api/health")
def health(request: Request):
    with request.app.state.pool.connection() as database:
        database.execute("SELECT 1 FROM users LIMIT 1")
    return {"status": "ok"}


@app.get("/api/session")
def session(user=Depends(current_user)):
    return {"username": user["username"]}


@app.post("/api/session")
def login(details: Login, request: Request, response: Response):
    with request.app.state.pool.connection() as database:
        user = database.execute("SELECT * FROM users WHERE username = %s FOR UPDATE", (details.username,)).fetchone()
        now = datetime.now(timezone.utc)
        if user and user["locked_until"] and user["locked_until"] > now:
            raise HTTPException(429, "登录尝试过多，请在 15 分钟后重试")
        password_hash = user["password_hash"] if user else dummy_hash
        authenticated = verify_password(password_hash, details.password) and user is not None
        if authenticated:
            token = new_session()
            database.execute("DELETE FROM sessions WHERE expires_at <= now()")
            database.execute(
                "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
                (session_hash(token), user["id"], now + SESSION_TTL),
            )
            database.execute("""
                UPDATE users SET failed_logins = 0, locked_until = NULL, password_hash = %s
                WHERE id = %s
            """, (hasher.hash(details.password) if hasher.check_needs_rehash(password_hash) else password_hash, user["id"]))
        elif user:
            failures = 1 if user["locked_until"] else user["failed_logins"] + 1
            database.execute("UPDATE users SET failed_logins = %s, locked_until = %s WHERE id = %s",
                             (failures, now + timedelta(minutes=15) if failures >= 8 else None, user["id"]))
    if not authenticated:
        raise HTTPException(401, "用户名或密码错误")
    response.set_cookie(
        COOKIE, token, max_age=int(SESSION_TTL.total_seconds()), httponly=True,
        secure=settings.cookie_secure, samesite="strict", path="/",
    )
    return {"username": user["username"]}


@app.delete("/api/session", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE, "")
    if token and len(token) <= 128:
        with request.app.state.pool.connection() as database:
            database.execute("DELETE FROM sessions WHERE token_hash = %s", (session_hash(token),))
    response.delete_cookie(COOKIE, path="/", secure=settings.cookie_secure, httponly=True, samesite="strict")


@app.get("/api/directory")
def directory(request: Request, user=Depends(current_user)):
    """干员 ID ↔ 名称，用于把发起者等纯文本字段对上头像。"""
    with request.app.state.pool.connection() as database:
        rows = database.execute(
            "SELECT operators FROM matches WHERE user_id = %s", (user["id"],),
        ).fetchall()
    names = {}
    for row in rows:
        for operator in row["operators"]:
            names[operator["id"]] = operator["name"]
    return {"operators": [{"id": key, "name": value} for key, value in sorted(names.items(), key=lambda item: item[1])]}


SOLO_RANGES = (
    (1, 4, "规程等级 1–4"),
    (5, 8, "规程等级 5–8"),
    (9, 14, "规程等级 9–14"),
    (15, 20, "规程等级 15–20"),
)
UNION_TIERS = ("标准模拟", "险境模拟", "绝境模拟", "终极模拟")


def distribution_label(play: str, difficulty: str) -> str | None:
    """把难度归到展示分档；没有对应分档的返回 None（不展示「其他」）。"""
    if play == "联合模拟":
        return difficulty if difficulty in UNION_TIERS else None
    for low, high, label in SOLO_RANGES:
        level = difficulty.replace("规程等级", "").strip()
        if level.isdigit() and low <= int(level) <= high:
            return label
    return "极速模拟" if difficulty == "极速模拟" else None


@app.get("/api/facets")
def facets(request: Request, user=Depends(current_user)):
    with request.app.state.pool.connection() as database:
        return database.execute("""
            SELECT DISTINCT protocol, play, difficulty FROM matches WHERE user_id = %s
            ORDER BY protocol, play, difficulty
        """, (user["id"],)).fetchall()


@app.get("/api/distribution")
def distribution(request: Request, filters: Annotated[Filters, Depends()], user=Depends(current_user)):
    """按模拟方式与难度分组统计胜负，展示模式分布。"""
    where, params = filters.sql(user["id"])
    with request.app.state.pool.connection() as database:
        rows = database.execute(
            f"SELECT play, difficulty, result FROM matches WHERE {where}", params,
        ).fetchall()

    counts: dict[tuple[str, str], list[int]] = {}
    for row in rows:
        label = distribution_label(row["play"], row["difficulty"])
        if label is None:
            continue
        bucket = counts.setdefault((row["play"], label), [0, 0])
        bucket[0 if row["result"] == "win" else 1] += 1

    order = {
        "联合模拟": list(UNION_TIERS),
        "独立模拟": [label for _, _, label in SOLO_RANGES] + ["极速模拟"],
    }
    result = []
    for play in ("联合模拟", "独立模拟"):
        buckets = []
        for label in order[play]:
            wins, losses = counts.get((play, label), (0, 0))
            buckets.append({"label": label, "wins": wins, "losses": losses, "total": wins + losses})
        result.append({"play": play, "buckets": buckets})
    return result


@app.get("/api/overview")
def overview(
    request: Request, filters: Annotated[Filters, Depends()],
    scope: Literal["recent", "all", "day"] = "recent", user=Depends(current_user),
):
    where, params = filters.model_copy(update={"include_exits": True}).sql(user["id"])
    with request.app.state.pool.connection() as database:
        candidates = database.execute(
            "SELECT played_at, result, rounds, kills, coins, suspected_exit, bonds, operators "
            f"FROM matches WHERE {where} ORDER BY played_at, id", params,
        ).fetchall()
    records = candidates if filters.include_exits else [row for row in candidates if not row["suspected_exit"]]
    return stats.overview(records, len(candidates) - len(records), scope)


@app.get("/api/matches")
def matches(
    request: Request, filters: Annotated[Filters, Depends()],
    result: Literal["win", "loss"] | None = None,
    page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    user=Depends(current_user),
):
    where, params = filters.sql(user["id"])
    if result:
        where += " AND result = %s"
        params.append(result)
    with request.app.state.pool.connection() as database:
        database.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        count = database.execute(f"SELECT count(*) AS count FROM matches WHERE {where}", params).fetchone()["count"]
        pages = max(1, (count + limit - 1) // limit)
        page = min(page, pages)
        rows = database.execute(
            f"SELECT {READ_COLUMNS}, bonds FROM matches WHERE {where} "
            "ORDER BY played_at DESC, id DESC LIMIT %s OFFSET %s",
            [*params, limit, (page - 1) * limit],
        ).fetchall()
    for row in rows:
        row["bond_layers"] = stats.bond_total(row)
        del row["bonds"]
    return {"page": page, "pages": pages, "total": count, "matches": rows}


@app.get("/api/matches/{match_id}")
def match(match_id: UUID, request: Request, user=Depends(current_user)):
    with request.app.state.pool.connection() as database:
        row = database.execute(
            f"SELECT {READ_COLUMNS}, sync_count, trophies, duration_seconds, "
            "bonds, squad, bosses FROM matches WHERE user_id = %s AND id = %s",
            (user["id"], match_id),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "战报不存在")
    return row


@app.get("/api/operators")
def operators(
    request: Request, filters: Annotated[Filters, Depends()],
    sort: Literal["count", "win", "name"] = "count",
    q: Annotated[str, Query(max_length=100)] = "", user=Depends(current_user),
):
    where, params = filters.sql(user["id"])
    with request.app.state.pool.connection() as database:
        records = database.execute(
            f"SELECT result, operators FROM matches WHERE {where} ORDER BY played_at, id", params,
        ).fetchall()
    with_squad, entries = stats.operator_stats(records)
    term = q.strip().casefold()
    rows = [row for row in entries if term in row["name"].casefold()]
    keys = {
        "count": lambda row: (-row["count"], row["name"]),
        "win": lambda row: (-row["win_rate"], -row["count"], row["name"]),
        "name": lambda row: row["name"],
    }
    rows.sort(key=keys[sort])
    return {"with_squad": with_squad, "operators": rows}


@app.get("/api/imports")
def imports(request: Request, user=Depends(current_user)):
    with request.app.state.pool.connection() as database:
        return database.execute("""
            SELECT id, status, total, processed, error, created_at, completed_at
            FROM import_jobs WHERE user_id = %s ORDER BY created_at DESC, id DESC LIMIT 20
        """, (user["id"],)).fetchall()


def queue_import(pool, user_id, content):
    try:
        records = read_snapshot(json.loads(content))
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
        raise HTTPException(422, "请选择有效的 JSON 文件") from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    job_id = uuid4()
    with pool.connection() as database:
        database.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,))
        pending = database.execute(
            "SELECT count(*) AS count FROM import_jobs WHERE user_id = %s AND status = 'pending'", (user_id,),
        ).fetchone()["count"]
        if pending >= MAX_PENDING_IMPORTS:
            raise HTTPException(409, "当前有多个导入任务，请稍后重试")
        database.execute("""
            INSERT INTO import_jobs (id, user_id, status, payload, total)
            VALUES (%s, %s, 'pending', %s, %s)
        """, (job_id, user_id, json_param([record.model_dump(mode="json") for record in records]), len(records)))
    return {"id": job_id, "status": "pending", "total": len(records)}


@app.post("/api/imports", status_code=status.HTTP_202_ACCEPTED)
async def upload_snapshot(request: Request, user=Depends(current_user)):
    media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(415, "导入文件必须为 JSON")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "战绩文件不能超过 8 MB")
        content.extend(chunk)
    return await run_in_threadpool(queue_import, request.app.state.pool, user["id"], content)


# ------------------------------------------------------------ 成就档案（鹰角通行证）

ACHV_TTL = timedelta(minutes=10)
ACHV_CACHE: dict[str, tuple[datetime, dict]] = {}
ACHV_LOCK = Lock()


class AchvConnect(BaseModel):
    phone: str | None = Field(default=None, max_length=32)
    password: str | None = Field(default=None, max_length=256)
    token: str | None = Field(default=None, max_length=8192)
    access_token: str | None = Field(default=None, max_length=4096)
    uid: str | None = Field(default=None, max_length=32)


def mask_phone(phone: str | None) -> str | None:
    digits = "".join(character for character in (phone or "") if character.isdigit())
    return f"{digits[:3]}****{digits[-4:]}" if len(digits) >= 7 else None


def achv_state(row) -> dict:
    if row is None:
        return {"connected": False, "source": None, "uid": None, "nickname": None,
                "fetched_at": None, "stale": False, "phone": None}
    fetched = row["fetched_at"]
    stale = (datetime.now(timezone.utc) - fetched) > ACHV_TTL
    return {"connected": True, "source": row["source"], "uid": row["uid"], "nickname": row["nickname"],
            "fetched_at": fetched.isoformat(), "stale": stale, "phone": row["phone_masked"]}


def save_link(request: Request, user_id, source: str, phone: str | None, code: str, uid: str | None,
              payload: dict) -> None:
    now = datetime.now(timezone.utc)
    with request.app.state.pool.connection() as database:
        database.execute("""
            INSERT INTO achv_links
                (user_id, source, phone_masked, u8_token, uid, nickname, payload, fetched_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                source = EXCLUDED.source, phone_masked = EXCLUDED.phone_masked, u8_token = EXCLUDED.u8_token,
                uid = EXCLUDED.uid, nickname = EXCLUDED.nickname, payload = EXCLUDED.payload,
                fetched_at = EXCLUDED.fetched_at, updated_at = EXCLUDED.updated_at
        """, (user_id, source, phone, code, uid, (payload.get("player") or {}).get("nickname"),
              json_param(payload), now, now))
    with ACHV_LOCK:
        ACHV_CACHE[str(user_id)] = (now, payload)


def fetch_link(request: Request, user_id):
    with request.app.state.pool.connection() as database:
        return database.execute("SELECT * FROM achv_links WHERE user_id = %s", (user_id,)).fetchone()


@app.get("/api/achv/status")
def achv_status(request: Request, user=Depends(current_user)):
    row = fetch_link(request, user["id"])
    state = achv_state(row)
    if row is not None:
        cached = ACHV_CACHE.get(str(user["id"]))
        state["payload_ready"] = bool(cached) or row["payload"] is not None
    return state


@app.post("/api/achv/session")
def achv_connect(details: AchvConnect, request: Request, user=Depends(current_user)):
    warnings: list[str] = []
    uid: str | None = None
    phone = mask_phone(details.phone)
    if details.token and details.token.strip():
        source = "token"
        try:
            code = hypergryph.extract_code(details.token)
            data = hypergryph.player_summary(code)
        except hypergryph.CredentialError as error:
            raise HTTPException(424, str(error)) from error
    elif details.access_token and details.access_token.strip():
        source = "hypergryph"
        try:
            uid, code, data, warnings = hypergryph.connect_with_access_token(
                details.access_token.strip(), (details.uid or "").strip())
        except hypergryph.CredentialError as error:
            raise HTTPException(424, str(error)) from error
    elif details.phone and details.password:
        source = "hypergryph"
        try:
            uid, code, data, warnings = hypergryph.connect_with_password(details.phone, details.password)
        except hypergryph.CredentialError as error:
            raise HTTPException(424, str(error)) from error
    else:
        raise HTTPException(422, "请填写手机号与密码，或粘贴成就页链接")
    payload = achievements.normalize(data)
    if warnings:
        payload["warnings"] = warnings
    save_link(request, user["id"], source, phone, code, uid or payload["player"]["uid"], payload)
    return {"state": achv_state(fetch_link(request, user["id"])), "warnings": warnings, "data": payload}


@app.get("/api/achv/summary")
def achv_summary(request: Request, refresh: bool = False, user=Depends(current_user)):
    row = fetch_link(request, user["id"])
    if row is None:
        raise HTTPException(404, "尚未绑定鹰角通行证或成就令牌")
    state = achv_state(row)
    payload = row["payload"] or {}
    warning = None
    if refresh or state["stale"]:
        try:
            data = hypergryph.player_summary(row["u8_token"])
            payload = achievements.normalize(data)
            save_link(request, user["id"], row["source"], row["phone_masked"], row["u8_token"],
                      row["uid"], payload)
            state = achv_state(fetch_link(request, user["id"]))
        except hypergryph.CredentialError as error:
            warning = f"刷新失败，正在展示上次成功的数据：{error}"
    return {"state": state, "warning": warning, "data": payload}


@app.post("/api/achv/import-capture")
def achv_import_capture(request: Request, user=Depends(current_user)):
    """本地便利功能：扫 Reqable 最近抓包，取最新的 u8 token 直接入库。"""
    tokens = capture.candidate_tokens()
    if not tokens:
        raise HTTPException(404, "没在 Reqable 抓包里找到成就接口，先在模拟器里打开一次成就页")
    errors: list[str] = []
    for code, origin in tokens[:8]:
        try:
            data = hypergryph.player_summary(code)
        except hypergryph.CredentialError as error:
            errors.append(f"{origin}: {error}")
            continue
        payload = achievements.normalize(data)
        payload["captured_from"] = origin
        save_link(request, user["id"], "token", None, code, payload["player"]["uid"], payload)
        return {"state": achv_state(fetch_link(request, user["id"])), "warnings": [], "data": payload,
                "source_file": origin, "tried": len(errors) + 1}
    raise HTTPException(424, "抓包里的令牌都失效了：" + "；".join(errors[:2]))


@app.delete("/api/achv/session", status_code=status.HTTP_204_NO_CONTENT)
def achv_disconnect(request: Request, user=Depends(current_user)):
    with request.app.state.pool.connection() as database:
        database.execute("DELETE FROM achv_links WHERE user_id = %s", (user["id"],))
    with ACHV_LOCK:
        ACHV_CACHE.pop(str(user["id"]), None)
