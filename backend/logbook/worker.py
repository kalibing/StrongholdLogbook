import logging
import signal
from collections import Counter
from threading import Event
from uuid import uuid4

from .errors import StorageUnavailable, WriteRejected
from .records import DEFAULT_PROTOCOL
from .storage import connect, import_value

LOGGER = logging.getLogger(__name__)

COLUMNS = (
    "protocol", "external_id", "played_at", "play", "difficulty", "result",
    "scenario", "strategy", "initiator", "rounds", "kills", "coins", "sync_count",
    "trophies", "duration_seconds", "suspected_exit", "bonds", "squad", "operators", "bosses",
)
COLLECTION_COLUMNS = ("bonds", "squad", "operators", "bosses")
OPTIONAL_COLUMNS = (
    "scenario", "strategy", "initiator", "rounds", "kills", "coins", "sync_count", "trophies", "duration_seconds",
)
UPDATE_COLUMNS = (
    "played_at = EXCLUDED.played_at",
    "play = COALESCE(NULLIF(EXCLUDED.play, '未知'), matches.play)",
    "difficulty = COALESCE(NULLIF(EXCLUDED.difficulty, '未知'), matches.difficulty)",
    "result = EXCLUDED.result",
    *(f"{column} = COALESCE(EXCLUDED.{column}, matches.{column})" for column in OPTIONAL_COLUMNS),
    """suspected_exit = CASE
        WHEN %s OR (EXCLUDED.rounds IS NOT NULL AND EXCLUDED.kills IS NOT NULL AND EXCLUDED.coins IS NOT NULL)
            THEN EXCLUDED.suspected_exit
        WHEN EXCLUDED.rounds > 0 OR EXCLUDED.kills > 0 OR EXCLUDED.coins > 0 THEN FALSE
        ELSE matches.suspected_exit END""",
    *(f"{column} = CASE WHEN %s THEN EXCLUDED.{column} ELSE matches.{column} END"
      for column in COLLECTION_COLUMNS),
)
UPSERT_MATCH = (
    "INSERT INTO matches (id, user_id, " + ", ".join(COLUMNS) + ") VALUES ("
    + ", ".join(["%s"] * (2 + len(COLUMNS))) + ") "
    "ON CONFLICT (user_id, protocol, external_id) DO UPDATE SET "
    + ", ".join(UPDATE_COLUMNS)
)


def complete_squad(connection, user_id, record):
    """Preserve unreported unit fields when a unit can be matched unambiguously."""
    squad = record["squad"]
    previous = []
    if any("items" not in unit or unit.get("elite") is None or unit.get("evolve") is None
           or unit["name"] == unit["id"] for unit in squad):
        row = connection.execute(
            "SELECT squad FROM matches WHERE user_id = %s AND protocol = %s AND external_id = %s",
            (user_id, record["protocol"], record["external_id"]),
        ).fetchone()
        previous = row["squad"] if row else []
    current_counts = Counter(unit["id"] for unit in squad)
    previous_counts = Counter(unit["id"] for unit in previous)
    by_id = {unit["id"]: unit for unit in previous
             if current_counts[unit["id"]] == previous_counts[unit["id"]] == 1}
    completed = []
    for unit in squad:
        old = by_id.get(unit["id"], {})
        name = old.get("name", unit["name"]) if unit["name"] == unit["id"] else unit["name"]
        completed.append({
            "id": unit["id"], "name": name, "items": unit.get("items", old.get("items", [])),
            "elite": old.get("elite") if unit.get("elite") is None else unit["elite"],
            "evolve": old.get("evolve") if unit.get("evolve") is None else unit["evolve"],
        })
    return completed


def write_parameters(connection, user_id, record):
    values = {"protocol": DEFAULT_PROTOCOL, **record}
    exit_reported = values.get("suspected_exit") is not None
    if not exit_reported:
        values["suspected_exit"] = values.get("rounds") == values.get("kills") == values.get("coins") == 0
    has_collection = [column in values for column in COLLECTION_COLUMNS]
    if values.get("squad"):
        values["squad"] = complete_squad(connection, user_id, values)
        names = {unit["id"]: unit["name"] for unit in values["squad"]}
        values["operators"] = [
            {**operator, "name": names.get(operator["id"], operator["name"])}
            if operator["name"] == operator["id"] else operator
            for operator in values.get("operators", [])
        ]
    for column in COLLECTION_COLUMNS:
        values.setdefault(column, [])
    return (uuid4(), user_id, *(import_value(column, values.get(column)) for column in COLUMNS),
            exit_reported, *has_collection)


def pending_records(payload):
    if isinstance(payload, dict):
        return payload["matches"]
    # The old queue format filled in missing arrays and could synthesize zero trophies.
    records = []
    for old in payload:
        record = {column: value for column, value in old.items() if column not in COLLECTION_COLUMNS or value}
        if record.get("trophies") == 0:
            del record["trophies"]
        if record.get("squad"):
            record["squad"] = [
                {field: value for field, value in unit.items() if field != "items" or value}
                for unit in record["squad"]
            ]
        records.append(record)
    return records


def process_one(connection) -> bool:
    with connection.transaction():
        job = connection.execute("""
            SELECT job.id, job.user_id, job.payload, job.total FROM import_jobs AS job
            WHERE job.status = 'pending' AND NOT EXISTS (
                SELECT 1 FROM import_jobs AS earlier
                WHERE earlier.user_id = job.user_id AND earlier.status = 'pending'
                    AND (earlier.created_at, earlier.id) < (job.created_at, job.id)
            )
            ORDER BY job.created_at, job.id
            LIMIT 1 FOR UPDATE SKIP LOCKED
        """).fetchone()
        if job is None:
            return False
        job_id, user_id = job["id"], job["user_id"]
        records, total = pending_records(job["payload"]), job["total"]
        try:
            with connection.transaction(), connection.cursor() as cursor:
                cursor.executemany(UPSERT_MATCH, [write_parameters(connection, user_id, record) for record in records])
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
