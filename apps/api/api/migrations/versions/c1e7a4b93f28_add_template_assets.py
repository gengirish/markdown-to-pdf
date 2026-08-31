"""template artwork: an image a certificate is drawn on

A template's HTML cannot carry its own background — MAX_HTML_BYTES is 256 KB
and a 150 dpi A4-landscape design is ~940 KB as a data URI. The image is stored
in object storage, described by a row here, and reaches the renderer through the
{{background}} placeholder at render time.

templates.background_asset_id is RESTRICT rather than CASCADE on purpose:
deleting the artwork a previously issued credential renders from would break
re-rendering its PDF. No backfill — every existing template genuinely has no
background, and NULL is the true value rather than a guess.

Revision ID: c1e7a4b93f28
Revises: b8f3c15d0a72
Create Date: 2026-08-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c1e7a4b93f28"
down_revision: Union[str, Sequence[str], None] = "b8f3c15d0a72"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "template_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        # NOT NULL, unlike templates.org_id: a template can be global, a
        # customer's artwork never is.
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("mime", sa.String(length=32), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=False),
        sa.Column("height_px", sa.Integer(), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("storage_key"),
        # The same file uploaded twice is one asset, scoped per org.
        sa.UniqueConstraint("org_id", "checksum", name="uq_template_asset_checksum"),
    )
    op.create_index("idx_template_assets_org", "template_assets", ["org_id"])

    op.add_column(
        "templates",
        sa.Column("background_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_templates_background_asset",
        "templates",
        "template_assets",
        ["background_asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("fk_templates_background_asset", "templates", type_="foreignkey")
    op.drop_column("templates", "background_asset_id")
    op.drop_index("idx_template_assets_org", table_name="template_assets")
    op.drop_table("template_assets")
