from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('NEW', 'CONTACTED', 'VIEWING_SCHEDULED', "
            "'VIEWING_COMPLETED', 'INTERESTED', 'RENTED', "
            "'UNSUCCESSFUL')",
            name="leads_stage_check",
        ),
        CheckConstraint(
            "dispute_status IN ('none', 'open', 'resolved', 'dismissed')",
            name="leads_dispute_status_check",
        ),
        CheckConstraint(
            "dispute_status != 'open' OR billing_eligible = false",
            name="leads_open_dispute_not_billable_check",
        ),
        UniqueConstraint(
            "contact_request_id",
            name="leads_contact_request_id_key",
        ),
        Index(
            "leads_landlord_created_idx",
            "landlord_id",
            "created_at",
            "lead_id",
        ),
        Index(
            "leads_tenant_created_idx",
            "tenant_id",
            "created_at",
            "lead_id",
        ),
        Index(
            "leads_stage_updated_idx",
            "stage",
            "updated_at",
            "lead_id",
        ),
    )

    lead_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        Identity(always=True),
        primary_key=True,
    )
    contact_request_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "contact_requests.request_id",
            name="leads_contact_request_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", name="leads_tenant_id_fkey"),
        nullable=False,
    )
    landlord_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", name="leads_landlord_id_fkey"),
        nullable=False,
    )
    listing_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("listings.listing_id", name="leads_listing_id_fkey"),
        nullable=False,
    )
    stage: Mapped[str] = mapped_column(
        String(24),
        nullable=False,
        server_default="NEW",
    )
    dispute_status: Mapped[str] = mapped_column(
        String(16),
        nullable=False,
        default="none",
        server_default="none",
    )
    rented_at: Mapped[datetime | None] = mapped_column(DateTime)
    unsuccessful_reason: Mapped[str | None] = mapped_column(Text)
    billing_eligible: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class LeadStageHistory(Base):
    __tablename__ = "lead_stage_history"
    __table_args__ = (
        CheckConstraint(
            "from_stage IS NULL OR from_stage IN "
            "('NEW', 'CONTACTED', 'VIEWING_SCHEDULED', "
            "'VIEWING_COMPLETED', 'INTERESTED', 'RENTED', "
            "'UNSUCCESSFUL', 'DISPUTED')",
            name="lead_stage_history_from_stage_check",
        ),
        CheckConstraint(
            "to_stage IN ('NEW', 'CONTACTED', 'VIEWING_SCHEDULED', "
            "'VIEWING_COMPLETED', 'INTERESTED', 'RENTED', "
            "'UNSUCCESSFUL', 'DISPUTED')",
            name="lead_stage_history_to_stage_check",
        ),
        Index(
            "lead_stage_history_lead_changed_idx",
            "lead_id",
            "changed_at",
            "history_id",
        ),
    )

    history_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        Identity(always=True),
        primary_key=True,
    )
    lead_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "leads.lead_id",
            name="lead_stage_history_lead_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    from_stage: Mapped[str | None] = mapped_column(String(24))
    to_stage: Mapped[str] = mapped_column(String(24), nullable=False)
    actor_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.user_id",
            name="lead_stage_history_actor_user_id_fkey",
        ),
        nullable=False,
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
    )
    note: Mapped[str | None] = mapped_column(Text)
