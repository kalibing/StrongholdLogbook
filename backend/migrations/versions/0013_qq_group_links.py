"""Bind QQ group members to site accounts through one-time links sent by private reply.

The bot replies privately to a group message's sender (QQ「群消息私聊回复」) with a link;
opening it while signed in associates that group member with the signed-in account.
This replaces the request / confirmation codes of 0011.
"""

from alembic import op

revision = "0013"
down_revision = "0012"


def upgrade():
    op.execute("""
        CREATE TABLE qq_group_members (
            bot_app_id text NOT NULL,
            group_openid text NOT NULL,
            member_openid text NOT NULL,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (bot_app_id, group_openid, member_openid)
        );
        INSERT INTO qq_group_members (bot_app_id, group_openid, member_openid, user_id)
        SELECT groups.bot_app_id, groups.group_openid, groups.member_openid, identities.user_id
        FROM qq_group_identities AS groups
        JOIN qq_identities AS identities
            ON identities.bot_app_id = groups.bot_app_id AND identities.openid = groups.openid;
        CREATE TABLE qq_group_links (
            token_hash bytea PRIMARY KEY,
            bot_app_id text NOT NULL,
            group_openid text NOT NULL,
            member_openid text NOT NULL,
            nickname text NOT NULL DEFAULT '',
            expires_at timestamptz NOT NULL,
            UNIQUE (bot_app_id, group_openid, member_openid)
        );
        DROP TABLE qq_group_codes;
        DROP TABLE qq_group_identities;
    """)


def downgrade():
    op.execute("""
        CREATE TABLE qq_group_identities (
            bot_app_id text NOT NULL,
            group_openid text NOT NULL,
            member_openid text NOT NULL,
            openid text NOT NULL,
            PRIMARY KEY (bot_app_id, group_openid, member_openid),
            FOREIGN KEY (bot_app_id, openid) REFERENCES qq_identities(bot_app_id, openid) ON DELETE CASCADE
        );
        INSERT INTO qq_group_identities (bot_app_id, group_openid, member_openid, openid)
        SELECT members.bot_app_id, members.group_openid, members.member_openid, identities.openid
        FROM qq_group_members AS members
        JOIN qq_identities AS identities
            ON identities.bot_app_id = members.bot_app_id AND identities.user_id = members.user_id;
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
        DROP TABLE qq_group_links;
        DROP TABLE qq_group_members;
    """)
