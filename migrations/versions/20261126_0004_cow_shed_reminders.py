"""Add cow_shed_state reminder flags.

Revision ID: 0004_cow_shed_reminders
Revises: 0003_cow_shed_role
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0004_cow_shed_reminders"
down_revision: str | None = "0003_cow_shed_role"


def upgrade() -> None:
    op.add_column(
        "cow_shed_state",
        sa.Column("reminders_active", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "cow_shed_state", sa.Column("last_reminder_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("cow_shed_state", "last_reminder_at")
    op.drop_column("cow_shed_state", "reminders_active")
