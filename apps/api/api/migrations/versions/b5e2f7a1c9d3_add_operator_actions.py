"""add operator_actions: the audit and idempotency log for operator resends

See api/models/operator_action.py. One row per operator action; the unique
idempotency key makes a repeated request a replay, and the partial unique
index allows one in-flight action per target.

Also indexes credentials (org_id, issued_at): the operator org list reads each
org's last activity as max(issued_at) per org, and the deliveries list filters
by org and date range.

Revision ID: b5e2f7a1c9d3
Revises: a7d3e91c0b54
Create Date: 2026-11-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b5e2f7a1c9d3"
down_revision: Union[str, Sequence[str], None] = "a7d3e91c0b54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "operator_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("action", sa.String(50), nullable=False),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(100), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("finished_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "uq_operator_actions_in_flight",
        "operator_actions",
        ["action", "target"],
        unique=True,
        postgresql_where=sa.text("status = 'started'"),
    )
    op.create_index("ix_operator_actions_target", "operator_actions", ["target"])
    op.create_index("idx_credentials_org_issued", "credentials", ["org_id", "issued_at"])


def downgrade() -> None:
    op.drop_index("idx_credentials_org_issued", table_name="credentials")
    op.drop_index("ix_operator_actions_target", table_name="operator_actions")
    op.drop_index("uq_operator_actions_in_flight", table_name="operator_actions")
    op.drop_table("operator_actions")
