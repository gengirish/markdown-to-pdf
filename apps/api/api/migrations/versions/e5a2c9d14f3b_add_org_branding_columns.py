"""add organization branding columns

Single-issue credentials never rendered a PDF at all, and bulk-issued ones
rendered the seed templates' hardcoded colors regardless of which org issued
them. These three columns let an org's PDF actually look like theirs;
services/rendering.py falls back to CertForge's own defaults when they are
NULL, so an org that never set them keeps rendering exactly as before.

Revision ID: e5a2c9d14f3b
Revises: c3d81ea47b19
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e5a2c9d14f3b"
down_revision: Union[str, Sequence[str], None] = "c3d81ea47b19"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations", sa.Column("primary_color", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "organizations", sa.Column("accent_color", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "organizations", sa.Column("footer_text", sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("organizations", "footer_text")
    op.drop_column("organizations", "accent_color")
    op.drop_column("organizations", "primary_color")
