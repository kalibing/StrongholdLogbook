import argparse
import getpass
import os
import re
import sys
from uuid import UUID, uuid4

from . import notifications
from .config import settings
from .errors import UniqueConflict
from .security import USERNAME_PATTERN, hasher
from .storage import connect, backend_name


def read_password(parser) -> str:
    """交互输入；CI 或脚本可用 LOGBOOK_ADMIN_PASSWORD 免交互。"""
    preset = os.getenv("LOGBOOK_ADMIN_PASSWORD")
    if preset:
        password, confirm = preset, preset
    else:
        password = getpass.getpass("新密码（至少 12 字符）: ")
        confirm = getpass.getpass("再次输入: ")
    if not 12 <= len(password) <= 256 or password != confirm:
        parser.error("密码长度无效或两次输入不一致")
    return password


def notices(argv) -> None:
    """站内通知：announce 发全站公告，notify 发给单个账号，list 查看，remove 删除。"""
    parser = argparse.ArgumentParser(prog="logbook.admin", description="管理站内通知")
    commands = parser.add_subparsers(dest="command", required=True)
    announce = commands.add_parser("announce", help="发布全站公告")
    announce.add_argument("title")
    announce.add_argument("body")
    notify = commands.add_parser("notify", help="给单个账号发通知")
    notify.add_argument("username")
    notify.add_argument("title")
    notify.add_argument("body")
    commands.add_parser("list-notices", help="列出最近 50 条通知")
    remove = commands.add_parser("remove-notice", help="删除一条通知")
    remove.add_argument("id")
    args = parser.parse_args(argv)
    with connect() as connection:
        if args.command in {"announce", "notify"}:
            user_id = None
            if args.command == "notify":
                account = connection.execute(
                    "SELECT id FROM users WHERE username = %s", (args.username.strip().lower(),),
                ).fetchone()
                if not account:
                    parser.error("账号不存在")
                user_id = account["id"]
            try:
                # 命令行里写字面量 \n 表示换行
                body = args.body.replace("\\n", "\n")
                notice_id = notifications.create(connection, args.title, body, user_id)
            except notifications.NotificationError as error:
                parser.error(str(error))
            print(f"已发布通知 {notice_id}")
        elif args.command == "list-notices":
            for row in notifications.recent(connection):
                print(f"{row['id']}  {row['created_at']:%Y-%m-%d %H:%M}  {row['username'] or '全站'}  {row['title']}")
        else:
            try:
                notice_id = UUID(args.id)
            except ValueError:
                parser.error("通知 ID 格式不正确")
            if not notifications.remove(connection, notice_id):
                parser.error("通知不存在")
            print("已删除")


def admins(argv) -> None:
    """管理员名单：grant-admin / revoke-admin 授予或撤销，list-admins 查看。管理员可在网页发布和删除通知。"""
    parser = argparse.ArgumentParser(prog="logbook.admin", description="管理管理员名单")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, text in (("grant-admin", "授予管理员权限"), ("revoke-admin", "撤销管理员权限")):
        commands.add_parser(name, help=text).add_argument("username")
    commands.add_parser("list-admins", help="列出全部管理员")
    args = parser.parse_args(argv)
    with connect() as connection:
        if args.command == "list-admins":
            for row in connection.execute(
                "SELECT u.username FROM admins AS a JOIN users AS u ON u.id = a.user_id ORDER BY u.username",
            ).fetchall():
                print(row["username"])
            return
        account = connection.execute(
            "SELECT id FROM users WHERE username = %s", (args.username.strip().lower(),),
        ).fetchone()
        if not account:
            parser.error("账号不存在")
        if args.command == "grant-admin":
            connection.execute(
                "INSERT INTO admins (user_id) VALUES (%s) ON CONFLICT DO NOTHING", (account["id"],),
            )
            print("已授予管理员权限")
        else:
            connection.execute("DELETE FROM admins WHERE user_id = %s", (account["id"],))
            print("已撤销管理员权限")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] in {"announce", "notify", "list-notices", "remove-notice"}:
        return notices(sys.argv[1:])
    if len(sys.argv) > 1 and sys.argv[1] in {"grant-admin", "revoke-admin", "list-admins"}:
        return admins(sys.argv[1:])
    parser = argparse.ArgumentParser(
        description="管理站点登录账号；通知命令见 announce / notify / list-notices / remove-notice，"
                    "管理员命令见 grant-admin / revoke-admin / list-admins",
    )
    parser.add_argument("command", choices=["create-user", "reset-password"])
    parser.add_argument("username")
    args = parser.parse_args()
    username = args.username.strip().lower()
    if not re.fullmatch(USERNAME_PATTERN, username):
        parser.error("用户名须为 3–64 位小写字母、数字、点、下划线或连字符")
    password_hash = hasher.hash(read_password(parser))
    try:
        with connect() as connection:
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
                connection.execute("DELETE FROM sessions WHERE user_id = %s", (account["id"],))
    except UniqueConflict:
        parser.error("用户名已存在")
    print(f"账号已更新（{backend_name()}: {settings.sqlite_path if backend_name() == 'sqlite' else 'postgres'}）")


if __name__ == "__main__":
    main()
