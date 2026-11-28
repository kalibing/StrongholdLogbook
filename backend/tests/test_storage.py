import importlib.util
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
import sqlglot
from alembic import op
from sqlglot import exp

from logbook import storage
from logbook.errors import UniqueConflict
from logbook.sqlite_schema import SCHEMA

BACKEND = Path(__file__).resolve().parents[1]


def test_translate_rewrites_postgres_dialect():
    assert storage.translate("SELECT 1 WHERE a = %s") == "SELECT 1 WHERE a = ?"
    assert "FOR UPDATE" not in storage.translate("SELECT id FROM roles WHERE id = %s FOR UPDATE")
    assert "SKIP LOCKED" not in storage.translate(
        "SELECT id FROM import_jobs WHERE status = 'pending' FOR UPDATE SKIP LOCKED"
    )
    assert storage.translate("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY") == ""
    assert "strftime" in storage.translate("DELETE FROM sessions WHERE expires_at <= now()")


def test_translate_keeps_now_expression_intact():
    translated = storage.translate("UPDATE import_jobs SET completed_at = now() WHERE id = %s")
    assert "strftime('%s','now')" in translated
    assert translated.count("?") == 1
    assert "'?'" not in translated


def test_encode_covers_supported_types():
    moment = datetime(2026, 11, 20, 21, 12, 5, tzinfo=timezone(timedelta(hours=8)))
    assert storage.encode(moment) == int(moment.timestamp())
    assert storage.encode(True) == 1
    assert storage.encode(uuid4()) != ""
    assert storage.encode({"name": "维多利亚"}) == '{"name": "维多利亚"}'
    with pytest.raises(ValueError):
        storage.encode(datetime(2026, 11, 20, 21, 12, 5))


def test_decode_row_restores_types():
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    cursor = connection.execute(
        "SELECT 1 AS played_at, '[{\"name\": \"霜星\"}]' AS bosses, 1 AS suspected_exit, 0 AS kills"
    )
    row = storage.decode_row(cursor.fetchone())
    assert row["played_at"].utcoffset() == timedelta(0)
    assert row["bosses"] == [{"name": "霜星"}]
    assert row["suspected_exit"] is True
    assert row["kills"] == 0


def test_import_value_parses_sqlite_timestamps(monkeypatch):
    monkeypatch.setenv("LOGBOOK_DB", "sqlite")
    value = storage.import_value("played_at", "2026-11-20T21:12:05+08:00")
    assert isinstance(value, datetime)
    assert value.utcoffset() is not None
    assert storage.import_value("bonds", [{"name": "x", "layers": 1}]) == [{"name": "x", "layers": 1}]


def _columns(ddl: str, dialect: str) -> dict[str, set[str]]:
    tables = {}
    for statement in sqlglot.parse(ddl, dialect=dialect):
        if isinstance(statement, exp.Create) and statement.args.get("kind") == "TABLE":
            tables[statement.this.this.name] = {
                column.name for column in statement.this.expressions if isinstance(column, exp.ColumnDef)
            }
        elif isinstance(statement, exp.Alter) and statement.args.get("kind") == "TABLE":
            for action in statement.args.get("actions") or []:
                if isinstance(action, exp.ColumnDef):
                    tables[statement.this.name].add(action.name)
        elif isinstance(statement, exp.Drop) and statement.args.get("kind") == "TABLE":
            for table in statement.args.get("tables") or []:
                tables.pop(table.name, None)
    return tables


def _migration_ddl() -> str:
    """把全部 Alembic 迁移的 DDL 按版本顺序拼起来。"""
    versions = sorted((BACKEND / "migrations" / "versions").glob("*.py"))
    captured: list[str] = []
    for path in versions:
        spec = importlib.util.spec_from_file_location(f"migration_{path.stem}", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        original = op.execute
        op.execute = lambda sql, *args, **kwargs: captured.append(str(sql))
        try:
            module.upgrade()
        finally:
            op.execute = original
    return ";\n".join(captured)


def test_sqlite_schema_matches_alembic_migration():
    postgres = _columns(_migration_ddl(), "postgres")
    sqlite = _columns(";\n".join(SCHEMA).replace("IF NOT EXISTS ", ""), "sqlite")
    assert set(sqlite) == set(postgres)
    for table, columns in postgres.items():
        assert sqlite[table] == columns, table


def test_sqlite_schema_declares_the_same_indexes():
    postgres = set(re.findall(r"CREATE INDEX (\w+)", _migration_ddl()))
    sqlite = set(re.findall(r"CREATE INDEX IF NOT EXISTS (\w+)", "\n".join(SCHEMA)))
    assert sqlite == postgres
    assert "matches_recent" in sqlite


def test_sqlite_pool_round_trip(tmp_path):
    pool = storage.SqlitePool(tmp_path / "db.sqlite3")
    pool.open()
    try:
        with pool.connection() as database:
            database.execute(
                "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
                (uuid4(), "tester", "hash"),
            )
        with pool.connection() as database:
            row = database.execute("SELECT username, failed_logins FROM users").fetchone()
            assert row == {"username": "tester", "failed_logins": 0}
            with pytest.raises(UniqueConflict):
                database.execute(
                    "INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)",
                    (uuid4(), "tester", "hash"),
                )
    finally:
        pool.close()


def test_sqlite_connection_is_reusable_after_failed_statement(tmp_path):
    pool = storage.SqlitePool(tmp_path / "db.sqlite3")
    pool.open()
    try:
        with pytest.raises(UniqueConflict):
            with pool.connection() as database:
                database.execute("INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)", (uuid4(), "a", "h"))
                database.execute("INSERT INTO users (id, username, password_hash) VALUES (%s, %s, %s)", (uuid4(), "a", "h"))
        with pool.connection() as database:
            assert database.execute("SELECT count(*) AS count FROM users").fetchone()["count"] == 0
    finally:
        pool.close()
