"""Dodo Payments: the governing subscription on each org, and a webhook log

Adds the columns that tie an organization to the one Dodo subscription allowed
to move its tier, and `billing_events`, the replay guard and audit trail for
webhook deliveries. See docs/dodo-payments-integration-plan.md, D1.

No backfill. Every existing org either is on Community or was moved by hand,
and NULL in `dodo_subscription_id` is exactly what keeps a webhook from ever
touching a hand-set tier. Writing anything there would invent a subscription.

`razorpay_sub_id` is deliberately NOT dropped here. That is gated on checking
production holds no value in it (step D0), and a migration cannot check.

Revision ID: e3a7c5d9b041
Revises: d9e4b7a2c615
Create Date: 2026-09-22

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e3a7c5d9b041"
down_revision: Union[str, Sequence[str], None] = "d9e4b7a2c615"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("dodo_customer_id", sa.String(length=100), nullable=True))
    op.add_column("organizations", sa.Column("dodo_subscription_id", sa.String(length=100), nullable=True))
    op.add_column("organizations", sa.Column("subscription_status", sa.String(length=30), nullable=True))
    op.add_column(
        "organizations",
        sa.Column("current_period_end", postgresql.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("cancel_at_period_end", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_organizations_dodo_subscription_id", "organizations", ["dodo_subscription_id"]
    )

    op.create_table(
        "billing_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("webhook_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("subscription_id", sa.String(length=100), nullable=True),
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("outcome", sa.String(length=50), nullable=False),
        sa.Column("received_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("webhook_id"),
    )


def downgrade() -> None:
    op.drop_table("billing_events")
    op.drop_index("ix_organizations_dodo_subscription_id", table_name="organizations")
    op.drop_column("organizations", "cancel_at_period_end")
    op.drop_column("organizations", "current_period_end")
    op.drop_column("organizations", "subscription_status")
    op.drop_column("organizations", "dodo_subscription_id")
    op.drop_column("organizations", "dodo_customer_id")
