from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Identity,
    Integer,
    Index,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ENUM, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Report(Base):
    __tablename__ = "report"
    __table_args__ = (
        CheckConstraint(
            "(listing_id IS NOT NULL AND target_user_id IS NULL "
            "AND lead_id IS NULL) OR "
            "(listing_id IS NULL AND target_user_id IS NOT NULL "
            "AND lead_id IS NULL) OR "
            "(listing_id IS NULL AND target_user_id IS NULL "
            "AND lead_id IS NOT NULL)",
            name="report_target_check",
        ),
        Index(
            "report_one_active_lead_dispute_idx",
            "lead_id",
            unique=True,
            postgresql_where=text(
                "lead_id IS NOT NULL AND status IN ('open', 'under_review')",
            ),
            sqlite_where=text(
                "lead_id IS NOT NULL AND status IN ('open', 'under_review')",
            ),
        ),
    )

    report_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        Identity(always=True),
        primary_key=True,
    )
    listing_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("listings.listing_id", name="report_listing_id_fkey"),
    )
    target_user_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", name="report_target_user_id_fkey"),
    )
    lead_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("leads.lead_id", name="report_lead_id_fkey"),
    )
    tenant_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.user_id", name="report_tenant_id_fkey"),
        nullable=False,
    )
    admin_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.user_id",
            name="report_admin_id_fkey",
            ondelete="SET NULL",
        ),
    )
    reason: Mapped[str] = mapped_column(
        ENUM(
            "scam",
            "fake_listing",
            "inaccurate_info",
            "abusive",
            "misleading_price",
            "incorrect_availability",
            "unauthorized_property",
            "harassment",
            "fake_account",
            "other",
            name="report_reason_enum",
            create_type=False,
        ),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        ENUM(
            "open",
            "under_review",
            "resolved",
            "dismissed",
            name="report_status_enum",
            create_type=False,
        ),
        nullable=False,
        server_default="open",
    )
    details: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ReportHistory(Base):
    __tablename__ = "report_history"

    history_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        Identity(always=True),
        primary_key=True,
    )
    report_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "report.report_id",
            name="report_history_report_id_fkey",
            ondelete="CASCADE",
        ),
        nullable=False,
    )
    actor_user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey(
            "users.user_id",
            name="report_history_actor_user_id_fkey",
        ),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(
        ENUM(
            "submitted",
            "assigned",
            "resolved",
            "dismissed",
            "note_added",
            name="report_action_enum",
            create_type=False,
        ),
        nullable=False,
    )
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
