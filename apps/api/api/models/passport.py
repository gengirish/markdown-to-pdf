"""Passport and PassportCredential models."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import String, Integer, Boolean, Text, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.models import Base


class Passport(Base):
    __tablename__ = "passports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    clerk_user_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    # Relationships
    credential_links: Mapped[list["PassportCredential"]] = relationship(
        back_populates="passport", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Passport username={self.username!r}>"


class PassportCredential(Base):
    __tablename__ = "passport_credentials"

    passport_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("passports.id", ondelete="CASCADE"),
        primary_key=True,
    )
    credential_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credentials.id", ondelete="CASCADE"),
        primary_key=True,
    )
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pinned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    passport: Mapped["Passport"] = relationship(back_populates="credential_links")
    credential: Mapped["Credential"] = relationship(back_populates="passport_links")
