"""站内账号的展示信息：昵称与头像，和登录用户名分开存放（user_profiles 表）。

- 昵称：去掉首尾空白、合并连续空白，1–16 个字符，不允许控制字符；空串视为清除，回落到用户名。
- 头像：只接受 PNG / JPEG / WebP / GIF，最多 2 MB、边长不超过 4096；按 EXIF 摆正、
  居中裁成正方形、缩到 256×256 后重新编码成 PNG。原始字节不落库，顺带丢掉 EXIF 等元数据。
"""

from io import BytesIO
import re
import secrets
import unicodedata
from uuid import uuid4

from PIL import Image, ImageOps, UnidentifiedImageError

from .security import hasher

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
    }


# 去掉易混字符（0/O、1/l/I）的字母数字，16 位约 94 bit 熵。
PASSWORD_ALPHABET = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PASSWORD_LENGTH = 16


def random_password() -> str:
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(PASSWORD_LENGTH))


def create_with_random_password(database, username: str) -> tuple[dict, str]:
    """建号并生成随机密码，返回 (账号, 明文密码)。明文只交给调用方展示一次，库里只存 Argon2 哈希。

    网页 QQ 号注册和之后的 QQ 机器人建号共用这一个入口；用户名重复时由存储层抛 UniqueConflict。
    """
    password = random_password()
    user = {"id": uuid4(), "username": username}
    database.execute(
        "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
        (user["id"], username, hasher.hash(password)),
    )
    return user, password
