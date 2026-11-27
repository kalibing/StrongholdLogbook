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
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id TEXT PRIMARY KEY,
        user_id TEXT REFERENCES users(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        created_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
    )
    """,
    "CREATE INDEX IF NOT EXISTS notifications_recent ON notifications (user_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS notification_reads (
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        notification_id TEXT NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
        PRIMARY KEY (user_id, notification_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS admins (
        user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        granted_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qq_identities (
        bot_app_id TEXT NOT NULL,
        openid TEXT NOT NULL,
        user_id TEXT NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
        created_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
        renamed_at INTEGER,
        password_set_at INTEGER,
        PRIMARY KEY (bot_app_id, openid)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qq_login_links (
        token_hash BLOB PRIMARY KEY,
        user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        expires_at INTEGER NOT NULL,
        used_at INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qq_bind_codes (
        user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        bot_app_id TEXT NOT NULL,
        code_hash BLOB NOT NULL UNIQUE,
        expires_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qq_group_identities (
        bot_app_id TEXT NOT NULL,
        group_openid TEXT NOT NULL,
        member_openid TEXT NOT NULL,
        openid TEXT NOT NULL,
        PRIMARY KEY (bot_app_id, group_openid, member_openid),
        FOREIGN KEY (bot_app_id, openid) REFERENCES qq_identities(bot_app_id, openid) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS qq_group_codes (
        bot_app_id TEXT NOT NULL,
        group_openid TEXT NOT NULL,
        member_openid TEXT NOT NULL,
        request_hash BLOB NOT NULL UNIQUE,
        openid TEXT,
        confirmation_hash BLOB,
        expires_at INTEGER NOT NULL,
        PRIMARY KEY (bot_app_id, group_openid, member_openid),
        FOREIGN KEY (bot_app_id, openid) REFERENCES qq_identities(bot_app_id, openid) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feed_subscriptions (
        bot_app_id TEXT NOT NULL,
        target_type TEXT NOT NULL CHECK (target_type IN ('group', 'c2c')),
        target_openid TEXT NOT NULL,
        source TEXT NOT NULL,
        created_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
        PRIMARY KEY (bot_app_id, target_type, target_openid, source)
    )
    """,
    "CREATE INDEX IF NOT EXISTS feed_subscriptions_source ON feed_subscriptions (bot_app_id, source)",
    """
    CREATE TABLE IF NOT EXISTS qq_feed_groups (
        bot_app_id TEXT NOT NULL,
        group_openid TEXT NOT NULL,
        group_number TEXT,
        updated_at INTEGER NOT NULL,
        PRIMARY KEY (bot_app_id, group_openid),
        UNIQUE (bot_app_id, group_number)
    )
    """,
    """
    INSERT INTO qq_feed_groups (bot_app_id, group_openid, updated_at)
    SELECT bot_app_id, target_openid, max(created_at) FROM feed_subscriptions
    WHERE target_type = 'group'
    GROUP BY bot_app_id, target_openid
    ON CONFLICT DO NOTHING
    """,
    """
    CREATE TABLE IF NOT EXISTS bili_credentials (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        cookie TEXT NOT NULL,
        uname TEXT NOT NULL DEFAULT '',
        updated_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER))
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS feed_seen (
        source TEXT NOT NULL,
        item_id TEXT NOT NULL,
        created_at INTEGER NOT NULL DEFAULT (CAST(strftime('%s','now') AS INTEGER)),
        PRIMARY KEY (source, item_id)
    )
    """,
)
