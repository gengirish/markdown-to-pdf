"""Uploaded template artwork — the image a certificate is drawn on.

A template's HTML can never carry its own background. `MAX_HTML_BYTES` is
256 KB and a 150 dpi A4-landscape design is ~940 KB as a data URI, so the
image lives here and arrives at render time through the `{{background}}`
placeholder. See api/services/backgrounds.py.

The bytes in object storage are **not** the bytes that were uploaded. Every
upload is re-encoded by Pillow before it is stored (routes/templates.py), which
is what lets the dashboard render one in an `<img>` and what stops an appended
polyglot payload from reaching a PDF we hand to third parties. `checksum` and
`byte_size` therefore describe the stored image, never the upload.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models import Base


class TemplateAsset(Base):
    __tablename__ = "template_assets"
    __table_args__ = (
        # A double-clicked upload, or the same file uploaded twice, is one
        # asset. Scoped to the org: two customers uploading the same stock
        # certificate must not share a row, or deleting one org's asset would
        # break the other's template.
        UniqueConstraint("org_id", "checksum", name="uq_template_asset_checksum"),
        Index("idx_template_assets_org", "org_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: NOT NULL, unlike Template.org_id. A template can be global — the
    #: platform ships three — but a customer's artwork is never platform-wide.
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Key in the object store. Never a URL: nothing outside core/storage.py
    #: should know where the bucket is.
    storage_key: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    #: Always image/jpeg today, because the upload path re-encodes to JPEG.
    #: Stored rather than assumed so a second stored format later does not
    #: mean guessing at the media type of every existing row.
    mime: Mapped[str] = mapped_column(String(32), nullable=False)
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    byte_size: Mapped[int] = mapped_column(Integer, nullable=False)
    #: sha256 of the stored bytes. The render cache keys on this rather than on
    #: `id`, so an id whose bytes changed can never serve a stale image.
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    #: An API key has no person behind it, so record the key. Same rule as
    #: CredentialBatch.created_by.
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    organization: Mapped["Organization"] = relationship(  # noqa: F821
        back_populates="template_assets",
        # Disambiguates against organizations.logo_asset_id, which points back
        # at this table from the other side.
        foreign_keys=[org_id],
    )

    def __repr__(self) -> str:
        return (
            f"<TemplateAsset id={self.id!r} org={self.org_id!r} "
            f"{self.width_px}x{self.height_px} {self.byte_size}B>"
        )
