"""One row per Dodo Payments webhook delivery we have accepted."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from api.models import Base


class BillingEvent(Base):
    """The replay guard and the audit trail for billing webhooks.

    `webhook_id` is UNIQUE, and the row is inserted in the same transaction
    that applies the event. That pairing is the whole idempotency story: a
    retry of an applied event finds the row and does nothing; a delivery whose
    handler failed rolls its row back with its changes, so the retry can apply
    it. Committing the row first would drop that event forever.

    `outcome` records what the handler *decided*, including every decision to
    do nothing. "Why didn't my upgrade apply?" has to be answerable from the
    database after the logs have rolled off — the same reason
    `credentials.delivery_status` records `not_requested` rather than leaving
    a blank.
    """

    __tablename__ = "billing_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    webhook_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    subscription_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    #: No foreign key: an event for an org we cannot resolve, or one deleted
    #: since, is still worth keeping, and a cascade would erase billing history.
    org_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    #: `applied`, or one of the `ignored_*` reasons in services/billing.py.
    outcome: Mapped[str] = mapped_column(String(50), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<BillingEvent {self.event_type} {self.webhook_id} {self.outcome}>"
