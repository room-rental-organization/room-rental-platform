from datetime import datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.lead import Lead
from app.repositories.lead_repository import LeadRepository
from app.repositories.report_repository import ReportRepository
from app.schemas.lead import (
    AdminLeadDisputeResponse,
    AdminLeadDetailResponse,
    LandlordLeadDetailResponse,
    LandlordLeadResponse,
    LeadConversionSummary,
    LeadStageCounts,
    LeadStageHistoryResponse,
    TenantLeadDetailResponse,
    TenantLeadResponse,
    TenantLeadStageHistoryResponse,
)
from app.schemas.report import ReportHistoryResponse


class LeadError(Exception):
    pass


class LeadNotFoundError(LeadError):
    pass




class LeadStateError(LeadError):
    pass


class LeadService:
    NEW = "NEW"
    CONTACTED = "CONTACTED"
    VIEWING_SCHEDULED = "VIEWING_SCHEDULED"
    VIEWING_COMPLETED = "VIEWING_COMPLETED"
    INTERESTED = "INTERESTED"
    RENTED = "RENTED"
    UNSUCCESSFUL = "UNSUCCESSFUL"
    LANDLORD_TRANSITIONS = {
        NEW: {CONTACTED, UNSUCCESSFUL},
        CONTACTED: {VIEWING_SCHEDULED, INTERESTED, UNSUCCESSFUL},
        VIEWING_SCHEDULED: {VIEWING_COMPLETED, UNSUCCESSFUL},
        VIEWING_COMPLETED: {INTERESTED, UNSUCCESSFUL},
        INTERESTED: {RENTED, UNSUCCESSFUL},
    }

    def __init__(self, db: Session) -> None:
        self._db = db
        self._leads = LeadRepository(db)
        self._reports = ReportRepository(db)

    def list_for_landlord(self, landlord_id: int) -> list[LandlordLeadResponse]:
        return [
            LandlordLeadResponse.model_validate(lead)
            for lead in self._leads.list_for_landlord(landlord_id)
        ]

    def get_for_landlord(
        self,
        lead_id: int,
        landlord_id: int,
    ) -> LandlordLeadDetailResponse:
        lead = self._leads.get_for_landlord(lead_id, landlord_id)
        if lead is None:
            raise LeadNotFoundError("Lead does not exist.")
        return self._landlord_detail(lead)

    def list_for_tenant(self, tenant_id: int) -> list[TenantLeadResponse]:
        return [
            TenantLeadResponse.model_validate(
                {
                    "lead_id": lead.lead_id,
                    "contact_request_id": lead.contact_request_id,
                    "listing_id": lead.listing_id,
                    "listing_title": listing_title,
                    "listing_address": listing_address,
                    "stage": lead.stage,
                    "dispute_status": lead.dispute_status,
                    "rented_at": lead.rented_at,
                    "created_at": lead.created_at,
                    "updated_at": lead.updated_at,
                },
            )
            for lead, listing_title, listing_address in
            self._leads.list_for_tenant_with_listing(tenant_id)
        ]

    def get_for_tenant(
        self,
        lead_id: int,
        tenant_id: int,
    ) -> TenantLeadDetailResponse:
        lead_with_listing = self._leads.get_for_tenant_with_listing(
            lead_id,
            tenant_id,
        )
        if lead_with_listing is None:
            raise LeadNotFoundError("Lead does not exist.")
        lead, listing_title, listing_address = lead_with_listing
        return self._tenant_detail(lead, listing_title, listing_address)

    def list_for_admin(
        self,
        stage_filter: str | None = None,
    ) -> list[LandlordLeadResponse]:
        return [
            LandlordLeadResponse.model_validate(lead)
            for lead in self._leads.list_for_admin(stage_filter)
        ]

    def get_for_admin(self, lead_id: int) -> AdminLeadDetailResponse:
        lead = self._leads.get_for_admin(lead_id)
        if lead is None:
            raise LeadNotFoundError("Lead does not exist.")
        return self._admin_detail(lead)

    def list_open_disputes_for_admin(self) -> list[AdminLeadDisputeResponse]:
        responses: list[AdminLeadDisputeResponse] = []
        for (
            lead,
            report,
            tenant_name,
            landlord_name,
            listing_title,
            listing_address,
        ) in self._leads.list_open_disputes_for_admin():
            responses.append(
                AdminLeadDisputeResponse(
                    lead_id=lead.lead_id,
                    contact_request_id=lead.contact_request_id,
                    tenant_id=lead.tenant_id,
                    tenant_name=tenant_name,
                    landlord_id=lead.landlord_id,
                    landlord_name=landlord_name,
                    listing_id=lead.listing_id,
                    listing_title=listing_title,
                    listing_address=listing_address,
                    stage=lead.stage,
                    dispute_status=lead.dispute_status,
                    rented_at=lead.rented_at,
                    unsuccessful_reason=lead.unsuccessful_reason,
                    created_at=lead.created_at,
                    updated_at=lead.updated_at,
                    report_id=report.report_id,
                    report_status=report.status,
                    report_reason=report.reason,
                    report_details=report.details,
                    report_created_at=report.created_at,
                    history=[
                        LeadStageHistoryResponse.model_validate(item)
                        for item in self._leads.list_history(lead.lead_id)
                    ],
                    report_history=[
                        ReportHistoryResponse.model_validate(item)
                        for item in self._reports.list_history(report.report_id)
                    ],
                ),
            )
        return responses

    def summary_for_landlord(self, landlord_id: int) -> LeadConversionSummary:
        counts = self._leads.count_by_stage_for_landlord(landlord_id)
        rented = counts.get(self.RENTED, 0)
        unsuccessful = counts.get(self.UNSUCCESSFUL, 0)
        closed = rented + unsuccessful
        disputed = self._leads.count_open_disputes_for_landlord(landlord_id)
        return LeadConversionSummary(
            total_leads=sum(counts.values()),
            closed_leads=closed,
            conversion_rate=(rented / closed * 100) if closed else 0,
            stages=LeadStageCounts(
                new=counts.get(self.NEW, 0),
                contacted=counts.get(self.CONTACTED, 0),
                viewing_scheduled=counts.get(self.VIEWING_SCHEDULED, 0),
                viewing_completed=counts.get(self.VIEWING_COMPLETED, 0),
                interested=counts.get(self.INTERESTED, 0),
                rented=rented,
                unsuccessful=unsuccessful,
                disputed=disputed,
            ),
        )

    def update_for_landlord(
        self,
        lead_id: int,
        landlord_id: int,
        stage: str,
        note: str | None,
    ) -> LandlordLeadDetailResponse:
        lead = self._get_for_landlord_update(lead_id, landlord_id)
        if stage in {self.RENTED, self.UNSUCCESSFUL}:
            raise LeadStateError(
                "Use the dedicated outcome or dispute workflow for this stage.",
            )
        if stage not in self.LANDLORD_TRANSITIONS.get(lead.stage, set()):
            raise LeadStateError(
                f"Lead cannot transition from {lead.stage} to {stage}.",
            )
        self._transition(lead, stage, landlord_id, note)
        self._commit()
        return self._landlord_detail(lead)

    def record_rented(
        self,
        lead_id: int,
        landlord_id: int,
        note: str | None,
    ) -> LandlordLeadDetailResponse:
        lead = self._get_for_landlord_update(lead_id, landlord_id)
        if self.RENTED not in self.LANDLORD_TRANSITIONS.get(lead.stage, set()):
            raise LeadStateError(
                "Only an interested lead can be marked as rented.",
            )
        self._transition(lead, self.RENTED, landlord_id, note)
        self._commit()
        return self._landlord_detail(lead)

    def record_unsuccessful(
        self,
        lead_id: int,
        landlord_id: int,
        reason: str,
    ) -> LandlordLeadDetailResponse:
        lead = self._get_for_landlord_update(lead_id, landlord_id)
        if self.UNSUCCESSFUL not in self.LANDLORD_TRANSITIONS.get(lead.stage, set()):
            raise LeadStateError(
                "This lead can no longer be marked unsuccessful.",
            )
        self._transition(
            lead,
            self.UNSUCCESSFUL,
            landlord_id,
            reason,
            unsuccessful_reason=reason,
        )
        self._commit()
        return self._landlord_detail(lead)

    def resolve_dispute(
        self,
        lead_id: int,
        admin_id: int,
        stage: str,
        note: str,
    ) -> AdminLeadDetailResponse:
        lead = self._leads.get_for_admin(lead_id, for_update=True)
        if lead is None:
            raise LeadNotFoundError("Lead does not exist.")
        if lead.dispute_status != "open":
            raise LeadStateError("Only disputed leads can be resolved.")
        normalized_note = note.strip()
        if normalized_note == "":
            raise LeadStateError("A resolution reason is required.")
        report = self._reports.get_active_lead_dispute(
            lead_id,
            for_update=True,
        )
        if report is None:
            raise LeadStateError("The active dispute report could not be found.")
        if stage != lead.stage:
            self._transition(
                lead,
                stage,
                admin_id,
                normalized_note,
                unsuccessful_reason=(
                    normalized_note if stage == self.UNSUCCESSFUL else None
                ),
            )
        lead.dispute_status = "resolved"
        lead.updated_at = self._now()
        if report.admin_id is None:
            report.admin_id = admin_id
            self._reports.add_history(report.report_id, admin_id, "assigned")
        report.status = "resolved"
        self._reports.add_history(
            report.report_id,
            admin_id,
            "resolved",
            normalized_note,
        )
        self._commit()
        return self._admin_detail(lead)

    def dismiss_dispute(
        self,
        lead_id: int,
        admin_id: int,
        reason: str,
    ) -> AdminLeadDetailResponse:
        lead = self._leads.get_for_admin(lead_id, for_update=True)
        if lead is None:
            raise LeadNotFoundError("Lead does not exist.")
        if lead.dispute_status != "open":
            raise LeadStateError("Only disputed leads can be dismissed.")
        normalized_reason = reason.strip()
        if normalized_reason == "":
            raise LeadStateError("A dismissal reason is required.")
        report = self._reports.get_active_lead_dispute(
            lead_id,
            for_update=True,
        )
        if report is None:
            raise LeadStateError("The active dispute report could not be found.")

        lead.dispute_status = "dismissed"
        lead.updated_at = self._now()
        if report.admin_id is None:
            report.admin_id = admin_id
            self._reports.add_history(report.report_id, admin_id, "assigned")
        report.status = "dismissed"
        self._reports.add_history(
            report.report_id,
            admin_id,
            "dismissed",
            normalized_reason,
        )
        self._commit()
        return self._admin_detail(lead)

    def prepare_report_dispute(
        self,
        lead: Lead,
    ) -> None:
        if lead.dispute_status == "open":
            raise LeadStateError("This lead is already under dispute review.")
        lead.dispute_status = "open"
        lead.billing_eligible = False
        lead.updated_at = self._now()

    def _get_for_landlord_update(
        self,
        lead_id: int,
        landlord_id: int,
    ) -> Lead:
        lead = self._leads.get_for_landlord(
            lead_id,
            landlord_id,
            for_update=True,
        )
        if lead is None:
            raise LeadNotFoundError("Lead does not exist.")
        if lead.dispute_status == "open":
            raise LeadStateError(
                "Lead updates are paused while an inaccurate-record report is under review.",
            )
        return lead

    def _transition(
        self,
        lead: Lead,
        stage: str,
        actor_user_id: int,
        note: str | None,
        *,
        unsuccessful_reason: str | None = None,
    ) -> None:
        previous_stage = lead.stage
        changed_at = self._now()
        lead.stage = stage
        lead.updated_at = changed_at

        if stage == self.RENTED:
            lead.rented_at = changed_at
            lead.unsuccessful_reason = None
        elif stage == self.UNSUCCESSFUL:
            lead.rented_at = None
            lead.unsuccessful_reason = unsuccessful_reason
        else:
            lead.rented_at = None
            lead.unsuccessful_reason = None

        try:
            self._leads.add_history(
                lead_id=lead.lead_id,
                from_stage=previous_stage,
                to_stage=stage,
                actor_user_id=actor_user_id,
                changed_at=changed_at,
                note=note,
            )
        except SQLAlchemyError:
            self._db.rollback()
            raise

    def _landlord_detail(self, lead: Lead) -> LandlordLeadDetailResponse:
        response = LandlordLeadResponse.model_validate(lead)
        return LandlordLeadDetailResponse.model_validate(
            {
                **response.model_dump(),
                "history": [
                    LeadStageHistoryResponse.model_validate(item)
                    for item in self._leads.list_history(lead.lead_id)
                ],
            },
        )

    def _tenant_detail(
        self,
        lead: Lead,
        listing_title: str,
        listing_address: str,
    ) -> TenantLeadDetailResponse:
        response = TenantLeadResponse.model_validate(
            {
                "lead_id": lead.lead_id,
                "contact_request_id": lead.contact_request_id,
                "listing_id": lead.listing_id,
                "listing_title": listing_title,
                "listing_address": listing_address,
                "stage": lead.stage,
                "dispute_status": lead.dispute_status,
                "rented_at": lead.rented_at,
                "created_at": lead.created_at,
                "updated_at": lead.updated_at,
            },
        )
        return TenantLeadDetailResponse.model_validate(
            {
                **response.model_dump(),
                "listing_title": listing_title,
                "listing_address": listing_address,
                "history": [
                    TenantLeadStageHistoryResponse.model_validate(item)
                    for item in self._leads.list_history(lead.lead_id)
                ],
            },
        )

    def _admin_detail(self, lead: Lead) -> AdminLeadDetailResponse:
        response = LandlordLeadResponse.model_validate(lead)
        return AdminLeadDetailResponse.model_validate(
            {
                **response.model_dump(),
                "history": [
                    LeadStageHistoryResponse.model_validate(item)
                    for item in self._leads.list_history(lead.lead_id)
                ],
            },
        )

    def _commit(self) -> None:
        try:
            self._db.commit()
        except SQLAlchemyError:
            self._db.rollback()
            raise

    @staticmethod
    def _now() -> datetime:
        return datetime.now()
