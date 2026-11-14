"""add credentials.delivery_deferred_since

The deferral deadline (MAX_DEFERRAL, 7 days) was measured from `issued_at`.
That is wrong for any row deferred long after it was issued — a resend of a
month-old credential that meets the provider's daily limit failed at once,
with "the send limit persisted for 7 days". It now counts from when the row
entered `deferred`.

Rows already deferred get `delivery_next_attempt_at`'s day as a stand-in; a
deferred row is never more than a day from its next attempt, so that is the
closest thing to the truth the table holds.

Revision ID: e6c3a8d1f27b
Revises: d2b7e9f4a1c3
Create Date: 2026-11-14

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "e6c3a8d1f27b"
down_revision: Union[str, Sequence[str], None] = "d2b7e9f4a1c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "credentials",
        sa.Column("delivery_deferred_since", postgresql.TIMESTAMP(timezone=True), nullable=True),
    )
    op.execute(
        "UPDATE credentials "
        "SET delivery_deferred_since = COALESCE(delivery_next_attempt_at, now()) - interval '1 day' "
        "WHERE delivery_status = 'deferred'"
    )


def downgrade() -> None:
    op.drop_column("credentials", "delivery_deferred_since")
