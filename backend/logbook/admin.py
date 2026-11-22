import argparse
import getpass
import re
from uuid import uuid4

import psycopg
from psycopg.errors import UniqueViolation

from .config import settings
from .security import USERNAME_PATTERN, hasher


def main() -> None:
    parser = argparse.ArgumentParser(description="管理站点登录账号")
    parser.add_argument("command", choices=["create-user", "reset-password"])
    parser.add_argument("username")
    args = parser.parse_args()
    username = args.username.strip().lower()
    if not re.fullmatch(USERNAME_PATTERN, username):
        parser.error("用户名须为 3–64 位小写字母、数字、点、下划线或连字符")
    password = getpass.getpass("新密码（至少 12 字符）: ")
    if not 12 <= len(password) <= 256 or password != getpass.getpass("再次输入: "):
        parser.error("密码长度无效或两次输入不一致")
    password_hash = hasher.hash(password)
    try:
        with psycopg.connect(**settings.connect_kwargs) as connection:
            if args.command == "create-user":
                connection.execute(
                    "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
                    (uuid4(), username, password_hash),
                )
            else:
                account = connection.execute(
                    "UPDATE users SET password_hash = %s, failed_logins = 0, locked_until = NULL "
                    "WHERE username = %s RETURNING id",
                    (password_hash, username),
                ).fetchone()
                if not account:
                    parser.error("账号不存在")
                connection.execute("DELETE FROM sessions WHERE user_id = %s", account)
    except UniqueViolation:
        parser.error("用户名已存在")
    print("账号已更新")


if __name__ == "__main__":
    main()
