"""achievement links: per-user hypergryph / u8 token binding + cached summary."""

from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade():
    op.execute("""
        CREATE TABLE achv_links (
            user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            source text NOT NULL CHECK (source IN ('hypergryph', 'token')),
            phone_masked text,
            u8_token text NOT NULL,
            uid text,
            nickname text,
            payload jsonb NOT NULL,
            fetched_at timestamptz NOT NULL,
            updated_at timestamptz NOT NULL
        );
    """)


def downgrade():
    op.execute("DROP TABLE achv_links")
