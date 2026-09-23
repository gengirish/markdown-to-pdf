"""Every change to an organization's credential quota override, append-only.

The question this table exists to answer is the one asked six months later:
"why does acme get 5,000?". So a row carries a required reason and who made
the change, and stores the limit that was in force before and after as well
as the override itself — a tier's default can change later, and the history
has to read correctly when it does.

Written only by `services/plans.py`, in the same transaction as the change it
describes: a rolled-back change leaves no row, a committed one always has one.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from api.models import Base


class CredentialQuotaChange(Base):
    __tablename__ = "credential_quota_changes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: NULL = no override. -1 = an unlimited override. Same encoding as
    #: `organizations.credential_quota_override`.
    previous_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    #: `effective_credential_quota()` either side of the change. -1 = unlimited.
    effective_before: Mapped[int] = mapped_column(Integer, nullable=False)
    effective_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    #: An operator's verified Clerk user id (`user_…`), or a system actor such
    #: as `razorpay-webhook`. Free text because the webhook is not a user, and
    #: a plan change that clears an override has to be in this log too.
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return (
            f"<CredentialQuotaChange org_id={self.org_id!r} "
            f"{self.previous_override!r}->{self.new_override!r} by {self.actor!r}>"
        )
