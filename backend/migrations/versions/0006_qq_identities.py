"""Accounts created through the QQ official bot, keyed by (bot app id, user openid), with one-time login links."""

from alembic import op

revision = "0006"
down_revision = "0005"


def upgrade():
    op.execute("""
        CREATE TABLE qq_identities (
            bot_app_id text NOT NULL,
            openid text NOT NULL,
            user_id uuid NOT NULL UNIQUE REFERENCES users(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            renamed_at timestamptz,
            password_set_at timestamptz,
            PRIMARY KEY (bot_app_id, openid)
        );
        CREATE TABLE qq_login_links (
            token_hash bytea PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at timestamptz NOT NULL,
            used_at timestamptz
        );
    """)


def downgrade():
    op.execute("DROP TABLE qq_login_links; DROP TABLE qq_identities")
