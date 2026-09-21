"""put the Community tier's monthly quota back to 50

b2d9f4e610ac raised it to 500 and has already run in production, so this is a
forward migration rather than a revert. Deleting that file would leave
alembic_version naming a revision that no longer exists, and the next
release_command would fail to locate it.

The scope mirrors b2d9f4e610ac: tier = 'community' AND monthly_quota = 500.
That also catches Community orgs created while the 500 default was live —
which is the point, they were given it by the default and not by anyone.

An org that already issued more than 50 this period is not broken by this:
consume_quota() refuses its next issuance with a 402 and reports 0 remaining.
Nothing it already issued is affected.

Revision ID: c6a1e85f3d27
Revises: b2d9f4e610ac
Create Date: 2026-09-21

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c6a1e85f3d27"
down_revision: Union[str, Sequence[str], None] = "b2d9f4e610ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE organizations SET monthly_quota = 50 "
        "WHERE tier = 'community' AND monthly_quota = 500"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE organizations SET monthly_quota = 500 "
        "WHERE tier = 'community' AND monthly_quota = 50"
    )
