"""Users, role archives, and durable imports."""

from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    op.execute("""
        CREATE TABLE users (
            id uuid PRIMARY KEY,
            username text NOT NULL UNIQUE,
            password_hash text NOT NULL,
            failed_logins integer NOT NULL DEFAULT 0,
            locked_until timestamptz
        );
        CREATE TABLE sessions (
            token_hash bytea PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at timestamptz NOT NULL
        );
        CREATE INDEX sessions_expiration ON sessions (expires_at);
        CREATE TABLE roles (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            UNIQUE (user_id, name)
        );
        CREATE TABLE matches (
            id uuid PRIMARY KEY,
            role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            protocol text NOT NULL,
            external_id text NOT NULL,
            played_at timestamptz NOT NULL,
            play text NOT NULL,
            difficulty text NOT NULL,
            result text NOT NULL CHECK (result IN ('win', 'loss')),
            scenario text,
            strategy text,
            initiator text,
            rounds integer,
            kills integer,
            coins integer,
            sync_count integer,
            trophies integer,
            duration_seconds integer,
            suspected_exit boolean NOT NULL,
            bonds jsonb NOT NULL,
            squad jsonb NOT NULL,
            operators jsonb NOT NULL,
            bosses jsonb NOT NULL,
            UNIQUE (role_id, protocol, external_id)
        );
        CREATE INDEX matches_recent ON matches (role_id, played_at DESC, id DESC);
        CREATE TABLE import_jobs (
            id uuid PRIMARY KEY,
            role_id uuid NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
            status text NOT NULL CHECK (status IN ('pending', 'done', 'failed')),
            payload jsonb NOT NULL,
            total integer NOT NULL,
            processed integer NOT NULL DEFAULT 0,
            error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            completed_at timestamptz
        );
        CREATE INDEX pending_import_jobs ON import_jobs (created_at, id) WHERE status = 'pending';
        CREATE INDEX role_import_jobs ON import_jobs (role_id, created_at DESC);
    """)


def downgrade():
    op.execute("DROP TABLE import_jobs, matches, roles, sessions, users")
