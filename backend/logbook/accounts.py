"""站内账号的展示信息：昵称与头像，和登录用户名分开存放（user_profiles 表）。

- 昵称：去掉首尾空白、合并连续空白，1–16 个字符，不允许控制字符；空串视为清除，回落到用户名。
- 头像：只接受 PNG / JPEG / WebP / GIF，最多 2 MB、边长不超过 4096；按 EXIF 摆正、
  居中裁成正方形、缩到 256×256 后重新编码成 PNG。原始字节不落库，顺带丢掉 EXIF 等元数据。
"""

from datetime import datetime, timedelta, timezone
from io import BytesIO
import re
import secrets
import unicodedata
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from . import notifications
from .errors import UniqueConflict
from .security import hasher, session_hash

NAME_LIMIT = 16
AVATAR_BYTES = 2 * 1024 * 1024
AVATAR_EDGE = 4096
AVATAR_SIZE = 256
AVATAR_FORMATS = {"PNG", "JPEG", "WEBP", "GIF"}


class AccountError(ValueError):
    """输入不合法，消息可以直接给用户看。"""


def clean_name(value: str | None) -> str | None:
    if value is None:
        return None
    name = re.sub(r"\s+", " ", value).strip()
    if not name:
        return None
    if any(unicodedata.category(char).startswith("C") for char in name):
        raise AccountError("昵称不能包含控制字符")
    if len(name) > NAME_LIMIT:
        raise AccountError(f"昵称最多 {NAME_LIMIT} 个字")
    return name


def process_avatar(data: bytes) -> bytes:
    if not data:
        raise AccountError("没有收到图片")
    if len(data) > AVATAR_BYTES:
        raise AccountError("图片不能超过 2 MB")
    try:
        with Image.open(BytesIO(data)) as image:
            if image.format not in AVATAR_FORMATS:
                raise AccountError("只支持 PNG、JPEG、WebP 或 GIF 图片")
            if max(image.size) > AVATAR_EDGE:
                raise AccountError(f"图片边长不能超过 {AVATAR_EDGE} 像素")
            image.seek(0)
            frame = ImageOps.exif_transpose(image).convert("RGBA")
    except AccountError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as error:
        raise AccountError("无法识别这张图片") from error
    square = ImageOps.fit(frame, (AVATAR_SIZE, AVATAR_SIZE), Image.Resampling.LANCZOS)
    output = BytesIO()
    square.save(output, format="PNG", optimize=True)
    return output.getvalue()


def avatar_url(version: int | None) -> str | None:
    return f"/api/profile/avatar?v={version}" if version else None


def load(database, user) -> dict:
    """会话、主页共用的账号展示信息。"""
    row = database.execute(
        "SELECT display_name, avatar_version FROM user_profiles WHERE user_id = %s", (user["id"],),
    ).fetchone()
    display_name = row["display_name"] if row else None
    return {
        "username": user["username"],
        "display_name": display_name,
        "avatar_url": avatar_url(row["avatar_version"] if row else None),
        "username_editable": username_editable(database, user["id"]),
        "needs_password": needs_password(database, user["id"]),
    }


def username_editable(database, user_id) -> bool:
    """只有 QQ 机器人渠道建的账号能改一次登录账号；网页注册和命令行建的账号自己定的名，不能改。"""
    return database.execute(
        "SELECT 1 FROM qq_identities WHERE user_id = %s AND renamed_at IS NULL", (user_id,),
    ).fetchone() is not None


# 去掉易混字符（0/O、1/l/I）的字母数字，16 位约 94 bit 熵。
PASSWORD_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PASSWORD_LENGTH = 16


def random_password() -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))


PASSWORD_MIN = 10


def create_with_password(database, username: str, password: str) -> dict:
    """网页注册：用户自己设的密码。长度等格式由调用方先校验；库里只存 Argon2 哈希。"""
    user = {"id": uuid4(), "username": username}
    database.execute(
        "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
        (user["id"], username, hasher.hash(password)),
    )
    return user


def create_with_random_password(database, username: str) -> tuple[dict, str]:
    """建号并生成随机密码，返回 (账号, 明文密码)。明文只交给调用方展示一次，库里只存 Argon2 哈希。

    QQ 机器人渠道建号用；用户名重复时由存储层抛 UniqueConflict。
    """
    password = random_password()
    user = {"id": uuid4(), "username": username}
    database.execute(
        "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
        (user["id"], username, hasher.hash(password)),
    )
    return user, password


# QQ 机器人渠道：官方机器人只提供 openid（拿不到 QQ 号），账号按 (机器人 AppID, openid) 唯一。
# 用户名用保留前缀 + 随机串，网页注册不能占用这个前缀；用户凭机器人私聊发来的用户名和随机密码登录网页。
QQ_USERNAME_PREFIX = "qq-"
QQ_NOTICE_TITLE = "QQ 机器人已为你创建账号"
QQ_NOTICE_BODY = (
    "登录账号：{username}（系统生成）\n"
    "这个账号通过 QQ 机器人私聊发来的一次性链接免密登录，链接 10 分钟内有效、只能用一次。\n"
    "想直接在网页登录，请在弹出的提示里设置密码；账号名也可以顺便改一次。"
)
QQ_USERNAME_ALPHABET = "abcdefghijkmnpqrstuvwxyz23456789"
OPENID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
LOGIN_LINK_TTL = timedelta(minutes=10)


def create_for_qq_openid(database, bot_app_id: str, openid: str) -> dict:
    """按 openid 建号，可重复调用（已有账号时直接返回）。

    新账号没有可用密码（库里是谁也不知道的随机串的哈希），只能用 issue_login_link 签发的
    一次性链接登录，登录后由用户自己设置密码。调用方（QQ 接入服务）必须只传入验签通过的
    回调事件里的 AppID 和 openid。
    """
    if not OPENID_PATTERN.fullmatch(bot_app_id) or not OPENID_PATTERN.fullmatch(openid):
        raise AccountError("AppID 或 openid 格式不正确")
    existing = find_qq_account(database, bot_app_id, openid)
    if existing:
        return existing
    for _ in range(5):
        suffix = "".join(secrets.choice(QQ_USERNAME_ALPHABET) for _ in range(10))
        try:
            with database.transaction():
                user, _unusable = create_with_random_password(database, QQ_USERNAME_PREFIX + suffix)
                database.execute(
                    "INSERT INTO qq_identities (bot_app_id, openid, user_id) VALUES (%s, %s, %s)",
                    (bot_app_id, openid, user["id"]),
                )
                notifications.create(database, QQ_NOTICE_TITLE, QQ_NOTICE_BODY.format(username=user["username"]), user["id"])
            return user
        except UniqueConflict:
            # 用户名随机串撞车，或同一 openid 并发建号：后者重查即可拿到已建好的账号。
            existing = find_qq_account(database, bot_app_id, openid)
            if existing:
                return existing
    raise AccountError("暂时无法创建账号，请稍后重试")


def find_qq_account(database, bot_app_id: str, openid: str) -> dict | None:
    row = database.execute("""
        SELECT users.id, users.username FROM qq_identities JOIN users ON users.id = qq_identities.user_id
        WHERE qq_identities.bot_app_id = %s AND qq_identities.openid = %s
    """, (bot_app_id, openid)).fetchone()
    return {"id": row["id"], "username": row["username"]} if row else None


def issue_login_link(database, user_id, now: datetime | None = None) -> str:
    """签发一次性免密登录令牌（10 分钟、单次使用），库里只存 SHA-256 摘要。

    QQ 接入服务把 {PUBLIC_ORIGIN}/#qq-login=<令牌> 私聊发给本人；令牌放在 # 片段里，
    不会出现在服务器访问日志和 Referer 中。
    """
    now = now or datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    database.execute("DELETE FROM qq_login_links WHERE expires_at <= now() OR used_at IS NOT NULL")
    database.execute(
        "INSERT INTO qq_login_links (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
        (session_hash(token), user_id, now + LOGIN_LINK_TTL),
    )
    return token


def redeem_login_link(database, token: str):
    """核销令牌并返回账号；过期、用过或不存在都返回 None。核销是原子的，同一令牌只能成功一次。"""
    if not token or len(token) > 128:
        return None
    row = database.execute("""
        UPDATE qq_login_links SET used_at = now()
        WHERE token_hash = %s AND used_at IS NULL AND expires_at > now()
        RETURNING user_id
    """, (session_hash(token),)).fetchone()
    if row is None:
        return None
    return database.execute("SELECT id, username FROM users WHERE id = %s", (row["user_id"],)).fetchone()


def needs_password(database, user_id) -> bool:
    return database.execute(
        "SELECT 1 FROM qq_identities WHERE user_id = %s AND password_set_at IS NULL", (user_id,),
    ).fetchone() is not None


def set_initial_password(database, user_id, password: str) -> None:
    """QQ 渠道账号首次设置密码（无需旧密码，因为本来就没有可用密码），只能设一次。"""
    claimed = database.execute(
        "UPDATE qq_identities SET password_set_at = now() WHERE user_id = %s AND password_set_at IS NULL RETURNING user_id",
        (user_id,),
    ).fetchone()
    if claimed is None:
        raise AccountError("该账号已经设置过密码")
    database.execute("UPDATE users SET password_hash = %s WHERE id = %s", (hasher.hash(password), user_id))


def rename_once(database, user_id, new_username: str) -> None:
    """QQ 渠道账号把随机账号名改成自己定的，只能改一次。用户名格式由调用方先校验。"""
    if new_username.startswith(QQ_USERNAME_PREFIX):
        raise AccountError(f"新账号不能以 {QQ_USERNAME_PREFIX} 开头")
    claimed = database.execute(
        "UPDATE qq_identities SET renamed_at = now() WHERE user_id = %s AND renamed_at IS NULL RETURNING user_id",
        (user_id,),
    ).fetchone()
    if claimed is None:
        raise AccountError("账号名只能修改一次，你已经改过或该账号不支持修改")
    database.execute("UPDATE users SET username = %s WHERE id = %s", (new_username, user_id))
