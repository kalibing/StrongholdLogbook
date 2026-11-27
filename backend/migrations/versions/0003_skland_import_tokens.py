"""Remember the access token used for each user's Skland imports."""

from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade():
    op.execute("""
        CREATE TABLE skland_import_tokens (
            user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            access_token text NOT NULL
        );
    """)


def downgrade():
    op.execute("DROP TABLE skland_import_tokens")
