"""add deferred credential delivery: credentials.delivery_next_attempt_at, email_send_pauses

A send the provider refuses for volume (AgentMail's daily limit) is now
`deferred` rather than `failed`, costs no delivery attempt, and is released
by a periodic sweep once the limit resets. `email_send_pauses` remembers the
limit so that, after the first refusal, the remaining rows are deferred
without calling the provider at all. See docs/email-daily-cap-plan.md.

Additive only: no existing row changes state. The 2026-11-12 rows that failed
on the limit are moved by `python -m api.repair_rate_limited_deliveries`, run
by a person, not here.

Revision ID: d2b7e9f4a1c3
Revises: c8a1d4e7f2b6
Create Date: 2026-11-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d2b7e9f4a1c3"
down_revision: Union[str, Sequence[str], None] = "c8a1d4e7f2b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "credentials",
        sa.Column("delivery_next_attempt_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "idx_credentials_deferred_due",
        "credentials",
        ["delivery_next_attempt_at"],
        postgresql_where=sa.text("delivery_status = 'deferred'"),
    )
    op.create_table(
        "email_send_pauses",
        sa.Column("provider", sa.String(50), primary_key=True),
        sa.Column("paused_until", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("email_send_pauses")
    op.drop_index("idx_credentials_deferred_due", table_name="credentials")
    op.drop_column("credentials", "delivery_next_attempt_at")
