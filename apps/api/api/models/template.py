"""Template model for certificate layouts."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, ForeignKey, Text, JSON
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models import Base


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    org_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,  # NULL = global default template
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    #: The only thing issuance reads. Whether it was hand-written or generated
    #: from `config`, this is the template.
    html_source: Mapped[str] = mapped_column(Text, nullable=False)
    #: Placeholders this template uses that issuance does not supply — they come
    #: from a credential's metadata (a CSV column). Recorded so the UI can say
    #: where a value has to come from before rows start rendering blank.
    variables: Mapped[dict] = mapped_column(JSON, nullable=False, default=list)
    #: Guided-form settings, when the template was built that way. NULL means
    #: the HTML is hand-authored and the form must not reopen against it:
    #: regenerating from a stale config would discard the author's edit, and
    #: keeping both would leave two descriptions of one certificate that
    #: quietly disagree.
    config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    #: The uploaded artwork this template is drawn on, when it has one. The
    #: id lives here and NOWHERE else — in particular not in `config`, which
    #: would be two descriptions of one certificate that can disagree. The
    #: generator only needs to know whether a background exists, not which.
    #:
    #: RESTRICT, not CASCADE: deleting the artwork a previously issued
    #: credential renders from would break re-rendering its PDF, which
    #: delete_org_template already refuses to allow for the template itself.
    background_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("template_assets.id", ondelete="RESTRICT"),
        nullable=True,
    )
    #: Exclusive per organization — see routes/templates.py's set-default, which
    #: clears the flag on the org's other templates in the same transaction.
    #: A global template (org_id NULL) uses it for the platform-wide default.
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="templates")

    def __repr__(self) -> str:
        scope = f"org={self.org_id}" if self.org_id else "global"
        return f"<Template name={self.name!r} {scope}>"
