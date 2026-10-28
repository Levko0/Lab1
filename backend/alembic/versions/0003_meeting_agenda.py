"""add agenda and ai_suggestion columns to meetings

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("meetings", sa.Column("agenda", JSONB, nullable=True))
    op.add_column("meetings", sa.Column("ai_suggestion", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("meetings", "ai_suggestion")
    op.drop_column("meetings", "agenda")
