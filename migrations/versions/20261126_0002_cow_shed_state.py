"""Add cow_shed_state table.

Revision ID: 0002_cow_shed
Revises: 0001_foundation
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0002_cow_shed"
down_revision: str | None = "0001_foundation"


def upgrade() -> None:
    op.create_table(
        "cow_shed_state",
        sa.Column("guild_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("fed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("collect_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("guild_id", name=op.f("pk_cow_shed_state")),
    )


def downgrade() -> None:
    op.drop_table("cow_shed_state")
