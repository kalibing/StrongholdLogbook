from collections import Counter
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
import json
import re
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, status
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from psycopg_pool import PoolTimeout
from pydantic import BaseModel, Field, StringConstraints
from starlette.concurrency import run_in_threadpool

from . import accounts, achievements, daily_card, daily_review, hypergryph, profile, skland, stats
from .config import settings
from .credentials import ACHIEVEMENTS, SKLAND, CredentialStorageError, initialize_vault
from .db import connection_pool
from .errors import UniqueConflict
from .limits import FailureThrottle, RequestSizeLimit
from .records import CHINA, Filters, read_snapshot
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
        with pool.connection() as database:
            application.state.credentials = initialize_vault(database)
        yield
    finally:
        pool.close()


app = FastAPI(title="卫戍协议战绩档案", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.add_middleware(RequestSizeLimit)
# 按来源 IP 限制登录失败次数，防止换着账号名撞库；账号级锁定见 login()。
login_throttle = FailureThrottle()


@app.middleware("http")
async def protect_requests(request: Request, call_next):
    if (
        request.method in {"POST", "PUT", "PATCH", "DELETE"}
        and request.headers.get("origin") != settings.public_origin
    ):
        response = JSONResponse({"detail": "请求来源无效"}, 403)
    else:
        response = await call_next(request)
    # 默认不缓存；个别响应（如带版本号的头像）自己声明缓存策略。
    response.headers.setdefault("Cache-Control", "no-store")
    return response


@app.exception_handler(PoolTimeout)
async def database_unavailable(_request, _error):
    return JSONResponse({"detail": "数据库暂不可用，请稍后重试"}, 503)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, error: RequestValidationError):
    if request.method == "POST" and request.url.path in {"/api/session", "/api/achv/session"}:
        # Pydantic's default validation response includes the submitted input.
        return JSONResponse({"detail": "凭据格式或长度无效"}, status_code=422)
    return await request_validation_exception_handler(request, error)


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
def session(request: Request, user=Depends(current_user)):
    with request.app.state.pool.connection() as database:
        return accounts.load(database, user)


@app.post("/api/session")
def login(details: Login, request: Request, response: Response):
    client = request.client.host if request.client else "unknown"
    if login_throttle.blocked(client):
        raise HTTPException(429, "登录尝试过多，请稍后重试")
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
        login_throttle.failed(client)
        raise HTTPException(401, "用户名或密码错误")
    with request.app.state.pool.connection() as database:
        account = accounts.load(database, user)
    response.set_cookie(
        COOKIE, token, max_age=int(SESSION_TTL.total_seconds()), httponly=True,
        secure=settings.cookie_secure, samesite="strict", path="/",
    )
    return account


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


# PRTS「卫戍协议·规程」逐级列出规程等级，并单列极速模拟。
SOLO_TIERS = ("极速模拟", *(f"规程等级 {level}" for level in range(1, 21)))
UNION_TIERS = ("标准模拟", "险境模拟", "绝境模拟", "终极模拟")
LEGACY_TIERS = ("入门协议", "同盟模拟")
DIFFICULTY_ORDER = {
    "联合模拟": (*LEGACY_TIERS, *UNION_TIERS),
    "独立模拟": (*SOLO_TIERS, *LEGACY_TIERS, *UNION_TIERS),
}


def distribution_label(play: str, difficulty: str) -> str:
    level = re.fullmatch(r"规程等级\s*(\d{1,2})", difficulty)
    label = f"规程等级 {int(level[1])}" if level else difficulty
    return label if label in DIFFICULTY_ORDER.get(play, ()) else "其他难度"


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
            f"SELECT play, difficulty, result, bosses FROM matches WHERE {where}", params,
        ).fetchall()

    counts: dict[str, dict[str, Counter[str]]] = {}
    for row in rows:
        play = row["play"] if row["play"] in DIFFICULTY_ORDER else "其他模拟方式"
        label = distribution_label(play, row["difficulty"])
        bucket = counts.setdefault(play, {}).setdefault(label, Counter())
        won = row["result"] == "win"
        bucket["wins" if won else "losses"] += 1
        boss_types = {"hidden" if hidden else "normal" for hidden in daily_review.defeated_bosses(row["bosses"]).values()}
        bucket.update(boss_types)
        if boss_types and not won:
            bucket["boss_losses"] += 1

    result = []
    for play in (*DIFFICULTY_ORDER, "其他模拟方式"):
        group = counts.get(play)
        if not group:
            continue
        buckets = []
        for label in (*DIFFICULTY_ORDER.get(play, ()), "其他难度"):
            if label not in group:
                continue
            bucket = group[label]
            buckets.append({
                "label": label, "wins": bucket["wins"], "losses": bucket["losses"],
                "total": bucket["wins"] + bucket["losses"], "hidden": bucket["hidden"],
                "normal_boss": bucket["normal"], "boss_losses": bucket["boss_losses"],
            })
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
            "SELECT id, played_at, result, strategy, rounds, kills, coins, trophies, suspected_exit, bonds, operators "
            f"FROM matches WHERE {where} ORDER BY played_at, id", params,
        ).fetchall()
        trophies = trophy_summary(database, user["id"])
    records = candidates if filters.include_exits else [row for row in candidates if not row["suspected_exit"]]
    return {**stats.overview(records, len(candidates) - len(records), scope), **trophies}


def trophy_summary(database, user_id) -> dict:
    """奖杯是账号累计值，不随筛选变化：优先用成就档案，没绑定时用全部对局的奖杯记录累加兜底。"""
    link = database.execute("SELECT payload FROM achv_links WHERE user_id = %s", (user_id,)).fetchone()
    recorded = database.execute(
        "SELECT SUM(trophies) AS total, COUNT(trophies) AS counted FROM matches WHERE user_id = %s", (user_id,),
    ).fetchone()
    payload = (link["payload"] if link else None) or {}
    trophy = payload.get("trophy")
    badge = {"icon": trophy.get("icon"), "level": trophy.get("level")} if trophy else None
    if trophy and trophy.get("total") is not None:
        total = {"total": trophy["total"], "source": "profile"}
    elif recorded and recorded["counted"]:
        total = {"total": max(0, int(recorded["total"] or 0)), "source": "matches"}
    else:
        total = None
    return {"trophy_badge": badge, "trophy_total": total}


@app.get("/api/career")
def career(request: Request, filters: Annotated[Filters, Depends()], user=Depends(current_user)):
    """战绩总览「生涯档案」：最高通关、连胜、生涯纪录与近一年活跃度，跟随筛选条件。"""
    where, params = filters.model_copy(update={"include_exits": True}).sql(user["id"])
    with request.app.state.pool.connection() as database:
        rows = database.execute(
            "SELECT played_at, play, difficulty, result, kills, duration_seconds, suspected_exit, bonds "
            f"FROM matches WHERE {where} ORDER BY played_at, id", params,
        ).fetchall()
    kept = rows if filters.include_exits else [row for row in rows if not row["suspected_exit"]]
    return profile.summarize(kept, len(rows) - len(kept), datetime.now(CHINA).date())


@app.get("/api/profile")
def my_profile(request: Request, user=Depends(current_user)):
    """个人主页：站内昵称 / 头像，以及已绑定成就档案时的游戏昵称（只给展示字段）。"""
    with request.app.state.pool.connection() as database:
        link = database.execute("SELECT nickname, payload FROM achv_links WHERE user_id = %s", (user["id"],)).fetchone()
        identity = accounts.load(database, user)
    payload = (link["payload"] if link else None) or {}
    player = payload.get("player") or {}
    # 不返回 uid、手机号、令牌。
    account = {
        "nickname": player.get("nickname") or (link["nickname"] if link else None),
        "nick_number": player.get("nick_number"),
        "level": player.get("level"),
        "likes": payload.get("likes"),
        "titles": len(payload.get("titles") or []),
    } if link else None
    return {**identity, "account": account}


class ProfileUpdate(BaseModel):
    display_name: Annotated[str, StringConstraints(max_length=64)] | None = None


@app.patch("/api/profile")
def update_profile(details: ProfileUpdate, request: Request, user=Depends(current_user)):
    """改昵称；传空串或 null 清除昵称，页面回落显示用户名。用户名本身不可改。"""
    try:
        name = accounts.clean_name(details.display_name)
    except accounts.AccountError as error:
        raise HTTPException(422, str(error)) from error
    with request.app.state.pool.connection() as database:
        database.execute(
            "INSERT INTO user_profiles (user_id, display_name) VALUES (%s, %s) "
            "ON CONFLICT (user_id) DO UPDATE SET display_name = excluded.display_name",
            (user["id"], name),
        )
        return accounts.load(database, user)


@app.put("/api/profile/avatar")
async def upload_avatar(request: Request, user=Depends(current_user)):
    """请求体直接是图片字节（Content-Type: image/*）；服务端裁成 256×256 PNG 后保存。"""
    if not request.headers.get("content-type", "").startswith("image/"):
        raise HTTPException(415, "请上传图片文件")
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > accounts.AVATAR_BYTES:
        raise HTTPException(413, "图片不能超过 2 MB")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > accounts.AVATAR_BYTES:
            raise HTTPException(413, "图片不能超过 2 MB")
    try:
        avatar = await run_in_threadpool(accounts.process_avatar, bytes(body))
    except accounts.AccountError as error:
        raise HTTPException(422, str(error)) from error
    version = int(datetime.now(timezone.utc).timestamp() * 1000)

    def save():
        with request.app.state.pool.connection() as database:
            database.execute(
                "INSERT INTO user_profiles (user_id, avatar, avatar_version) VALUES (%s, %s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET avatar = excluded.avatar, avatar_version = excluded.avatar_version",
                (user["id"], avatar, version),
            )
            return accounts.load(database, user)

    return await run_in_threadpool(save)


@app.delete("/api/profile/avatar")
def delete_avatar(request: Request, user=Depends(current_user)):
    with request.app.state.pool.connection() as database:
        database.execute(
            "UPDATE user_profiles SET avatar = NULL, avatar_version = 0 WHERE user_id = %s", (user["id"],),
        )
        return accounts.load(database, user)


@app.get("/api/profile/avatar", response_class=Response, responses={200: {"content": {"image/png": {}}}})
def avatar(request: Request, user=Depends(current_user)):
    """只返回当前登录用户自己的头像；URL 带版本号，换头像后地址会变，所以可以长缓存。"""
    with request.app.state.pool.connection() as database:
        row = database.execute("SELECT avatar FROM user_profiles WHERE user_id = %s", (user["id"],)).fetchone()
    if not row or not row["avatar"]:
        raise HTTPException(404, "还没有设置头像")
    return Response(bytes(row["avatar"]), media_type="image/png", headers={
        "Cache-Control": "private, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
    })


def daily_review_data(request, day, user_id):
    where, params = Filters(start=day, end=day).sql(user_id)
    with request.app.state.pool.connection() as database:
        rows = database.execute(
            "SELECT id, played_at, result, play, difficulty, rounds, kills, coins, duration_seconds, bonds, bosses "
            f"FROM matches WHERE {where} ORDER BY played_at DESC, id DESC", params,
        ).fetchall()
    return daily_review.summarize(rows)


@app.get("/api/daily-review")
def daily_review_summary(day: date, request: Request, user=Depends(current_user)):
    return {**daily_review_data(request, day, user["id"]), "ai_available": daily_review.model_config() is not None}


@app.get("/api/daily-review/image", response_class=Response, responses={200: {"content": {"image/png": {}}}})
def daily_review_image(request: Request, day: date | None = None, user=Depends(current_user)):
    """昨日战报图片（PNG）。不传 day 时取北京时间的昨天；口径与网页昨日战报一致。"""
    day = day or (datetime.now(CHINA).date() - timedelta(days=1))
    where, params = Filters(start=day, end=day, include_exits=True).sql(user["id"])
    with request.app.state.pool.connection() as database:
        rows = database.execute(
            "SELECT id, played_at, result, play, difficulty, strategy, rounds, kills, coins, trophies, "
            f"duration_seconds, suspected_exit, bonds, bosses FROM matches WHERE {where} ORDER BY played_at DESC, id DESC",
            params,
        ).fetchall()
    kept = [row for row in rows if not row["suspected_exit"]]
    try:
        png = daily_card.render(daily_card.build(kept, len(rows) - len(kept), day, user["username"]))
    except daily_card.CardFontError as error:
        raise HTTPException(503, str(error)) from error
    return Response(png, media_type="image/png", headers={
        "Cache-Control": "private, no-store",
        "Content-Disposition": f'inline; filename="daily-{day.isoformat()}.png"',
    })


@app.post("/api/daily-review")
def daily_review_analysis(day: date, request: Request, user=Depends(current_user)):
    config = daily_review.model_config()
    if config is None:
        raise HTTPException(503, "战报分析模型尚未配置")
    recap = daily_review_data(request, day, user["id"])
    if not recap["wins"]["matches"] and not recap["losses"]["matches"]:
        raise HTTPException(422, "当天暂无可分析的对局")
    try:
        return {"analysis": daily_review.analyze(config, recap)}
    except ValueError as error:
        raise HTTPException(502, "分析服务暂未返回有效结果，请稍后重试") from error


@app.get("/api/matches")
def matches(
    request: Request, filters: Annotated[Filters, Depends()],
    result: Literal["win", "loss"] | None = None,
    page: Annotated[int, Query(ge=1, le=1_000_000)] = 1,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    include_breakdown: bool = False,
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
        columns = READ_COLUMNS + (", bonds, bosses" if include_breakdown else ", bonds")
        rows = database.execute(
            f"SELECT {columns} FROM matches WHERE {where} "
            "ORDER BY played_at DESC, id DESC LIMIT %s OFFSET %s",
            [*params, limit, (page - 1) * limit],
        ).fetchall()
    for row in rows:
        row["bond_layers"] = stats.bond_total(row)
        if not include_breakdown:
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


@app.get("/api/strategies")
def strategies(request: Request, filters: Annotated[Filters, Depends()], user=Depends(current_user)):
    """完整策略列表；记录里可能存 band id 或策略名，展示名与搜索交给前端统一解析。"""
    where, params = filters.sql(user["id"])
    with request.app.state.pool.connection() as database:
        records = database.execute(
            f"SELECT result, strategy FROM matches WHERE {where} ORDER BY played_at, id", params,
        ).fetchall()
    with_strategy = sum(bool((row["strategy"] or "").strip()) for row in records)
    rows = stats.strategy_stats(records)
    return {
        "matches": len(records), "with_strategy": with_strategy,
        "strategies": [{**row, "losses": row["count"] - row["wins"],
                        "usage_rate": row["count"] / with_strategy} for row in rows],
    }


@app.get("/api/imports")
def imports(request: Request, user=Depends(current_user)):
    with request.app.state.pool.connection() as database:
        return database.execute("""
            SELECT id, status, total, processed, error, created_at, completed_at
            FROM import_jobs WHERE user_id = %s ORDER BY created_at DESC, id DESC LIMIT 20
        """, (user["id"],)).fetchall()


def queue_import(pool, user_id, content, *, sealed_token=None):
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
        payload = {"matches": [record.import_payload() for record in records]}
        database.execute("""
            INSERT INTO import_jobs (id, user_id, status, payload, total)
            VALUES (%s, %s, 'pending', %s, %s)
        """, (job_id, user_id, json_param(payload), len(records)))
        if sealed_token is not None:
            database.execute("""
                INSERT INTO skland_import_tokens (user_id, access_token) VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE SET access_token = EXCLUDED.access_token
            """, (user_id, sealed_token))
    return {"id": job_id, "status": "pending", "total": len(records)}


@app.get("/api/imports/skland/token")
def skland_token_status(request: Request, user=Depends(current_user)):
    with request.app.state.pool.connection() as database:
        saved = database.execute(
            "SELECT 1 FROM skland_import_tokens WHERE user_id = %s", (user["id"],),
        ).fetchone()
    return {"saved": saved is not None}


@app.delete("/api/imports/skland/token", status_code=status.HTTP_204_NO_CONTENT)
def clear_skland_token(request: Request, user=Depends(current_user)):
    with request.app.state.pool.connection() as database:
        database.execute("DELETE FROM skland_import_tokens WHERE user_id = %s", (user["id"],))


@app.post("/api/imports/skland", status_code=status.HTTP_202_ACCEPTED)
async def import_from_skland(request: Request, user=Depends(current_user)):
    """从森空岛拉最新战绩（固定 100 条）并入库。

      {"cred": "...", "sign_token": "..."}   —— 森空岛凭据
      {"token": "<鹰角 access token>"}       —— 导入入队后保存 token
      {"use_saved_token": true}             —— 使用当前账号已保存的 token
    """
    content_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    body: dict = {}
    if content_type == "application/json":
        raw = await request.body()
        if raw.strip():
            try:
                body = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError) as error:
                raise HTTPException(422, "请求体不是合法 JSON") from error

    if not isinstance(body, dict) or any(
        body.get(field) is not None and not isinstance(body[field], str)
        for field in ("cred", "sign_token", "token", "season")
    ):
        raise HTTPException(422, "导入凭据格式不正确")

    cred = (body.get("cred") or "").strip()
    sign_token = (body.get("sign_token") or "").strip()
    access_token = (body.get("token") or "").strip()
    season = (body.get("season") or skland.SEASON).strip()
    use_saved = body.get("use_saved_token") is True and not (cred or sign_token or access_token)
    token_to_save = access_token if access_token and not (cred and sign_token) else None

    if not use_saved and not (cred and sign_token) and not access_token:
        raise HTTPException(422, "请提供森空岛凭据（cred + sign_token）或鹰角 token")

    pool = request.app.state.pool
    user_id = user["id"]
    vault = request.app.state.credentials

    def pull() -> dict:
        pull_cred, pull_sign = cred, sign_token
        token = access_token
        if use_saved:
            with pool.connection() as database:
                saved = database.execute(
                    "SELECT access_token FROM skland_import_tokens WHERE user_id = %s", (user_id,),
                ).fetchone()
            if saved is None:
                raise HTTPException(404, "当前账号没有已保存的 token，请重新填写。")
            try:
                token = vault.unseal(SKLAND, user_id, saved["access_token"])
            except CredentialStorageError as error:
                raise HTTPException(424, "无法读取已保存的 token，请更换后重试。") from error
        try:
            if not pull_cred or not pull_sign:
                pull_cred, pull_sign = skland.cred_from_token(token)
            role = skland.arknights_role(pull_cred, pull_sign)
            records = skland.history(pull_cred, pull_sign, role, season)
            return skland.to_snapshot(records)
        except skland.AccessTokenRejected as error:
            if use_saved:
                raise HTTPException(424, "已保存的 token 无法通过鹰角验证，请更换后重试。") from error
            raise HTTPException(424, str(error)) from error
        except skland.SklandError as error:
            raise HTTPException(424, str(error)) from error

    snapshot = await run_in_threadpool(pull)
    if not snapshot["matches"]:
        raise HTTPException(404, "森空岛没有返回可导入的战绩")
    sealed_token = vault.seal(SKLAND, user_id, token_to_save) if token_to_save else None
    job = await run_in_threadpool(queue_import, pool, user_id,
                                  json.dumps(snapshot, ensure_ascii=False).encode(), sealed_token=sealed_token)
    return {**job, "source": "skland", "records": len(snapshot["matches"]),
            "operators": len(snapshot["operators"]), "token_saved": token_to_save is not None}


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
    stale = fetched.astimezone(CHINA).date() < datetime.now(CHINA).date()
    return {"connected": True, "source": row["source"], "uid": row["uid"], "nickname": row["nickname"],
            "fetched_at": fetched.isoformat(), "stale": stale, "phone": row["phone_masked"]}


def save_link(request: Request, user_id, source: str, phone: str | None, code: str, uid: str | None,
              payload: dict) -> None:
    now = datetime.now(timezone.utc)
    sealed_token = request.app.state.credentials.seal(ACHIEVEMENTS, user_id, code)
    with request.app.state.pool.connection() as database:
        database.execute("""
            INSERT INTO achv_links
                (user_id, source, phone_masked, u8_token, uid, nickname, payload, fetched_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET
                source = EXCLUDED.source, phone_masked = EXCLUDED.phone_masked, u8_token = EXCLUDED.u8_token,
                uid = EXCLUDED.uid, nickname = EXCLUDED.nickname, payload = EXCLUDED.payload,
                fetched_at = EXCLUDED.fetched_at, updated_at = EXCLUDED.updated_at
        """, (user_id, source, phone, sealed_token, uid, (payload.get("player") or {}).get("nickname"),
              json_param(payload), now, now))


def fetch_link(request: Request, user_id):
    with request.app.state.pool.connection() as database:
        return database.execute("SELECT * FROM achv_links WHERE user_id = %s", (user_id,)).fetchone()


@app.get("/api/achv/status")
def achv_status(request: Request, user=Depends(current_user)):
    row = fetch_link(request, user["id"])
    state = achv_state(row)
    if row is not None:
        state["payload_ready"] = row["payload"] is not None
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
    if refresh:
        try:
            code = request.app.state.credentials.unseal(ACHIEVEMENTS, user["id"], row["u8_token"])
            data = hypergryph.player_summary(code)
            updated = achievements.normalize(data)
            now = datetime.now(timezone.utc)
            with request.app.state.pool.connection() as database:
                database.execute(
                    "UPDATE achv_links SET nickname = %s, payload = %s, fetched_at = %s, updated_at = %s "
                    "WHERE user_id = %s AND fetched_at = %s AND u8_token = %s",
                    (updated["player"]["nickname"], json_param(updated), now, now,
                     user["id"], row["fetched_at"], row["u8_token"]),
                )
            latest = fetch_link(request, user["id"])
            if latest is None:
                raise HTTPException(404, "尚未绑定鹰角通行证或成就令牌")
            state = achv_state(latest)
            payload = latest["payload"] or {}
        except hypergryph.CredentialError as error:
            warning = f"刷新失败，正在展示上次成功的数据：{error}"
        except CredentialStorageError:
            warning = "无法读取已保存的成就令牌。正在展示上次成功的数据，请重新绑定。"
    return {"state": state, "warning": warning, "data": payload}


@app.delete("/api/achv/session", status_code=status.HTTP_204_NO_CONTENT)
def achv_disconnect(request: Request, user=Depends(current_user)):
    with request.app.state.pool.connection() as database:
        database.execute("DELETE FROM achv_links WHERE user_id = %s", (user["id"],))
