"""Add cow_shed_state.collect_role_id.

Revision ID: 0003_cow_shed_role
Revises: 0002_cow_shed
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0003_cow_shed_role"
down_revision: str | None = "0002_cow_shed"


def upgrade() -> None:
    op.add_column("cow_shed_state", sa.Column("collect_role_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("cow_shed_state", "collect_role_id")
