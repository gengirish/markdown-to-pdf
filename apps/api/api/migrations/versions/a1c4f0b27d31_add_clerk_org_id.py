"""add organizations.clerk_org_id

Links a CertForge organization to the Clerk organization it mirrors.

Until now nothing recorded that relationship: routes/orgs.py asked callers for
`clerk_org_id` in its request body and then dropped the value on the floor. That
left slug as the only possible join key, which Clerk lets users rename, so any
webhook sync built on it would desync on the first rename.

Nullable and unique: existing rows predate Clerk sync and keep a NULL, while no
two organizations may ever claim the same Clerk org.

Revision ID: a1c4f0b27d31
Revises: 9b6189514dd3
Create Date: 2026-08-25

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1c4f0b27d31"
down_revision: Union[str, Sequence[str], None] = "9b6189514dd3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("clerk_org_id", sa.String(length=255), nullable=True),
    )
    op.create_index(
        "ix_organizations_clerk_org_id", "organizations", ["clerk_org_id"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_organizations_clerk_org_id", table_name="organizations")
    op.drop_column("organizations", "clerk_org_id")
