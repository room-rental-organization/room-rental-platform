from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, aliased

from app.models.lead import Lead, LeadStageHistory
from app.models.listing import Listing
from app.models.report import Report
from app.models.user import User


class LeadRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def ensure_for_contact_request(
        self,
        *,
        contact_request_id: int,
        tenant_id: int,
        landlord_id: int,
        listing_id: int,
        created_at: datetime,
    ) -> Lead:
        existing = self.get_by_contact_request(contact_request_id)
        if existing is not None:
            return existing

        lead = Lead(
            contact_request_id=contact_request_id,
            tenant_id=tenant_id,
            landlord_id=landlord_id,
            listing_id=listing_id,
            stage="NEW",
            created_at=created_at,
            updated_at=created_at,
        )
        try:
            with self._db.begin_nested():
                self._db.add(lead)
                self._db.flush()
                self.add_history(
                    lead_id=lead.lead_id,
                    from_stage=None,
                    to_stage="NEW",
                    actor_user_id=tenant_id,
                    changed_at=created_at,
                )
        except IntegrityError:
            existing = self.get_by_contact_request(contact_request_id)
            if existing is None:
                raise
            return existing
        return lead

    def get_by_contact_request(
        self,
        contact_request_id: int,
    ) -> Lead | None:
        statement = select(Lead).where(
            Lead.contact_request_id == contact_request_id,
        )
        return self._db.scalar(statement)

    def get_for_landlord(
        self,
        lead_id: int,
        landlord_id: int,
        *,
        for_update: bool = False,
    ) -> Lead | None:
        statement = select(Lead).where(
            Lead.lead_id == lead_id,
            Lead.landlord_id == landlord_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self._db.scalar(statement)

    def get_for_tenant(
        self,
        lead_id: int,
        tenant_id: int,
        *,
        for_update: bool = False,
    ) -> Lead | None:
        statement = select(Lead).where(
            Lead.lead_id == lead_id,
            Lead.tenant_id == tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self._db.scalar(statement)

    def get_for_admin(
        self,
        lead_id: int,
        *,
        for_update: bool = False,
    ) -> Lead | None:
        statement = select(Lead).where(Lead.lead_id == lead_id)
        if for_update:
            statement = statement.with_for_update()
        return self._db.scalar(statement)

    def get_for_tenant_with_listing(
        self,
        lead_id: int,
        tenant_id: int,
    ) -> tuple[Lead, str, str] | None:
        statement = (
            select(Lead, Listing.title, Listing.address)
            .join(Listing, Listing.listing_id == Lead.listing_id)
            .where(Lead.lead_id == lead_id, Lead.tenant_id == tenant_id)
        )
        row = self._db.execute(statement).one_or_none()
        if row is None:
            return None
        lead, title, address = row
        return lead, title, address

    def list_for_landlord(self, landlord_id: int) -> list[Lead]:
        statement = (
            select(Lead)
            .where(Lead.landlord_id == landlord_id)
            .order_by(Lead.created_at.desc(), Lead.lead_id.desc())
        )
        return list(self._db.scalars(statement).all())

    def list_for_tenant(self, tenant_id: int) -> list[Lead]:
        statement = (
            select(Lead)
            .where(Lead.tenant_id == tenant_id)
            .order_by(Lead.created_at.desc(), Lead.lead_id.desc())
        )
        return list(self._db.scalars(statement).all())

    def list_for_tenant_with_listing(
        self,
        tenant_id: int,
    ) -> list[tuple[Lead, str, str]]:
        statement = (
            select(Lead, Listing.title, Listing.address)
            .join(Listing, Listing.listing_id == Lead.listing_id)
            .where(Lead.tenant_id == tenant_id)
            .order_by(Lead.created_at.desc(), Lead.lead_id.desc())
        )
        return [
            (lead, title, address)
            for lead, title, address in self._db.execute(statement).all()
        ]

    def list_for_admin(self, stage_filter: str | None = None) -> list[Lead]:
        statement = select(Lead)
        if stage_filter is not None:
            statement = statement.where(Lead.stage == stage_filter)
        statement = statement.order_by(
            Lead.updated_at.desc(),
            Lead.lead_id.desc(),
        )
        return list(self._db.scalars(statement).all())

    def list_open_disputes_for_admin(
        self,
    ) -> list[tuple[Lead, Report, str, str, str, str]]:
        tenant = aliased(User)
        landlord = aliased(User)
        statement = (
            select(
                Lead,
                Report,
                tenant.full_name,
                landlord.full_name,
                Listing.title,
                Listing.address,
            )
            .join(Report, Report.lead_id == Lead.lead_id)
            .join(tenant, tenant.user_id == Lead.tenant_id)
            .join(landlord, landlord.user_id == Lead.landlord_id)
            .join(Listing, Listing.listing_id == Lead.listing_id)
            .where(
                Lead.dispute_status == "open",
                Report.status.in_(("open", "under_review")),
            )
            .order_by(Report.created_at, Report.report_id)
        )
        return [
            (lead, report, tenant_name, landlord_name, title, address)
            for (
                lead,
                report,
                tenant_name,
                landlord_name,
                title,
                address,
            ) in self._db.execute(statement).all()
        ]

    def add_history(
        self,
        *,
        lead_id: int,
        from_stage: str | None,
        to_stage: str,
        actor_user_id: int,
        changed_at: datetime | None = None,
        note: str | None = None,
    ) -> LeadStageHistory:
        history = LeadStageHistory(
            lead_id=lead_id,
            from_stage=from_stage,
            to_stage=to_stage,
            actor_user_id=actor_user_id,
            changed_at=changed_at,
            note=note,
        )
        self._db.add(history)
        self._db.flush()
        return history

    def list_history(self, lead_id: int) -> list[LeadStageHistory]:
        statement = (
            select(LeadStageHistory)
            .where(LeadStageHistory.lead_id == lead_id)
            .order_by(
                LeadStageHistory.changed_at,
                LeadStageHistory.history_id,
            )
        )
        return list(self._db.scalars(statement).all())

    def count_by_stage_for_landlord(self, landlord_id: int) -> dict[str, int]:
        statement = (
            select(Lead.stage, func.count(Lead.lead_id))
            .where(Lead.landlord_id == landlord_id)
            .group_by(Lead.stage)
        )
        return {
            stage: int(count)
            for stage, count in self._db.execute(statement).all()
        }

    def count_open_disputes_for_landlord(self, landlord_id: int) -> int:
        statement = select(func.count(Lead.lead_id)).where(
            Lead.landlord_id == landlord_id,
            Lead.dispute_status == "open",
        )
        return int(self._db.scalar(statement) or 0)
