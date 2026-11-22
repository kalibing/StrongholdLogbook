from .storage import create_pool


def connection_pool():
    """按 LOGBOOK_DB 选择 PostgreSQL 连接池或单文件 SQLite。"""
    return create_pool()
