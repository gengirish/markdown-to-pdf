"""Credential and CredentialBatch models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Text, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models import Base


class CredentialBatch(Base):
    __tablename__ = "credential_batches"
    __table_args__ = (
        Index("idx_batches_org_status", "org_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id"), nullable=False
    )
    csv_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )  # pending, processing, completed, failed
    error_report: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="batches")
    credentials: Mapped[list["Credential"]] = relationship(back_populates="batch")
    template: Mapped["Template"] = relationship()

    def __repr__(self) -> str:
        return f"<CredentialBatch id={self.id!r} status={self.status!r} {self.succeeded}/{self.total}>"


class Credential(Base):
    __tablename__ = "credentials"
    __table_args__ = (
        Index("idx_credentials_org", "org_id"),
        Index("idx_credentials_public_id", "public_id"),
        Index("idx_credentials_recipient_email", "recipient_email"),
        Index(
            "idx_credentials_legacy_token", "legacy_token",
            postgresql_where="legacy_token IS NOT NULL",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    public_id: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("credential_batches.id", ondelete="SET NULL"), nullable=True
    )
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("templates.id"), nullable=True
    )
    recipient_name: Mapped[str] = mapped_column(String(255), nullable=False)
    recipient_email: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    pdf_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    hmac_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    legacy_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="issued"
    )  # issued, claimed, revoked
    claimed_by_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    claimed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="credentials")
    batch: Mapped["CredentialBatch | None"] = relationship(back_populates="credentials")
    passport_links: Mapped[list["PassportCredential"]] = relationship(
        back_populates="credential", cascade="all, delete-orphan"
    )

    @property
    def is_revoked(self) -> bool:
        return self.status == "revoked"

    def __repr__(self) -> str:
        return f"<Credential public_id={self.public_id!r} status={self.status!r}>"
