"""The provider's send limit, remembered.

One row per email provider, written when the provider refuses a send for
volume and read before every CertForge send. While `paused_until` is in the
future no send reaches the provider: the row is deferred instead, at no cost.

It is a table rather than a module global because a global does not survive
the machine stopping, and a second machine would not see it. The idempotency
cache learned the first half of that already.

See api/services/send_gate.py, the only reader and writer.
"""

from datetime import datetime, timezone

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from api.models import Base


class EmailSendPause(Base):
    __tablename__ = "email_send_pauses"

    provider: Mapped[str] = mapped_column(String(50), primary_key=True)
    paused_until: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    # The provider's own words, for whoever asks why nothing is sending.
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<EmailSendPause {self.provider} until {self.paused_until}>"
