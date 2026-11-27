"""Let site administrators manage destinations for group feed pushes."""

from alembic import op

revision = "0012"
down_revision = "0011"


def upgrade():
    op.execute("""
        CREATE TABLE qq_feed_groups (
            bot_app_id text NOT NULL,
            group_openid text NOT NULL,
            group_number text,
            updated_at timestamptz NOT NULL,
            PRIMARY KEY (bot_app_id, group_openid),
            UNIQUE (bot_app_id, group_number)
        );
        INSERT INTO qq_feed_groups (bot_app_id, group_openid, updated_at)
        SELECT bot_app_id, target_openid, max(created_at) FROM feed_subscriptions
        WHERE target_type = 'group'
        GROUP BY bot_app_id, target_openid;
    """)


def downgrade():
    op.execute("DROP TABLE qq_feed_groups")
