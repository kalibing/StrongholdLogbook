"""Display name and avatar, kept apart from the login username."""

from alembic import op

revision = "0004"
down_revision = "0003"


def upgrade():
    op.execute("""
        CREATE TABLE user_profiles (
            user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            display_name text,
            avatar bytea,
            avatar_version bigint NOT NULL DEFAULT 0
        );
    """)


def downgrade():
    op.execute("DROP TABLE user_profiles")
