"""raise the Community tier's monthly quota from 50 to 500

BILLING_TIERS is not what binds at issuance time — organizations.monthly_quota
is. consume_quota() reads the column, and orgs.py creates an org with no
explicit quota, so the value is frozen into the row at creation. Raising the
tier table alone would leave every existing Community org on 50 forever.

Only rows that still carry the old default are moved: tier = 'community' AND
monthly_quota = 50. An org whose quota was set by hand to anything else was set
that way on purpose and is left alone.

Revision ID: b2d9f4e610ac
Revises: a4f61c8b20e7
Create Date: 2026-09-20

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2d9f4e610ac"
down_revision: Union[str, Sequence[str], None] = "a4f61c8b20e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE organizations SET monthly_quota = 500 "
        "WHERE tier = 'community' AND monthly_quota = 50"
    )


def downgrade() -> None:
    # The inverse cannot distinguish an org raised by this migration from one
    # deliberately given 500 while on the community tier — there were none at
    # the time it ran, and a downgrade that left orgs above the tier's quota
    # would be the same defect in the other direction.
    op.execute(
        "UPDATE organizations SET monthly_quota = 50 "
        "WHERE tier = 'community' AND monthly_quota = 500"
    )
