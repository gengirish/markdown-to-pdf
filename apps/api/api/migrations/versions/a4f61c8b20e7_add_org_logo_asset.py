"""an organization's logo, as stored bytes rather than a URL

organizations.logo_url has always been an external URL. That works for the
viewer page and for an Open Badges consumer — both fetch it themselves — and it
can never work in a PDF: _pdf_link_callback refuses every http(s) URI on
purpose, so `<img src="{{logo_url}}">` in a guided template rendered as nothing,
silently, for every org that ticked the box.

logo_asset_id points at the same template_assets table the traced backgrounds
use, so the bytes are in object storage and reach the renderer as a data URI.
RESTRICT, matching templates.background_asset_id: a credential re-renders its
PDF on demand, so deleting the image an issued certificate draws would break it
after the fact.

logo_url is deliberately NOT dropped and NOT backfilled. It is still the right
thing for an org that would rather point at its own CDN, the viewer still uses
it, and there is nothing to migrate — the bytes behind those URLs are not ours
to fetch and store.

Revision ID: a4f61c8b20e7
Revises: d5c8b21e4a09
Create Date: 2026-09-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a4f61c8b20e7"
down_revision: Union[str, Sequence[str], None] = "d5c8b21e4a09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("logo_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_organizations_logo_asset",
        "organizations",
        "template_assets",
        ["logo_asset_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_organizations_logo_asset", "organizations", type_="foreignkey"
    )
    op.drop_column("organizations", "logo_asset_id")
