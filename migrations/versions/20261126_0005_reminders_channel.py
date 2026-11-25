"""Add dedicated reminders channel and persistent cow embed id.

Revision ID: 0005_reminders_channel
Revises: 0004_cow_shed_reminders
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0005_reminders_channel"
down_revision: str | None = "0004_cow_shed_reminders"


def upgrade() -> None:
    op.add_column(
        "guild_settings",
        sa.Column("reminders_channel_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "cow_shed_state",
        sa.Column("reminder_message_id", sa.BigInteger(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cow_shed_state", "reminder_message_id")
    op.drop_column("guild_settings", "reminders_channel_id")
