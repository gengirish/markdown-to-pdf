"""log every plan change in credential_quota_changes

`change_tier()` used to write a change-log row only when a plan change cleared
an override, so moving an org with no override from Scale to Pro left a log
line and nothing an operator could read back. From here every real plan change
writes a row, with the tier before and after.

Additive and nullable: existing rows are override changes and keep NULL. No
backfill — a plan change that left no row cannot be reconstructed, and a
guessed one would be evidence manufactured after the fact.

Revision ID: a7d3e91c0b54
Revises: f4b28e0c71da
Create Date: 2026-11-08

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a7d3e91c0b54"
down_revision: Union[str, Sequence[str], None] = "f4b28e0c71da"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "credential_quota_changes",
        sa.Column("previous_tier", sa.String(50), nullable=True),
    )
    op.add_column(
        "credential_quota_changes",
        sa.Column("new_tier", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("credential_quota_changes", "new_tier")
    op.drop_column("credential_quota_changes", "previous_tier")
