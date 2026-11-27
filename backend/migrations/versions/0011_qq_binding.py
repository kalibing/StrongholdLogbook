"""Link existing web accounts to QQ and verify group member identities."""

from alembic import op

revision = "0011"
down_revision = "0010"


def upgrade():
    op.execute("""
        CREATE TABLE qq_bind_codes (
            user_id uuid PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
            bot_app_id text NOT NULL,
            code_hash bytea NOT NULL UNIQUE,
            expires_at timestamptz NOT NULL
        );
        CREATE TABLE qq_group_identities (
            bot_app_id text NOT NULL,
            group_openid text NOT NULL,
            member_openid text NOT NULL,
            openid text NOT NULL,
            PRIMARY KEY (bot_app_id, group_openid, member_openid),
            FOREIGN KEY (bot_app_id, openid) REFERENCES qq_identities(bot_app_id, openid) ON DELETE CASCADE
        );
        CREATE TABLE qq_group_codes (
            bot_app_id text NOT NULL,
            group_openid text NOT NULL,
            member_openid text NOT NULL,
            request_hash bytea NOT NULL UNIQUE,
            openid text,
            confirmation_hash bytea,
            expires_at timestamptz NOT NULL,
            PRIMARY KEY (bot_app_id, group_openid, member_openid),
            FOREIGN KEY (bot_app_id, openid) REFERENCES qq_identities(bot_app_id, openid) ON DELETE CASCADE
        );
    """)


def downgrade():
    op.execute("DROP TABLE qq_group_codes; DROP TABLE qq_group_identities; DROP TABLE qq_bind_codes")
