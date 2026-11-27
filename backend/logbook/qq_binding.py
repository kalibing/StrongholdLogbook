"""One-time proofs for private account binding and QQ group membership."""

from datetime import datetime, timedelta, timezone
import secrets

from .accounts import AccountError, find_qq_account
from .security import session_hash


CODE_TTL = timedelta(minutes=10)
CODE_PATTERN = r"[A-Z][A-HJ-NP-Z2-9]{12}"
ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def new_code(prefix):
    return prefix + "".join(secrets.choice(ALPHABET) for _ in range(12))


def expires():
    return datetime.now(timezone.utc) + CODE_TTL


def private_bound(database, app_id, user_id):
    return database.execute(
        "SELECT 1 FROM qq_identities WHERE bot_app_id = %s AND user_id = %s", (app_id, user_id),
    ).fetchone() is not None


def issue_account_code(database, app_id, user_id):
    with database.transaction():
        database.execute("SELECT id FROM users WHERE id = %s FOR UPDATE", (user_id,))
        if database.execute("SELECT 1 FROM qq_identities WHERE user_id = %s", (user_id,)).fetchone():
            raise AccountError("该站点账号已绑定 QQ")
        code = new_code("W")
        database.execute("""
            INSERT INTO qq_bind_codes (user_id, bot_app_id, code_hash, expires_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (user_id) DO UPDATE SET bot_app_id = excluded.bot_app_id,
                code_hash = excluded.code_hash, expires_at = excluded.expires_at
        """, (user_id, app_id, session_hash(code), expires()))
    return code


def bind_account(database, app_id, openid, code):
    with database.transaction():
        # Lock the account first, in the same order as issue_account_code.
        candidate = database.execute("""
            SELECT id FROM users WHERE id = (
                SELECT user_id FROM qq_bind_codes WHERE bot_app_id = %s AND code_hash = %s AND expires_at > now()
            ) FOR UPDATE
        """, (app_id, session_hash(code))).fetchone()
        if not candidate:
            raise AccountError("绑定码无效或已过期，请在个人主页重新获取")
        user_id = candidate["id"]
        consumed = database.execute("""
            DELETE FROM qq_bind_codes WHERE user_id = %s AND code_hash = %s AND expires_at > now()
            RETURNING user_id
        """, (user_id, session_hash(code))).fetchone()
        if not consumed:
            raise AccountError("绑定码无效或已过期，请在个人主页重新获取")
        identity = database.execute("""
            INSERT INTO qq_identities (bot_app_id, openid, user_id, renamed_at, password_set_at)
            VALUES (%s, %s, %s, now(), now()) ON CONFLICT DO NOTHING RETURNING user_id
        """, (app_id, openid, user_id)).fetchone()
        if not identity:
            raise AccountError("该 QQ 或站点账号已绑定，现有绑定无法覆盖")


def group_account(database, app_id, group_openid, member_openid):
    row = database.execute("""
        SELECT openid FROM qq_group_identities
        WHERE bot_app_id = %s AND group_openid = %s AND member_openid = %s
    """, (app_id, group_openid, member_openid)).fetchone()
    # Reuse a private binding when QQ supplies the same user OpenID for this bot.
    # Groups with a different member OpenID use their explicitly verified association.
    openid = row["openid"] if row else member_openid
    return find_qq_account(database, app_id, openid)


def issue_group_code(database, app_id, group_openid, member_openid):
    code = new_code("G")
    database.execute("DELETE FROM qq_group_codes WHERE expires_at <= now()")
    database.execute("""
        INSERT INTO qq_group_codes (bot_app_id, group_openid, member_openid, request_hash, expires_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (bot_app_id, group_openid, member_openid) DO UPDATE SET
            request_hash = excluded.request_hash, expires_at = excluded.expires_at,
            openid = NULL, confirmation_hash = NULL
    """, (app_id, group_openid, member_openid, session_hash(code), expires()))
    return code


def confirm_in_private(database, app_id, openid, code):
    if not find_qq_account(database, app_id, openid):
        raise AccountError("请先认证 QQ：已有站点账号可在「我的主页」获取绑定码；新用户私聊发「登录」即可注册并自动绑定。")
    confirmation = new_code("C")
    matched = database.execute("""
        UPDATE qq_group_codes SET openid = %s, confirmation_hash = %s
        WHERE bot_app_id = %s AND request_hash = %s AND expires_at > now()
        RETURNING member_openid
    """, (openid, session_hash(confirmation), app_id, session_hash(code))).fetchone()
    if not matched:
        raise AccountError("群验证码无效或已过期，请在群里重新请求昨日战报")
    return confirmation


def confirm_in_group(database, app_id, group_openid, member_openid, code):
    with database.transaction():
        matched = database.execute("""
            DELETE FROM qq_group_codes WHERE bot_app_id = %s AND group_openid = %s AND member_openid = %s
                AND confirmation_hash = %s AND expires_at > now()
            RETURNING openid
        """, (app_id, group_openid, member_openid, session_hash(code))).fetchone()
        if not matched:
            raise AccountError("确认码无效或已过期，请用发起请求的 QQ 在原群重试")
        database.execute("""
            INSERT INTO qq_group_identities (bot_app_id, group_openid, member_openid, openid)
            VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING
        """, (app_id, group_openid, member_openid, matched["openid"]))
        return group_account(database, app_id, group_openid, member_openid)
