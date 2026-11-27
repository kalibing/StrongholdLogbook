"""B 站登录 Cookie（扫码登录获得，加密存储，只有一行），供动态推送使用。"""

from alembic import op

revision = "0010"
down_revision = "0009"


def upgrade():
    op.execute("""
        CREATE TABLE bili_credentials (
            id integer PRIMARY KEY CHECK (id = 1),
            cookie text NOT NULL,
            uname text NOT NULL DEFAULT '',
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)


def downgrade():
    op.execute("DROP TABLE bili_credentials")
