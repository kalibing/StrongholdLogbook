"""Site administrators: accounts allowed to publish and remove notices from the web UI."""

from alembic import op

revision = "0008"
down_revision = "0007"


def upgrade():
    op.execute("""
        CREATE TABLE admins (
            user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            granted_at timestamptz NOT NULL DEFAULT now()
        )
    """)


def downgrade():
    op.execute("DROP TABLE admins")
