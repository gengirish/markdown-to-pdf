"""rename Starter rows to Pro, the plan that replaced it

The catalog went from four plans to two: Community at 50 a month, Pro at
1,000, and Scale still real but hand-sold (`listed: False`).

Almost nothing needs migrating, because `effective_credential_quota()` reads
the tier's quota live — the two migrations in a row that 50 -> 500 -> 50 needed
are exactly what that change removed. What is left is the `tier` column itself,
which is free text and is what an operator reads.

Only Starter is renamed. `TIER_ALIASES` already makes `starter` resolve to
`pro` everywhere, so this is tidying rather than repair, and it is restricted
to rows that still carry Starter's old default quota on the same rule as
b2d9f4e610ac: a number set by hand was set on purpose.

Two things it deliberately does not do:

* **It does not touch Growth rows.** Growth resolves to Pro through the alias,
  but Growth's quota was 2,000 and Pro's is 1,000, so renaming the row would
  quietly halve a live organization's allowance inside a deploy. There are no
  external paying orgs today; if one ever holds Growth, that reduction is a
  conversation.
* **It does not clear a credential override.** `change_tier()` clears one
  because a real plan change invalidates it. This is not a plan change — the
  org keeps the plan it bought, under the name that plan is sold as now — so
  an operator's override must survive it.

Revision ID: f4b28e0c71da
Revises: e3a7c5d9b041
Create Date: 2026-09-22

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f4b28e0c71da"
down_revision: Union[str, Sequence[str], None] = "e3a7c5d9b041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # monthly_quota is written alongside, not read: nothing enforces on it any
    # more, but it is kept equal to the effective limit so a rollback finds a
    # current number (W4 of the operator quota plan drops the column).
    op.execute(
        "UPDATE organizations SET tier = 'pro', monthly_quota = 1000 "
        "WHERE tier = 'starter' AND monthly_quota = 500"
    )


def downgrade() -> None:
    # Only rows still on Pro's exact default go back, so an org that bought Pro
    # after this ran and had its quota adjusted stays where it is. Same
    # asymmetry b2d9f4e610ac documented: neither direction can tell a row this
    # migration moved from one that always looked that way.
    op.execute(
        "UPDATE organizations SET tier = 'starter', monthly_quota = 500 "
        "WHERE tier = 'pro' AND monthly_quota = 1000"
    )
