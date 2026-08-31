"""count the vision calls that read an uploaded design

Each call to the model that proposes a certificate layout costs real money, and
billing is still mocked, so tier gating cannot bound it — anyone able to create
an organization could otherwise run one in a loop.

Counted on usage_ledger, which is already per org per month, but in its own
column: a vision import is not a credential, and metering it against the
certificate allowance would make consume_quota's meaning depend on which route
called it.

Nullable with no backfill. A row written before this column existed did not
count imports, and writing 0 would assert that it counted zero of them.

Revision ID: d5c8b21e4a09
Revises: c1e7a4b93f28
Create Date: 2026-08-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d5c8b21e4a09"
down_revision: Union[str, Sequence[str], None] = "c1e7a4b93f28"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "usage_ledger", sa.Column("vision_imports", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("usage_ledger", "vision_imports")
