"""SQLite 后端的内置表结构。

与 PostgreSQL 迁移保持一致：表名、列名、唯一约束与索引相同，
只把 PostgreSQL 的 uuid / timestamptz / jsonb / bytea 映射成 TEXT / INTEGER / TEXT / BLOB。
时间戳统一存 UTC 秒级整数，由 storage 适配层转回带时区的 datetime。
"""

SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        failed_logins INTEGER NOT NULL DEFAULT 0,
        locked_until INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        token_hash BLOB PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        expires_at INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS sessions_expiration ON sessions (expires_at)",
    """
    CREATE TABLE IF NOT EXISTS matches (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        protocol TEXT NOT NULL,
        external_id TEXT NOT NULL,
        played_at INTEGER NOT NULL,
        play TEXT NOT NULL,
        difficulty TEXT NOT NULL,
        result TEXT NOT NULL CHECK (result IN ('win', 'loss')),
        scenario TEXT,
        strategy TEXT,
        initiator TEXT,
        rounds INTEGER,
        kills INTEGER,
        coins INTEGER,
        sync_count INTEGER,
        trophies INTEGER,
        duration_seconds INTEGER,
        suspected_exit INTEGER NOT NULL,
        bonds TEXT NOT NULL,
        squad TEXT NOT NULL,
        operators TEXT NOT NULL,
        bosses TEXT NOT NULL,
        UNIQUE (user_id, protocol, external_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS matches_recent ON matches (user_id, played_at DESC, id DESC)",
    """
    CREATE TABLE IF NOT EXISTS import_jobs (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        status TEXT NOT NULL CHECK (status IN ('pending', 'done', 'failed')),
        payload TEXT NOT NULL,
        total INTEGER NOT NULL,
        processed INTEGER NOT NULL DEFAULT 0,
        error TEXT,
        created_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
        completed_at INTEGER
    )
    """,
    "CREATE INDEX IF NOT EXISTS pending_import_jobs ON import_jobs (created_at, id) WHERE status = 'pending'",
    "CREATE INDEX IF NOT EXISTS user_import_jobs ON import_jobs (user_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS skland_import_tokens (
        user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        access_token TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS skland_profiles (
        user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        nickname TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS achv_links (
        user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        source TEXT NOT NULL CHECK (source IN ('hypergryph', 'token')),
        phone_masked TEXT,
        u8_token TEXT NOT NULL,
        uid TEXT,
        nickname TEXT,
        payload TEXT NOT NULL,
        fetched_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS user_profiles (
        user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        display_name TEXT,
        avatar BLOB,
        avatar_version INTEGER NOT NULL DEFAULT 0
    )
    """,
)
