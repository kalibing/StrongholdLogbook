"""数据库驱动适配层。

业务代码只写一套 PostgreSQL 风格 SQL（``%s`` 占位符、``now()``、``FOR UPDATE``），
这里负责选择驱动并抹平方言差异：

* ``LOGBOOK_DB=postgres``（默认）：psycopg 3 + 连接池，表结构由 Alembic 迁移管理。
* ``LOGBOOK_DB=sqlite``：单文件 SQLite，启动时按 ``sqlite_schema.py`` 建表，
  时间戳存 UTC 秒、JSON 存文本，写事务在进程内串行。

SQLite 适配器改写四处方言：占位符、``now()``、``FOR UPDATE [SKIP LOCKED]``，
并跳过只读事务隔离语句（``SET TRANSACTION ...``）。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from threading import RLock
from uuid import UUID

from .config import settings
from .errors import StorageUnavailable, UniqueConflict, WriteRejected
from .sqlite_schema import ADDED_COLUMNS, SCHEMA

TIMESTAMP_COLUMNS = frozenset({
    "played_at", "created_at", "completed_at", "expires_at", "locked_until", "fetched_at", "updated_at",
    "renamed_at", "password_set_at", "used_at",
})
JSON_COLUMNS = frozenset({"bonds", "squad", "operators", "bosses", "payload"})
BOOL_COLUMNS = frozenset({"suspected_exit"})
SQLITE_NOW = "CAST(strftime('%s','now') AS INTEGER)"


def json_param(value):
    """交给驱动的 JSON 参数：PostgreSQL 需要 Jsonb 包装，SQLite 由适配器编码。"""
    if settings.backend == "sqlite":
        return value
    from psycopg.types.json import Jsonb

    return Jsonb(value)

def import_value(column, value):
    """导入载荷里的字段交给驱动前做一次归一：JSON 包装、SQLite 时间戳解析。"""
    if column in JSON_COLUMNS:
        return json_param(value)
    if settings.backend == "sqlite" and column in TIMESTAMP_COLUMNS and isinstance(value, str):
        return datetime.fromisoformat(value)
    return value

# ---------------------------------------------------------------- PostgreSQL


class PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def executemany(self, sql, rows):
        self._cursor.executemany(sql, rows)


class PostgresConnection:
    """包装 psycopg 连接：把驱动异常翻译成 logbook.errors 里的类型。"""

    name = "postgres"

    def __init__(self, connection):
        self._connection = connection

    def execute(self, sql, params=None):
        from psycopg import DataError, IntegrityError, OperationalError
        from psycopg.errors import UniqueViolation

        try:
            return self._connection.execute(sql, params)
        except UniqueViolation as error:
            raise UniqueConflict(str(error)) from None
        except (DataError, IntegrityError) as error:
            raise WriteRejected(str(error)) from None
        except OperationalError as error:
            raise StorageUnavailable(str(error)) from None

    @contextmanager
    def transaction(self):
        with self._connection.transaction():
            yield self

    @contextmanager
    def cursor(self):
        from psycopg import DataError, IntegrityError, OperationalError
        from psycopg.errors import UniqueViolation

        try:
            with self._connection.cursor() as cursor:
                yield PostgresCursor(cursor)
        except UniqueViolation as error:
            raise UniqueConflict(str(error)) from None
        except (DataError, IntegrityError) as error:
            raise WriteRejected(str(error)) from None
        except OperationalError as error:
            raise StorageUnavailable(str(error)) from None


class PostgresPool:
    name = "postgres"

    def __init__(self):
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        self._pool = ConnectionPool(
            kwargs={**settings.connect_kwargs, "row_factory": dict_row},
            min_size=1, max_size=8, timeout=5, open=False,
        )

    def open(self):
        self._pool.open()

    def close(self):
        self._pool.close()

    @contextmanager
    def connection(self):
        with self._pool.connection() as connection:
            yield PostgresConnection(connection)


# --------------------------------------------------------------------- SQLite


def translate(sql: str) -> str:
    """把 PostgreSQL 风格语句改写成 SQLite 可执行的形式；返回空串表示跳过。"""
    text = " ".join(sql.split())
    if text.upper().startswith("SET TRANSACTION"):
        return ""
    text = text.replace(" FOR UPDATE SKIP LOCKED", "").replace(" FOR UPDATE", "")
    # 先换占位符再换 now()，否则 SQLITE_NOW 里的 '%s' 会被一起替换掉。
    text = text.replace("%s", "?")
    return text.replace("now()", SQLITE_NOW)


def encode(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("写入数据库的 datetime 必须带时区")
        return int(value.timestamp())
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def decode_row(row) -> dict:
    data = dict(row)
    for column, value in data.items():
        if value is None:
            continue
        if column in TIMESTAMP_COLUMNS and isinstance(value, int):
            data[column] = datetime.fromtimestamp(value, timezone.utc)
        elif column in JSON_COLUMNS and isinstance(value, str):
            data[column] = json.loads(value)
        elif column in BOOL_COLUMNS and isinstance(value, int):
            data[column] = bool(value)
    return data


class SqliteCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def fetchone(self):
        row = self._cursor.fetchone()
        return None if row is None else decode_row(row)

    def fetchall(self):
        return [decode_row(row) for row in self._cursor.fetchall()]


class SqliteConnection:
    """包装 sqlite3 连接，使其接口与 psycopg 连接一致。"""

    name = "sqlite"

    def __init__(self, connection, autonomous: bool):
        self._connection = connection
        self._autonomous = autonomous
        self._depth = 0

    def _fail(self, error: Exception):
        if isinstance(error, sqlite3.IntegrityError) and "UNIQUE" in str(error).upper():
            return UniqueConflict(str(error))
        if isinstance(error, sqlite3.OperationalError):
            return StorageUnavailable(str(error))
        return WriteRejected(str(error))

    def execute(self, sql, params=None):
        text = translate(sql)
        if not text:
            return SqliteCursor(self._connection.execute("SELECT 1 WHERE 0"))
        try:
            cursor = self._connection.execute(text, [encode(value) for value in (params or ())])
        except sqlite3.Error as error:
            raise self._fail(error) from None
        return SqliteCursor(cursor)

    def executemany(self, sql, rows):
        try:
            self._connection.executemany(translate(sql), [[encode(value) for value in row] for row in rows])
        except sqlite3.Error as error:
            raise self._fail(error) from None

    @contextmanager
    def transaction(self):
        outermost = self._depth == 0
        savepoint = f"sp_{self._depth + 1}"
        if outermost and self._autonomous:
            self._connection.execute("BEGIN IMMEDIATE")
            finish, undo = "COMMIT", "ROLLBACK"
        else:
            self._connection.execute(f"SAVEPOINT {savepoint}")
            finish, undo = f"RELEASE {savepoint}", f"ROLLBACK TO {savepoint}"
        self._depth += 1
        try:
            yield self
        except BaseException:
            self._connection.execute(undo)
            raise
        else:
            self._connection.execute(finish)
        finally:
            self._depth -= 1

    @contextmanager
    def cursor(self):
        yield self


class SqlitePool:
    """进程内单连接 + 读写锁：FastAPI 的同步端点跑在线程池里，串行化即可。"""

    name = "sqlite"

    def __init__(self, path):
        self._path = path
        self._connection: sqlite3.Connection | None = None
        self._lock = RLock()

    def open(self):
        self._connection = open_sqlite(self._path)

    def close(self):
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @contextmanager
    def connection(self):
        if self._connection is None:
            raise StorageUnavailable("数据库尚未初始化")
        with self._lock:
            wrapped = SqliteConnection(self._connection, autonomous=False)
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield wrapped
            except BaseException:
                self._connection.execute("ROLLBACK")
                raise
            else:
                self._connection.execute("COMMIT")


# ------------------------------------------------------------------ 对外入口


def open_sqlite(path) -> sqlite3.Connection:
    """打开（并按需创建）SQLite 文件，返回可用连接。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA busy_timeout = 5000")
    for statement in SCHEMA:
        connection.execute(statement)
    for table, column, kind in ADDED_COLUMNS:
        if column not in {row["name"] for row in connection.execute(f"PRAGMA table_info({table})")}:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
    return connection


def create_pool():
    return SqlitePool(settings.sqlite_path) if settings.backend == "sqlite" else PostgresPool()


@contextmanager
def connect():
    """给命令行工具与 worker 用的独立连接（自动提交）。"""
    if settings.backend == "sqlite":
        connection = open_sqlite(settings.sqlite_path)
        try:
            yield SqliteConnection(connection, autonomous=True)
        finally:
            connection.close()
        return

    import psycopg
    from psycopg.rows import dict_row

    try:
        connection = psycopg.connect(**settings.connect_kwargs, autocommit=True, row_factory=dict_row)
    except psycopg.OperationalError as error:
        raise StorageUnavailable(str(error)) from None
    try:
        yield PostgresConnection(connection)
    finally:
        connection.close()


def backend_name() -> str:
    return settings.backend

