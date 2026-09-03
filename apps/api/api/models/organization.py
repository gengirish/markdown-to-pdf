"""Organization and OrgMember models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Boolean, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models import Base


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # The Clerk organization this mirrors. Nullable because orgs created through
    # the API before Clerk sync existed have no counterpart, and because the
    # column has to be addable to a populated table. Unique so two CertForge
    # orgs can never claim the same Clerk org.
    #
    # Slug is NOT a safe join key: Clerk generates slugs like
    # "certforge-1787635500301081932" and lets them be renamed at any time, so
    # matching on it would silently desync on the first rename.
    clerk_org_id: Mapped[str | None] = mapped_column(
        String(255), unique=True, nullable=True, index=True
    )
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: An external URL the org points at. Correct for the viewer page and for
    #: an Open Badges consumer, both of which fetch it themselves — and useless
    #: in a PDF, because the renderer refuses to fetch anything. Uploading is
    #: what puts a logo on a certificate; see `logo_asset_id`.
    logo_url: Mapped[str | None] = mapped_column(String, nullable=True)
    #: An uploaded logo, in the same store as traced-template artwork, so it can
    #: reach a render as a data URI. RESTRICT: a credential re-renders its PDF
    #: on demand, so the image an issued certificate draws must not be
    #: deletable out from under it. Wins over `logo_url` everywhere both apply.
    #:
    #: `use_alter` with an explicit name because this closes a cycle:
    #: template_assets.org_id points back at this table. Without it the
    #: metadata cannot be ordered for CREATE or DROP and the test database
    #: cannot be torn down. The name matches the migration's constraint.
    logo_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "template_assets.id",
            ondelete="RESTRICT",
            use_alter=True,
            name="fk_organizations_logo_asset",
        ),
        nullable=True,
    )
    # Credential PDF branding. Nullable so an org that never set these falls
    # back to CertForge's own defaults — see services/rendering.py.
    primary_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    accent_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    footer_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    tier: Mapped[str] = mapped_column(String(50), nullable=False, default="community")
    razorpay_sub_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    monthly_quota: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    members: Mapped[list["OrgMember"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    credentials: Mapped[list] = relationship(
        "Credential", back_populates="organization", cascade="all, delete-orphan"
    )
    template_assets: Mapped[list] = relationship(
        "TemplateAsset",
        back_populates="organization",
        cascade="all, delete-orphan",
        # Two paths lead from Organization to TemplateAsset now — this one, and
        # organizations.logo_asset_id pointing the other way. Without naming the
        # join, SQLAlchemy cannot tell which foreign key this collection means.
        foreign_keys="TemplateAsset.org_id",
    )
    logo_asset: Mapped["TemplateAsset"] = relationship(  # noqa: F821
        "TemplateAsset", foreign_keys=[logo_asset_id]
    )
    templates: Mapped[list] = relationship(
        "Template", back_populates="organization", cascade="all, delete-orphan"
    )
    batches: Mapped[list] = relationship(
        "CredentialBatch", back_populates="organization", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Organization slug={self.slug!r} tier={self.tier!r}>"


class OrgMember(Base):
    __tablename__ = "org_members"
    __table_args__ = (
        UniqueConstraint("org_id", "clerk_user_id", name="uq_org_member"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    clerk_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False)  # owner, admin, issuer
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="members")

    def __repr__(self) -> str:
        return f"<OrgMember org_id={self.org_id!r} role={self.role!r}>"
