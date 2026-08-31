"""Usage ledger for monthly credential quota tracking."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models import Base


class UsageLedger(Base):
    """Tracks monthly credential issuance counts per organization.

    Composite primary key (org_id, period) — one row per org per month.
    period format: YYYY-MM (e.g., "2026-08")
    """

    __tablename__ = "usage_ledger"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    period: Mapped[str] = mapped_column(
        String(7), primary_key=True
    )  # YYYY-MM
    credentials_issued: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    #: Calls to the vision model that reads an uploaded certificate design.
    #: Counted apart from credentials because they are a different unit with a
    #: different cost — each one is a paid API call, and charging it against a
    #: certificate allowance would make the two meters disagree about what a
    #: quota is. NULL on rows written before this column existed; treated as 0.
    vision_imports: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=0
    )

    # Relationships
    organization: Mapped["Organization"] = relationship()

    @staticmethod
    def current_period() -> str:
        """Return the current month period string (YYYY-MM)."""
        return datetime.now(timezone.utc).strftime("%Y-%m")

    def __repr__(self) -> str:
        return f"<UsageLedger org_id={self.org_id!r} period={self.period!r} issued={self.credentials_issued}>"
