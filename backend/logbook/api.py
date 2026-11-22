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
MAX_ROLES = 20
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


class RoleInput(BaseModel):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60)]


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


def require_role(role_id: UUID, request: Request, user=Depends(current_user)):
    with request.app.state.pool.connection() as database:
        role = database.execute(
            "SELECT id, name FROM roles WHERE id = %s AND user_id = %s", (role_id, user["id"]),
        ).fetchone()
    if role is None:
        raise HTTPException(404, "角色档案不存在")
    return role_id


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


@app.get("/api/roles")
def roles(request: Request, user=Depends(current_user)):
    with request.app.state.pool.connection() as database:
        return database.execute(
            "SELECT id, name FROM roles WHERE user_id = %s ORDER BY created_at, id", (user["id"],),
        ).fetchall()


@app.post("/api/roles", status_code=status.HTTP_201_CREATED)
def create_role(details: RoleInput, request: Request, user=Depends(current_user)):
    role_id = uuid4()
    try:
        with request.app.state.pool.connection() as database:
            database.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user["id"],))
            total = database.execute(
                "SELECT count(*) AS count FROM roles WHERE user_id = %s", (user["id"],),
            ).fetchone()["count"]
            if total >= MAX_ROLES:
                raise HTTPException(409, f"最多可建立 {MAX_ROLES} 个角色档案")
            database.execute(
                "INSERT INTO roles (id, user_id, name) VALUES (%s, %s, %s)",
                (role_id, user["id"], details.name),
            )
    except UniqueConflict as exc:
        raise HTTPException(409, "已存在同名角色档案") from exc
    return {"id": role_id, "name": details.name}


@app.patch("/api/roles/{role_id}")
def rename_role(details: RoleInput, request: Request, role_id=Depends(require_role)):
    try:
        with request.app.state.pool.connection() as database:
            database.execute("UPDATE roles SET name = %s WHERE id = %s", (details.name, role_id))
    except UniqueConflict as exc:
        raise HTTPException(409, "已存在同名角色档案") from exc
    return {"id": role_id, "name": details.name}


@app.delete("/api/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(request: Request, role_id=Depends(require_role)):
    with request.app.state.pool.connection() as database:
        database.execute("DELETE FROM roles WHERE id = %s", (role_id,))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/roles/{role_id}/facets")
def facets(request: Request, role_id=Depends(require_role)):
    with request.app.state.pool.connection() as database:
        return database.execute("""
            SELECT DISTINCT protocol, play, difficulty FROM matches WHERE role_id = %s
            ORDER BY protocol, play, difficulty
        """, (role_id,)).fetchall()


@app.get("/api/roles/{role_id}/overview")
def overview(
    request: Request, filters: Annotated[Filters, Depends()],
    scope: Literal["recent", "all", "day"] = "recent", role_id=Depends(require_role),
):
    where, params = filters.model_copy(update={"include_exits": True}).sql(role_id)
    with request.app.state.pool.connection() as database:
        candidates = database.execute(
            "SELECT played_at, result, rounds, kills, coins, suspected_exit, bonds, operators "
            f"FROM matches WHERE {where} ORDER BY played_at, id", params,
        ).fetchall()
    records = candidates if filters.include_exits else [row for row in candidates if not row["suspected_exit"]]
    return stats.overview(records, len(candidates) - len(records), scope)


@app.get("/api/roles/{role_id}/matches")
def matches(
    request: Request, filters: Annotated[Filters, Depends()],
    result: Literal["win", "loss"] | None = None,
    page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    role_id=Depends(require_role),
):
    where, params = filters.sql(role_id)
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


@app.get("/api/roles/{role_id}/matches/{match_id}")
def match(match_id: UUID, request: Request, role_id=Depends(require_role)):
    with request.app.state.pool.connection() as database:
        row = database.execute(
            f"SELECT {READ_COLUMNS}, scenario, sync_count, trophies, duration_seconds, "
            "bonds, squad, bosses FROM matches WHERE role_id = %s AND id = %s",
            (role_id, match_id),
        ).fetchone()
    if row is None:
        raise HTTPException(404, "战报不存在")
    return row


@app.get("/api/roles/{role_id}/operators")
def operators(
    request: Request, filters: Annotated[Filters, Depends()],
    sort: Literal["count", "win", "name"] = "count",
    q: Annotated[str, Query(max_length=100)] = "", role_id=Depends(require_role),
):
    where, params = filters.sql(role_id)
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


@app.get("/api/roles/{role_id}/imports")
def imports(request: Request, role_id=Depends(require_role)):
    with request.app.state.pool.connection() as database:
        return database.execute("""
            SELECT id, status, total, processed, error, created_at, completed_at
            FROM import_jobs WHERE role_id = %s ORDER BY created_at DESC, id DESC LIMIT 20
        """, (role_id,)).fetchall()


def queue_import(pool, role_id, content):
    try:
        records = read_snapshot(json.loads(content))
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError) as error:
        raise HTTPException(422, "请选择有效的 JSON 文件") from error
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
    job_id = uuid4()
    with pool.connection() as database:
        database.execute("SELECT id FROM roles WHERE id = %s FOR UPDATE", (role_id,))
        pending = database.execute(
            "SELECT count(*) AS count FROM import_jobs WHERE role_id = %s AND status = 'pending'", (role_id,),
        ).fetchone()["count"]
        if pending >= MAX_PENDING_IMPORTS:
            raise HTTPException(409, "当前有多个导入任务，请稍后重试")
        database.execute("""
            INSERT INTO import_jobs (id, role_id, status, payload, total)
            VALUES (%s, %s, 'pending', %s, %s)
        """, (job_id, role_id, json_param([record.model_dump(mode="json") for record in records]), len(records)))
    return {"id": job_id, "status": "pending", "total": len(records)}


@app.post("/api/roles/{role_id}/imports", status_code=status.HTTP_202_ACCEPTED)
async def upload_snapshot(request: Request, role_id=Depends(require_role)):
    media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media_type != "application/json":
        raise HTTPException(415, "导入文件必须为 JSON")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "战绩文件不能超过 8 MB")
        content.extend(chunk)
    return await run_in_threadpool(queue_import, request.app.state.pool, role_id, content)
