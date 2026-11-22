import logging
import signal
from threading import Event
from uuid import uuid4

from .errors import StorageUnavailable, WriteRejected
from .storage import connect, import_value

LOGGER = logging.getLogger(__name__)

COLUMNS = (
    "protocol", "external_id", "played_at", "play", "difficulty", "result",
    "scenario", "strategy", "initiator", "rounds", "kills", "coins", "sync_count",
    "trophies", "duration_seconds", "suspected_exit", "bonds", "squad", "operators", "bosses",
)
UPSERT_MATCH = (
    "INSERT INTO matches (id, role_id, " + ", ".join(COLUMNS) + ") VALUES ("
    + ", ".join(["%s"] * (2 + len(COLUMNS))) + ") "
    "ON CONFLICT (role_id, protocol, external_id) DO UPDATE SET "
    + ", ".join(f"{column} = EXCLUDED.{column}" for column in COLUMNS[2:])
)


def process_one(connection) -> bool:
    with connection.transaction():
        job = connection.execute("""
            SELECT id, role_id, payload, total FROM import_jobs
            WHERE status = 'pending' ORDER BY created_at, id
            LIMIT 1 FOR UPDATE SKIP LOCKED
        """).fetchone()
        if job is None:
            return False
        job_id, role_id = job["id"], job["role_id"]
        records, total = job["payload"], job["total"]
        try:
            with connection.transaction(), connection.cursor() as cursor:
                cursor.executemany(UPSERT_MATCH, [
                    (uuid4(), role_id, *(import_value(column, record[column]) for column in COLUMNS))
                    for record in records
                ])
        except WriteRejected:
            connection.execute("""
                UPDATE import_jobs SET status = 'failed', payload = '[]', completed_at = now(),
                    error = '无法写入数据库，请检查文件后重新导入' WHERE id = %s
            """, (job_id,))
            LOGGER.warning("Import failed for job %s", job_id)
        else:
            connection.execute("""
                UPDATE import_jobs SET status = 'done', payload = '[]', processed = %s,
                    completed_at = now() WHERE id = %s
            """, (total, job_id))
        return True


def main():
    logging.basicConfig(level=logging.INFO)
    stop = Event()
    for interrupt in (signal.SIGINT, signal.SIGTERM):
        signal.signal(interrupt, lambda *_: stop.set())
    while not stop.is_set():
        try:
            with connect() as connection:
                while not stop.is_set():
                    if not process_one(connection):
                        stop.wait(2)
        except StorageUnavailable:
            LOGGER.warning("Database connection interrupted; retrying")
            stop.wait(3)


if __name__ == "__main__":
    main()
