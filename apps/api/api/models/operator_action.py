"""What an operator did that was not a quota or plan change, append-only.

Today that is one thing: resending a credential email from the operator
console. A resend mails a third party, so it needs the same answer as a quota
change six months later — who did it, to what, and what happened — and it
needs to be idempotent, because a double-click must not mail someone twice.

Two constraints carry that:

- `idempotency_key` is unique. The console sends one key per confirmation; a
  second request with the same key finds this row and is answered from it
  instead of sending again.
- A partial unique index on `(action, target)` while `status = 'started'`
  means one in-flight resend per credential, whatever key the second request
  carries. Two operators clicking at once cannot both send.

Quota and plan changes stay in `credential_quota_changes`; this table does not
replace it.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from api.models import Base

STARTED = "started"
SUCCEEDED = "succeeded"   # the action ran; `result` says what came of it
REFUSED = "refused"       # the action was not allowed; `error` says why
FAILED = "failed"         # the action raised; `error` says what


class OperatorAction(Base):
    __tablename__ = "operator_actions"
    __table_args__ = (
        Index(
            "uq_operator_actions_in_flight",
            "action",
            "target",
            unique=True,
            postgresql_where=text("status = 'started'"),
            sqlite_where=text("status = 'started'"),
        ),
        Index("ix_operator_actions_target", "target"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    #: A verified Clerk user id from `require_operator`.
    actor: Mapped[str] = mapped_column(String(100), nullable=False)
    #: "resend_credential_email". Free text so a new action needs no migration.
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: What it was done to: a credential public id for a resend.
    target: Mapped[str] = mapped_column(String(100), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=STARTED)
    #: The response the action produced, replayed verbatim for a repeated key.
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<OperatorAction {self.action} {self.target} by {self.actor} {self.status}>"
