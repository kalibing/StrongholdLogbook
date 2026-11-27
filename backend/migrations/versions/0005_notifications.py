"""Site notifications: announcements (user_id NULL) and per-user notices, with read receipts."""

from alembic import op

revision = "0005"
down_revision = "0004"


def upgrade():
    op.execute("""
        CREATE TABLE notifications (
            id uuid PRIMARY KEY,
            user_id uuid REFERENCES users(id) ON DELETE CASCADE,
            title text NOT NULL,
            body text NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX notifications_recent ON notifications (user_id, created_at DESC);
        CREATE TABLE notification_reads (
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            notification_id uuid NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
            PRIMARY KEY (user_id, notification_id)
        );
    """)


def downgrade():
    op.execute("DROP TABLE notification_reads; DROP TABLE notifications")
