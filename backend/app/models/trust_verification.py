from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TrustVerificationRequest(Base):
    __tablename__ = "trust_verification_requests"
    __table_args__ = (
        CheckConstraint(
            "(verification_type = 'identity' AND listing_id IS NULL) OR "
            "(verification_type = 'property_authorization' AND listing_id IS NOT NULL)",
            name="trust_verification_subject_check",
        ),
        CheckConstraint(
            "verification_type IN ('identity', 'property_authorization')",
            name="trust_verification_type_check",
        ),
        CheckConstraint(
            "status IN ('pending', 'needs_information', 'approved', 'rejected')",
            name="trust_verification_status_check",
        ),
        Index(
            "ix_trust_verification_user_submitted",
            "user_id",
            "submitted_at",
        ),
        Index(
            "ix_trust_verification_status_submitted",
            "status",
            "submitted_at",
        ),
        Index(
            "ix_trust_verification_listing_submitted",
            "listing_id",
            "submitted_at",
        ),
        Index(
            "uq_trust_verification_active_profile",
            "user_id",
            "verification_type",
            unique=True,
            postgresql_where=text(
                "listing_id IS NULL AND status IN "
                "('pending', 'needs_information')",
            ),
            sqlite_where=text(
                "listing_id IS NULL AND status IN "
                "('pending', 'needs_information')",
            ),
        ),
        Index(
            "uq_trust_verification_active_listing",
            "user_id",
            "verification_type",
            "listing_id",
            unique=True,
            postgresql_where=text(
                "listing_id IS NOT NULL AND status IN "
                "('pending', 'needs_information')",
            ),
            sqlite_where=text(
                "listing_id IS NOT NULL AND status IN "
                "('pending', 'needs_information')",
            ),
        ),
    )

    request_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", name="trust_verification_user_id_fkey"),
        nullable=False,
    )
    listing_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "listings.listing_id",
            name="trust_verification_listing_id_fkey",
            ondelete="CASCADE",
        ),
    )
    verification_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="pending",
    )
    evidence_statement: Mapped[str] = mapped_column(Text, nullable=False)
    decision_reason: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class TrustVerificationHistory(Base):
    __tablename__ = "trust_verification_history"
    __table_args__ = (
        CheckConstraint(
            "action IN ('submitted', 'resubmitted', 'approved', "
            "'rejected', 'information_requested')",
            name="trust_verification_history_action_check",
        ),
        Index(
            "ix_trust_verification_history_request",
            "request_id",
            "created_at",
        ),
        Index(
            "ix_trust_verification_history_action_created",
            "action",
            "created_at",
        ),
    )

    history_id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    request_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "trust_verification_requests.request_id",
            name="trust_verification_history_request_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    actor_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.user_id",
            name="trust_verification_history_actor_user_id_fkey",
        ),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
