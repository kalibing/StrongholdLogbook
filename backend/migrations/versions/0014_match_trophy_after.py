"""Keep each match's absolute trophy count after it ended (森空岛 ``trophyAfter``).

The overview's trophy total then follows whichever is newer: the achievement profile
snapshot or the latest imported match.
"""

from alembic import op

revision = "0014"
down_revision = "0013"


def upgrade():
    op.execute("ALTER TABLE matches ADD COLUMN trophy_after integer")


def downgrade():
    op.execute("ALTER TABLE matches DROP COLUMN trophy_after")
