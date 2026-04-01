"""Add retry_count and next_retry_at to message_receipts for exponential backoff

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-31
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("message_receipts") as b:
        b.add_column(sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"))
        b.add_column(sa.Column("next_retry_at", sa.DateTime, nullable=True))


def downgrade():
    with op.batch_alter_table("message_receipts") as b:
        b.drop_column("next_retry_at")
        b.drop_column("retry_count")
