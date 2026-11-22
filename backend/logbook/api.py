from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import json
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout
from pydantic import BaseModel, Field, StringConstraints
from starlette.concurrency import run_in_threadpool

from . import stats
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
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.headers.get("origin") != settings.public_origin:
        response = JSONResponse({"detail": "请求来源无效"}, 403)
    else:
        response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


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


def distribution_label(play: str, difficulty: str) -> str:
    if play == "联合模拟":
        return difficulty if difficulty in UNION_TIERS else "其他"
    for low, high, label in SOLO_RANGES:
        level = difficulty.replace("规程等级", "").strip()
        if level.isdigit() and low <= int(level) <= high:
            return label
    if difficulty == "极速模拟":
        return "极速模拟"
    return "其他"


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
        key = (row["play"], distribution_label(row["play"], row["difficulty"]))
        bucket = counts.setdefault(key, [0, 0])
        bucket[0 if row["result"] == "win" else 1] += 1

    order = {"联合模拟": list(UNION_TIERS) + ["其他"], "独立模拟": [label for _, _, label in SOLO_RANGES] + ["极速模拟", "其他"]}
    result = []
    for play in ("联合模拟", "独立模拟"):
        labels = order[play]
        buckets = []
        for label in labels:
            wins, losses = counts.get((play, label), (0, 0))
            buckets.append({"label": label, "wins": wins, "losses": losses, "total": wins + losses})
        extra = sorted({key[1] for key in counts if key[0] == play} - set(labels))
        for label in extra:
            wins, losses = counts[(play, label)]
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
