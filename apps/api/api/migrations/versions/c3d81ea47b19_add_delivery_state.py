"""add credential delivery state and batch delivery counters

Delivery previously left no trace. A rejected send wrote one logger.warning; a
credential with no recipient_email took a silent `if` and wrote nothing at all.
Minutes later the two were identical rows, and the log had rolled off — which is
exactly how the first production batch ended up unexplainable.

Backfill is `unknown`, never a guess. Rows that predate these columns have no
delivery record, and writing `sent` or `not_requested` for them would invent
evidence: the whole point of this change is that the system stops implying
things it does not know. `unknown` is also excluded from DELIVERY_RETRYABLE, so
no backfilled row can trigger a retry that mails someone who was served months
ago.

New rows default to `not_requested`, so the server default is switched after the
backfill rather than before.

Revision ID: c3d81ea47b19
Revises: a1c4f0b27d31
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c3d81ea47b19"
down_revision: Union[str, Sequence[str], None] = "a1c4f0b27d31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- credentials ---------------------------------------------------------
    # Added with server_default='unknown' so the backfill happens in the same
    # statement as the ADD COLUMN. Postgres 11+ does this without rewriting the
    # table, which matters because this runs in the release command with the
    # API about to serve traffic.
    op.add_column(
        "credentials",
        sa.Column(
            "delivery_status",
            sa.String(length=50),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.add_column(
        "credentials",
        sa.Column("delivered_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column("credentials", sa.Column("delivery_error", sa.Text(), nullable=True))
    op.add_column(
        "credentials",
        sa.Column(
            "delivery_attempts", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    # Existing rows now read 'unknown'. Everything inserted from here on is a
    # row this code wrote, and it means not_requested until told otherwise.
    op.alter_column("credentials", "delivery_status", server_default="not_requested")

    op.create_index(
        "idx_credentials_delivery", "credentials", ["org_id", "delivery_status"]
    )

    # -- credential_batches --------------------------------------------------
    # Zero is honest for historical batches: nothing recorded a delivery, so
    # none is claimed. The counters only ever describe batches this code ran.
    op.add_column(
        "credential_batches",
        sa.Column("delivered", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "credential_batches",
        sa.Column(
            "delivery_failed", sa.Integer(), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("credential_batches", "delivery_failed")
    op.drop_column("credential_batches", "delivered")
    op.drop_index("idx_credentials_delivery", table_name="credentials")
    op.drop_column("credentials", "delivery_attempts")
    op.drop_column("credentials", "delivery_error")
    op.drop_column("credentials", "delivered_at")
    op.drop_column("credentials", "delivery_status")
