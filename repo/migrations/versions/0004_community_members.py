"""Add community_members table for group message membership tracking

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-01
"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "community_members",
        sa.Column("membership_id", sa.String(36), primary_key=True),
        sa.Column("community_id", sa.String(36),
                  sa.ForeignKey("communities.community_id"), nullable=False),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.user_id"), nullable=False),
        sa.Column("joined_at", sa.DateTime, nullable=False),
        sa.Column("left_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("community_id", "user_id", name="uix_community_member"),
    )
    op.create_index("ix_community_members_community_id", "community_members", ["community_id"])
    op.create_index("ix_community_members_user_id", "community_members", ["user_id"])


def downgrade():
    op.drop_index("ix_community_members_user_id", "community_members")
    op.drop_index("ix_community_members_community_id", "community_members")
    op.drop_table("community_members")
