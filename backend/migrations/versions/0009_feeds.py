"""QQ 推送订阅：群 / 单聊订阅明日方舟游戏公告与 B 站官号动态，以及已推送条目的去重记录。"""

from alembic import op

revision = "0009"
down_revision = "0008"


def upgrade():
    op.execute("""
        CREATE TABLE feed_subscriptions (
            bot_app_id text NOT NULL,
            target_type text NOT NULL CHECK (target_type IN ('group', 'c2c')),
            target_openid text NOT NULL,
            source text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (bot_app_id, target_type, target_openid, source)
        )
    """)
    op.execute("CREATE INDEX feed_subscriptions_source ON feed_subscriptions (bot_app_id, source)")
    op.execute("""
        CREATE TABLE feed_seen (
            source text NOT NULL,
            item_id text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (source, item_id)
        )
    """)


def downgrade():
    op.execute("DROP TABLE feed_seen")
    op.execute("DROP TABLE feed_subscriptions")
