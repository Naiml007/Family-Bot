"""initial foundation tables (guild_settings, members, audit_log)

Revision ID: 0001_foundation
Revises:
Create Date: 2026-11-25 17:15:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_foundation"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JSONVariant = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "guild_settings",
        sa.Column("guild_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("log_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("error_channel_id", sa.BigInteger(), nullable=True),
        sa.Column("role_map", _JSONVariant, nullable=False),
        sa.Column("enabled_modules", _JSONVariant, nullable=False),
        sa.Column("reminder_config", _JSONVariant, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("guild_id", name=op.f("pk_guild_settings")),
    )

    op.create_table(
        "members",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("discord_id", sa.BigInteger(), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("in_game_name", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_members")),
        sa.UniqueConstraint("guild_id", "discord_id", name="uq_members_guild_discord"),
    )
    op.create_index("ix_members_guild_id", "members", ["guild_id"], unique=False)

    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("guild_id", sa.BigInteger(), nullable=False),
        sa.Column("actor_id", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity", sa.String(length=64), nullable=False),
        sa.Column("entity_id", sa.String(length=128), nullable=False),
        sa.Column("payload", _JSONVariant, nullable=False),
        sa.Column("correlation_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index("ix_audit_log_correlation_id", "audit_log", ["correlation_id"], unique=False)
    op.create_index(
        "ix_audit_log_guild_created", "audit_log", ["guild_id", "created_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_audit_log_guild_created", table_name="audit_log")
    op.drop_index("ix_audit_log_correlation_id", table_name="audit_log")
    op.drop_table("audit_log")

    op.drop_index("ix_members_guild_id", table_name="members")
    op.drop_table("members")

    op.drop_table("guild_settings")
