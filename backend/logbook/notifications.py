"""站内通知：全站公告（user_id 为 NULL）与发给单个账号的通知，按账号记录已读。

正文按纯文本存储和展示（前端不会当 HTML 渲染），只去掉控制字符并限制长度。
发通知的入口：命令行（admin announce / notify）、服务端流程（如注册欢迎），
以及仅限管理员账号的 /api/admin/notifications 接口。
"""

import unicodedata
from uuid import UUID, uuid4

TITLE_LIMIT = 60
BODY_LIMIT = 2000
LIST_LIMIT = 50


class NotificationError(ValueError):
    pass


def clean(value: str, limit: int, field: str, multiline: bool) -> str:
    allowed = {"\n"} if multiline else set()
    text = "".join(
        char for char in value.replace("\r\n", "\n")
        if char in allowed or not unicodedata.category(char).startswith("C")
    ).strip()
    if not text:
        raise NotificationError(f"{field}不能为空")
    if len(text) > limit:
        raise NotificationError(f"{field}最多 {limit} 个字")
    return text


def create(database, title: str, body: str, user_id=None) -> UUID:
    notification_id = uuid4()
    database.execute(
        "INSERT INTO notifications (id, user_id, title, body) VALUES (%s, %s, %s, %s)",
        (notification_id, user_id, clean(title, TITLE_LIMIT, "标题", False), clean(body, BODY_LIMIT, "正文", True)),
    )
    return notification_id


def visible(database, user_id) -> list[dict]:
    rows = database.execute("""
        SELECT n.id, n.user_id, n.title, n.body, n.created_at, r.notification_id AS read_id
        FROM notifications AS n
        LEFT JOIN notification_reads AS r ON r.notification_id = n.id AND r.user_id = %s
        WHERE n.user_id = %s OR n.user_id IS NULL
        ORDER BY n.created_at DESC, n.id DESC
        LIMIT %s
    """, (user_id, user_id, LIST_LIMIT)).fetchall()
    return [{
        "id": str(row["id"]),
        "kind": "personal" if row["user_id"] is not None else "announcement",
        "title": row["title"],
        "body": row["body"],
        "created_at": row["created_at"],
        "read": row["read_id"] is not None,
    } for row in rows]


def summary(database, user_id) -> dict:
    items = visible(database, user_id)
    return {"unread": sum(not item["read"] for item in items), "items": items}


def mark_read(database, user_id, ids: list[UUID] | None) -> None:
    """ids 为空时标记全部可见通知；只会登记该账号能看到的通知。"""
    for item in visible(database, user_id):
        if item["read"] or (ids is not None and UUID(item["id"]) not in ids):
            continue
        database.execute(
            "INSERT INTO notification_reads (user_id, notification_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (user_id, UUID(item["id"])),
        )


def recent(database) -> list[dict]:
    """管理视角：最近的全部通知（含发给个人的），附收件人账号名。"""
    rows = database.execute("""
        SELECT n.id, n.title, n.body, n.created_at, u.username FROM notifications AS n
        LEFT JOIN users AS u ON u.id = n.user_id
        ORDER BY n.created_at DESC, n.id DESC LIMIT %s
    """, (LIST_LIMIT,)).fetchall()
    return [{
        "id": str(row["id"]),
        "kind": "announcement" if row["username"] is None else "personal",
        "username": row["username"],
        "title": row["title"],
        "body": row["body"],
        "created_at": row["created_at"],
    } for row in rows]


def remove(database, notification_id: UUID) -> bool:
    return database.execute(
        "DELETE FROM notifications WHERE id = %s RETURNING id", (notification_id,),
    ).fetchone() is not None
