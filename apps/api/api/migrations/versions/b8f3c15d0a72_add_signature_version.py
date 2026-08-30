"""record which rule signed each credential

`credentials.hmac_signature` was written by two code paths and read by none,
and both signed the public_id alone — so the column asserted integrity it did
not have. api/core/credential_signature.py now signs the fields a credential
actually claims, and every public read path verifies before it renders.

This column is how a verifier tells the two apart without guessing. Existing
rows stay NULL rather than being re-signed: their signature can only be
recomputed from what the row says today, so a backfill would manufacture the
evidence it claims to check. NULL is reported as `unverified`, the same
posture `delivery_status = "unknown"` takes for rows that predate delivery
state.

Revision ID: b8f3c15d0a72
Revises: f7b04c2e91da
Create Date: 2026-08-30

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b8f3c15d0a72"
down_revision: Union[str, Sequence[str], None] = "f7b04c2e91da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable with no server_default on purpose: a default would stamp every
    # pre-existing row with a version whose rule never signed it, and every one
    # of them would then verify as tampered.
    op.add_column(
        "credentials", sa.Column("signature_version", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("credentials", "signature_version")
