from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.listing import Listing
from app.models.report import Report, ReportHistory
from app.repositories.lead_repository import LeadRepository
from app.repositories.listing_repository import ListingRepository
from app.repositories.report_repository import ReportRepository
from app.repositories.user_repository import UserRepository
from app.schemas.report import ReportCreateRequest, ReportResponse
from app.services.listing_service import ListingService
from app.services.lead_service import LeadService, LeadStateError


class ReportNotFoundError(Exception):
    pass


class ReportTargetNotFoundError(Exception):
    pass


class ReportStateError(Exception):
    pass


class ReportTargetError(Exception):
    pass


class ReportRateLimitError(Exception):
    pass


class ReportDuplicateError(Exception):
    pass


class ReportService:
    OPEN_STATUS = "open"
    UNDER_REVIEW_STATUS = "under_review"
    RESOLVED_STATUS = "resolved"
    DISMISSED_STATUS = "dismissed"

    def __init__(self, db: Session) -> None:
        self._db = db
        self._reports = ReportRepository(db)
        self._leads = LeadRepository(db)
        self._listings = ListingRepository(db)
        self._users = UserRepository(db)
        self._public_listings = ListingService(self._listings)
        self._max_submissions_per_day = (
            get_settings().report_max_submissions_per_day
        )

    def submit_report(
        self,
        tenant_id: int,
        request: ReportCreateRequest,
    ) -> ReportResponse:
        listing = (
            None
            if request.target == "lead"
            else self._get_public_listing(request.listing_id)
        )
        lead = None
        if request.target == "lead":
            lead = self._leads.get_for_tenant(
                request.lead_id or 0,
                tenant_id,
                for_update=True,
            )
            if lead is None:
                raise ReportTargetNotFoundError(
                    "The lead is not available for reporting.",
                )
            if lead.dispute_status == "open":
                raise ReportStateError(
                    "This lead is already under dispute review.",
                )
        target_user_id = self._resolve_target_user_id(request, listing, tenant_id)
        now = self._now()
        if self._reports.has_recent_duplicate(
            tenant_id,
            request.listing_id,
            target_user_id,
            request.reason,
            now - timedelta(days=1),
            request.lead_id,
        ):
            raise ReportDuplicateError(
                "You have already submitted this report recently.",
            )
        if (
            self._reports.count_submissions_since(
                tenant_id,
                now - timedelta(days=1),
            )
            >= self._max_submissions_per_day
        ):
            raise ReportRateLimitError(
                "Daily report submission limit reached. Try again later.",
            )
        report = Report(
            listing_id=request.listing_id,
            target_user_id=target_user_id,
            lead_id=request.lead_id,
            tenant_id=tenant_id,
            reason=request.reason,
            status=self.OPEN_STATUS,
            details=request.details,
        )
        try:
            self._reports.add(report)
            self._reports.add_history(
                report.report_id,
                tenant_id,
                "submitted",
            )
            if lead is not None:
                LeadService(self._db).prepare_report_dispute(lead)
            self._db.commit()
        except SQLAlchemyError:
            self._db.rollback()
            raise
        except LeadStateError as exc:
            self._db.rollback()
            raise ReportStateError(str(exc)) from exc
        return ReportResponse.model_validate(report)

    def list_for_tenant(self, tenant_id: int) -> list[ReportResponse]:
        return [
            ReportResponse.model_validate(report)
            for report in self._reports.list_for_tenant(tenant_id)
        ]

    def list_for_admin(
        self,
        status_filter: str | None = None,
    ) -> list[ReportResponse]:
        return [
            ReportResponse.model_validate(report)
            for report in self._reports.list_for_admin(status_filter)
        ]

    def get_history(self, report_id: int) -> list[ReportHistory]:
        self._get_report(report_id)
        return self._reports.list_history(report_id)

    def assign_to_self(
        self,
        report_id: int,
        admin_id: int,
    ) -> ReportResponse:
        report = self._get_report(report_id, for_update=True)
        if report.status != self.OPEN_STATUS or report.admin_id is not None:
            raise ReportStateError("Only unassigned open reports can be assigned.")
        report.admin_id = admin_id
        report.status = self.UNDER_REVIEW_STATUS
        self._record_and_commit(report_id, admin_id, "assigned")
        return ReportResponse.model_validate(report)

    def resolve_report(
        self,
        report_id: int,
        admin_id: int,
        note: str | None = None,
    ) -> ReportResponse:
        return self._close_report(
            report_id,
            admin_id,
            self.RESOLVED_STATUS,
            "resolved",
            note,
        )

    def dismiss_report(
        self,
        report_id: int,
        admin_id: int,
        note: str | None = None,
    ) -> ReportResponse:
        return self._close_report(
            report_id,
            admin_id,
            self.DISMISSED_STATUS,
            "dismissed",
            note,
        )

    def add_internal_note(
        self,
        report_id: int,
        admin_id: int,
        note: str,
    ) -> ReportResponse:
        report = self._get_report(report_id, for_update=True)
        if report.status != self.UNDER_REVIEW_STATUS:
            raise ReportStateError(
                "Internal notes can only be added to reports under review.",
            )
        self._record_and_commit(
            report_id,
            admin_id,
            "note_added",
            note.strip(),
        )
        return ReportResponse.model_validate(report)

    def _close_report(
        self,
        report_id: int,
        admin_id: int,
        new_status: str,
        action: str,
        note: str | None,
    ) -> ReportResponse:
        report = self._get_report(report_id)
        lead = None
        if report.lead_id is not None:
            lead = self._leads.get_for_admin(
                report.lead_id,
                for_update=True,
            )
            report = self._get_report(report_id, for_update=True)
        else:
            report = self._get_report(report_id, for_update=True)
        if report.status != self.UNDER_REVIEW_STATUS:
            raise ReportStateError(
                "Only reports under review can be resolved or dismissed.",
            )
        normalized_note = note.strip() if note is not None else None
        if report.lead_id is not None:
            if lead is None:
                raise ReportStateError(
                    "The lead associated with this report is unavailable.",
                )
            if lead.dispute_status != "open":
                raise ReportStateError(
                    "The lead dispute is no longer open.",
                )
            if not normalized_note:
                raise ReportStateError(
                    "A reason is required to resolve or dismiss a lead dispute.",
                )
            lead.dispute_status = (
                "resolved"
                if new_status == self.RESOLVED_STATUS
                else "dismissed"
            )
            lead.billing_eligible = False
            lead.updated_at = datetime.now()
        report.status = new_status
        try:
            self._reports.add_history(
                report_id,
                admin_id,
                action,
                normalized_note or None,
            )
            self._db.commit()
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return ReportResponse.model_validate(report)

    def _record_and_commit(
        self,
        report_id: int,
        actor_user_id: int,
        action: str,
        note: str | None = None,
    ) -> None:
        try:
            self._reports.add_history(
                report_id,
                actor_user_id,
                action,
                note,
            )
            self._db.commit()
        except SQLAlchemyError:
            self._db.rollback()
            raise

    def _get_report(
        self,
        report_id: int,
        *,
        for_update: bool = False,
    ) -> Report:
        report = self._reports.get_by_id(report_id, for_update=for_update)
        if report is None:
            raise ReportNotFoundError("Report does not exist.")
        return report

    def _get_public_listing(self, listing_id: int | None) -> Listing | None:
        if listing_id is None:
            return None
        if self._public_listings.get_public_listing(listing_id) is None:
            raise ReportTargetNotFoundError(
                "The listing is unavailable for reporting.",
            )
        return self._listings.get_by_id(listing_id)

    def _resolve_target_user_id(
        self,
        request: ReportCreateRequest,
        listing: Listing | None,
        tenant_id: int,
    ) -> int | None:
        if request.target == "listing":
            return None
        if request.target == "landlord":
            if listing is None:
                raise ReportTargetError(
                    "A landlord report must reference a public listing.",
                )
            target_user_id = listing.landlord_id
        elif request.target == "lead":
            return None
        else:
            target_user_id = request.target_user_id
            if target_user_id is None or self._users.get_by_id(target_user_id) is None:
                raise ReportTargetNotFoundError("The reported user does not exist.")

        if target_user_id == tenant_id:
            raise ReportTargetError("You cannot report your own account.")
        return target_user_id

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
