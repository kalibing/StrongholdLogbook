"""Store the in-game nickname from the Skland role used for imports."""

from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade():
    op.execute("""
        CREATE TABLE skland_profiles (
            user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            nickname text
        )
    """)


def downgrade():
    op.execute("DROP TABLE skland_profiles")
