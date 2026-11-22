from contextlib import contextmanager
from uuid import uuid4

from logbook.errors import WriteRejected
from logbook.worker import COLUMNS, UPSERT_MATCH, process_one


class Result:
    def __init__(self, row=None):
        self.row = row

    def fetchone(self):
        return self.row


class Cursor:
    def __init__(self, fail=False):
        self.fail = fail
        self.batches = []

    def executemany(self, sql, rows):
        self.batches.append((sql, list(rows)))
        if self.fail:
            raise WriteRejected("bad row")


class Connection:
    """记录 worker 发起的语句，不需要真实数据库。"""

    def __init__(self, job=None, fail=False):
        self.job = job
        self.cursor_obj = Cursor(fail)
        self.executed = []

    @contextmanager
    def transaction(self):
        yield self

    @contextmanager
    def cursor(self):
        yield self.cursor_obj

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))
        if "SELECT id, role_id, payload, total" in sql:
            return Result(self.job)
        return Result(None)

    def updates(self):
        return [(sql, params) for sql, params in self.executed if sql.startswith("UPDATE import_jobs")]


def payload(records=1):
    row = {column: None for column in COLUMNS}
    row.update({
        "protocol": "V3_1", "external_id": "e1", "played_at": "2026-11-20T21:12:05+08:00",
        "play": "独立模拟", "difficulty": "规程等级 8", "result": "win",
        "suspected_exit": False, "bonds": [], "squad": [], "operators": [], "bosses": [],
    })
    return [dict(row) for _ in range(records)]


def job(records=None):
    return {
        "id": uuid4(),
        "role_id": uuid4(),
        "payload": records if records is not None else payload(),
        "total": 1,
    }


def test_empty_queue_returns_false():
    connection = Connection(job=None)
    assert process_one(connection) is False
    assert connection.updates() == []


def test_successful_import_marks_job_done():
    current = job()
    connection = Connection(job=current)
    assert process_one(connection) is True
    sql, rows = connection.cursor_obj.batches[0]
    assert "ON CONFLICT (role_id, protocol, external_id) DO UPDATE" in sql
    assert len(rows) == 1
    assert rows[0][1] == current["role_id"]
    [(update, params)] = connection.updates()
    assert "status = 'done'" in update
    assert params == (1, current["id"])


def test_failed_import_is_recorded():
    connection = Connection(job=job(), fail=True)
    assert process_one(connection) is True
    [(update, params)] = connection.updates()
    assert "status = 'failed'" in update
    assert params == (connection.job["id"],)


def test_upsert_covers_every_column():
    assert "INSERT INTO matches (id, role_id" in UPSERT_MATCH
    assert "ON CONFLICT" in UPSERT_MATCH
    assert len(COLUMNS) == 20
