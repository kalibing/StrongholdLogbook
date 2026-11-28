"""QQ 绑定：私聊用绑定码关联已有站点账号；群成员通过私聊收到的一次性链接关联站点账号。"""

from datetime import datetime, timedelta, timezone
import secrets

from .accounts import AccountError
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


GROUP_LINK_TTL = timedelta(minutes=10)
NICKNAME_LIMIT = 64


def group_account(database, app_id, group_openid, member_openid):
    """群成员已关联的站点账号；没有关联时返回 None。"""
    row = database.execute("""
        SELECT users.id, users.username FROM qq_group_members JOIN users ON users.id = qq_group_members.user_id
        WHERE qq_group_members.bot_app_id = %s AND qq_group_members.group_openid = %s
            AND qq_group_members.member_openid = %s
    """, (app_id, group_openid, member_openid)).fetchone()
    return {"id": row["id"], "username": row["username"]} if row else None


def clean_nickname(value) -> str:
    if not isinstance(value, str):
        return ""
    return "".join(char for char in value if char.isprintable()).strip()[:NICKNAME_LIMIT]


def issue_group_link(database, app_id, group_openid, member_openid, nickname=""):
    """签发群身份关联令牌（10 分钟、单次使用），库里只存摘要；每个群成员同时只有一个有效令牌。

    令牌只通过「群消息私聊回复」发给这条群消息的发送者，所以拿着它打开网页的就是这个群成员本人
    （或本人转交的人）。
    """
    token = secrets.token_urlsafe(32)
    database.execute("DELETE FROM qq_group_links WHERE expires_at <= now()")
    database.execute("""
        INSERT INTO qq_group_links (token_hash, bot_app_id, group_openid, member_openid, nickname, expires_at)
        VALUES (%s, %s, %s, %s, %s, %s)
        ON CONFLICT (bot_app_id, group_openid, member_openid) DO UPDATE SET
            token_hash = excluded.token_hash, nickname = excluded.nickname, expires_at = excluded.expires_at
    """, (session_hash(token), app_id, group_openid, member_openid, clean_nickname(nickname),
          datetime.now(timezone.utc) + GROUP_LINK_TTL))
    return token


def valid_token(token) -> bool:
    return isinstance(token, str) and 0 < len(token) <= 128


def group_link_info(database, app_id, token):
    """确认页展示用：群昵称与管理员配置的群号（没配置时为 None）。令牌无效返回 None。"""
    if not valid_token(token):
        return None
    row = database.execute("""
        SELECT links.nickname, groups.group_number FROM qq_group_links AS links
        LEFT JOIN qq_feed_groups AS groups
            ON groups.bot_app_id = links.bot_app_id AND groups.group_openid = links.group_openid
        WHERE links.bot_app_id = %s AND links.token_hash = %s AND links.expires_at > now()
    """, (app_id, session_hash(token))).fetchone()
    return {"nickname": row["nickname"], "group_number": row["group_number"]} if row else None


def confirm_group_link(database, app_id, token, user_id) -> None:
    """核销令牌，把群成员关联到 user_id；已有关联时改为新账号（本人重新证明了对这个群身份的控制）。"""
    if not valid_token(token):
        raise AccountError("关联链接无效或已过期，请在群里重新 @机器人 获取")
    with database.transaction():
        link = database.execute("""
            DELETE FROM qq_group_links WHERE bot_app_id = %s AND token_hash = %s AND expires_at > now()
            RETURNING group_openid, member_openid
        """, (app_id, session_hash(token))).fetchone()
        if not link:
            raise AccountError("关联链接无效或已过期，请在群里重新 @机器人 获取")
        database.execute("""
            INSERT INTO qq_group_members (bot_app_id, group_openid, member_openid, user_id)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (bot_app_id, group_openid, member_openid) DO UPDATE SET user_id = excluded.user_id
        """, (app_id, link["group_openid"], link["member_openid"], user_id))


def unbind_group(database, app_id, group_openid, member_openid) -> bool:
    return database.execute("""
        DELETE FROM qq_group_members WHERE bot_app_id = %s AND group_openid = %s AND member_openid = %s
        RETURNING user_id
    """, (app_id, group_openid, member_openid)).fetchone() is not None
