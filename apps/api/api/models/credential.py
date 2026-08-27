"""Credential and CredentialBatch models."""

# ── Credential lifecycle ────────────────────────────────────────────────────
#
# These were four ad-hoc string comparisons scattered across three files, and
# they disagreed. The viewer allowed only "issued" (a whitelist) while
# badge.json, claiming and passport listing allowed anything but "revoked" (a
# blacklist). Two consequences, both hit independently during Wave 1:
#
#   - a credential could not be marked "claimed" at all, because doing so
#     would have made an already-printed QR code stop verifying
#   - a "pending" credential — a bulk row the worker has not finished — was
#     invisible in the viewer yet still exported a public Open Badge
#
# Defining the states in one place means adding a fifth forces a decision about
# what every surface does with it, instead of four files quietly disagreeing.

PENDING = "pending"    # row exists; the worker has not produced it yet
ISSUED = "issued"      # live and publicly verifiable
CLAIMED = "claimed"    # a recipient attached it to their passport — still live
REVOKED = "revoked"    # withdrawn; never becomes valid again

#: Anything a stranger holding the URL may see. Claiming must not remove a
#: credential from public view — the QR code on the certificate is permanent.
PUBLICLY_VERIFIABLE = frozenset({ISSUED, CLAIMED})

#: A recipient may claim a credential that is live, and claiming twice is a
#: no-op rather than an error.
CLAIMABLE = frozenset({ISSUED, CLAIMED})

#: Terminal. Nothing transitions out of REVOKED.
TERMINAL = frozenset({REVOKED})


# -- Email delivery -----------------------------------------------------------
#
# Delivery used to leave no trace at all. A send that failed wrote one
# logger.warning and nothing else; a credential with no recipient_email took a
# silent `if` and wrote nothing whatsoever. Ten minutes later the two were
# indistinguishable in the database, and the log had rolled off. That is exactly
# how the first production batch ended: no email arrived, AgentMail was healthy,
# and nothing on the system could say which of the two had happened.
#
# NOT_REQUESTED is the state that earns its keep. Separating "we never tried"
# from "we tried and it failed" is the whole difference between an answerable
# support question and an unanswerable one.

NOT_REQUESTED = "not_requested"  # no address, or the caller did not ask
DELIVERY_PENDING = "pending"     # queued or in flight
SENT = "sent"                    # AgentMail accepted it
DELIVERY_FAILED = "failed"       # rejected; delivery_error says why
DELIVERY_UNKNOWN = "unknown"     # predates this column; never guess for these

#: Worth retrying. UNKNOWN is excluded deliberately — those rows predate any
#: delivery record, so a retry would mail people who may already have received
#: their credential months ago.
DELIVERY_RETRYABLE = frozenset({DELIVERY_FAILED})

#: Counted as delivered when a batch reports itself.
DELIVERY_SUCCEEDED = frozenset({SENT})


import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Text, ForeignKey, Index, JSON
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
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
    # succeeded/failed count RENDERS, not sends. A batch reporting "30 succeeded"
    # was read as "30 people got their credential", which it never meant — the
    # email could have failed for every one of them and these numbers would not
    # move. Delivery is counted separately so the batch can say "30 issued, 28
    # delivered, 2 failed" instead of implying all 30 landed.
    succeeded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivered: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivery_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending"
    )  # pending, processing, completed, failed
    error_report: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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
        # "show me this org's failed deliveries" is the query support runs.
        Index("idx_credentials_delivery", "org_id", "delivery_status"),
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
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
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

    # Delivery is tracked apart from `status` because the two answer different
    # questions: status is whether the credential exists, delivery is whether
    # its recipient was told. A credential is legitimately issued-and-undelivered
    # (no address given), and conflating them is what made the first production
    # batch unexplainable.
    delivery_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default=NOT_REQUESTED
    )  # not_requested, pending, sent, failed, unknown
    delivered_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # The provider's own words, kept verbatim. A support answer needs "AgentMail
    # rejected the request (403)", not a boolean.
    delivery_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivery_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="credentials")
    batch: Mapped["CredentialBatch | None"] = relationship(back_populates="credentials")
    passport_links: Mapped[list["PassportCredential"]] = relationship(
        back_populates="credential", cascade="all, delete-orphan"
    )

    @property
    def is_revoked(self) -> bool:
        return self.status == REVOKED

    @property
    def is_publicly_verifiable(self) -> bool:
        """May a stranger holding the URL see this credential?"""
        return self.status in PUBLICLY_VERIFIABLE

    @property
    def is_claimable(self) -> bool:
        return self.status in CLAIMABLE

    def __repr__(self) -> str:
        return f"<Credential public_id={self.public_id!r} status={self.status!r}>"
