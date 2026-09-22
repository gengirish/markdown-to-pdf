"""add credential_quota_override and the credential_quota_changes log

W1 of docs/operator-quota-overrides-plan.md. After this, issuance reads
`effective_credential_quota()` — the override if set, else the tier's quota
read live — instead of the `monthly_quota` copy, so a change to BILLING_TIERS
no longer needs a migration like b2d9f4e610ac and c6a1e85f3d27.

Backfill: an org whose `monthly_quota` differs from its tier's quota was set
deliberately (seed_e2e's 10,000, anything set by hand), so that number becomes
its override. An org that matches gets NULL and follows its tier from here on.

The tier quotas are literals, not imported from config.py: a migration must do
the same thing when it is re-run a year from now, whatever BILLING_TIERS says
then. A tier the table does not know (the old "pro") compares against
Community's 50 — the same fallback `get_tier()` uses — because that is the
limit such a row was being held to.

Each backfilled override also gets a change-log row, so the first question the
log is asked ("why does this org get 10,000?") has an answer rather than an
override that appears from nowhere.

`monthly_quota` stays, and the application keeps it equal to the effective
limit, so rolling this release back leaves the old code reading a current
number. It is dropped in W4.

Revision ID: d9e4b7a2c615
Revises: c6a1e85f3d27
Create Date: 2026-09-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d9e4b7a2c615"
down_revision: Union[str, Sequence[str], None] = "c6a1e85f3d27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# BILLING_TIERS' monthly quotas as of this revision. -1 = unlimited.
_TIER_QUOTA_SQL = """
    CASE tier
        WHEN 'community' THEN 50
        WHEN 'starter' THEN 500
        WHEN 'growth' THEN 2000
        WHEN 'scale' THEN -1
        ELSE 50
    END
"""


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("credential_quota_override", sa.Integer(), nullable=True),
    )
    op.create_table(
        "credential_quota_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("previous_override", sa.Integer(), nullable=True),
        sa.Column("new_override", sa.Integer(), nullable=True),
        sa.Column("effective_before", sa.Integer(), nullable=False),
        sa.Column("effective_after", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_credential_quota_changes_org_id", "credential_quota_changes", ["org_id"]
    )

    op.execute(
        f"UPDATE organizations SET credential_quota_override = monthly_quota "
        f"WHERE monthly_quota <> {_TIER_QUOTA_SQL}"
    )
    op.execute(
        f"""
        INSERT INTO credential_quota_changes
            (id, org_id, previous_override, new_override,
             effective_before, effective_after, reason, actor, created_at)
        SELECT gen_random_uuid(), id, NULL, credential_quota_override,
               credential_quota_override, credential_quota_override,
               'Carried over from monthly_quota, which differed from the '
                   || tier || ' tier''s quota of ' || ({_TIER_QUOTA_SQL})
                   || ' when overrides were introduced',
               'migration:{revision}', now()
        FROM organizations
        WHERE credential_quota_override IS NOT NULL
        """
    )


def downgrade() -> None:
    # monthly_quota has been kept current by the application, so there is
    # nothing to copy back before the override goes.
    op.drop_index("ix_credential_quota_changes_org_id", table_name="credential_quota_changes")
    op.drop_table("credential_quota_changes")
    op.drop_column("organizations", "credential_quota_override")
