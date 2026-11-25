import unittest
from datetime import date, datetime
from decimal import Decimal
from unittest.mock import Mock

from sqlalchemy.exc import SQLAlchemyError

from app.models.listing import Listing
from app.models.lead import Lead
from app.models.report import Report
from app.schemas.listing import ListingResponse
from app.schemas.report import ReportCreateRequest
from app.services.report_service import (
    ReportDuplicateError,
    ReportRateLimitError,
    ReportService,
    ReportStateError,
    ReportTargetError,
    ReportTargetNotFoundError,
)


class ReportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Mock()
        self.service = ReportService(self.db)
        self.reports = Mock()
        self.listings = Mock()
        self.users = Mock()
        self.public_listings = Mock()
        self.service._reports = self.reports
        self.leads = Mock()
        self.service._leads = self.leads
        self.service._listings = self.listings
        self.service._users = self.users
        self.service._public_listings = self.public_listings
        self.reports.has_recent_duplicate.return_value = False
        self.reports.count_submissions_since.return_value = 0

    @staticmethod
    def make_listing(
        *,
        listing_id: int = 12,
        landlord_id: int = 9,
    ) -> Listing:
        return Listing(
            listing_id=listing_id,
            landlord_id=landlord_id,
            area_id=3,
            title="A room",
            description="A room description",
            room_type="single_room",
            monthly_rent=Decimal("4200.00"),
            deposit_amount=Decimal("4200.00"),
            address="Test address",
            date_available=date(2026, 11, 1),
            status="active",
            created_at=datetime(2026, 10, 1),
        )

    @staticmethod
    def make_report(
        *,
        report_id: int = 5,
        status: str = "open",
        admin_id: int | None = None,
        lead_id: int | None = None,
    ) -> Report:
        return Report(
            report_id=report_id,
            listing_id=None if lead_id is not None else 12,
            target_user_id=None,
            lead_id=lead_id,
            tenant_id=7,
            admin_id=admin_id,
            reason="scam",
            status=status,
            details="This listing appears suspicious.",
            created_at=datetime(2026, 10, 1),
        )

    @staticmethod
    def listing_report_request() -> ReportCreateRequest:
        return ReportCreateRequest(
            target="listing",
            listing_id=12,
            reason="scam",
            details="This listing appears suspicious.",
        )

    def test_submit_listing_report_records_submission_history(self) -> None:
        self.public_listings.get_public_listing.return_value = ListingResponse(
            listing_id=12,
            area_id=3,
            title="A room",
            description="A room description",
            room_type="single_room",
            monthly_rent=Decimal("4200.00"),
            deposit_amount=Decimal("4200.00"),
            address="Test address",
            date_available=date(2026, 11, 1),
            status="active",
            created_at=datetime(2026, 10, 1),
            photos=[],
        )
        self.listings.get_by_id.return_value = self.make_listing()

        def assign_id(report: Report) -> Report:
            report.report_id = 5
            report.created_at = datetime(2026, 10, 1)
            return report

        self.reports.add.side_effect = assign_id

        result = self.service.submit_report(7, self.listing_report_request())

        self.assertEqual(result.report_id, 5)
        self.assertEqual(result.status, "open")
        self.assertEqual(result.target_user_id, None)
        self.reports.add_history.assert_called_once_with(
            5,
            7,
            "submitted",
        )
        self.db.commit.assert_called_once()

    def test_submit_landlord_report_resolves_landlord_from_listing(
        self,
    ) -> None:
        self.public_listings.get_public_listing.return_value = Mock()
        self.listings.get_by_id.return_value = self.make_listing(landlord_id=9)
        self.reports.add.side_effect = lambda report: self._assign_report(report)

        self.service.submit_report(
            7,
            ReportCreateRequest(
                target="landlord",
                listing_id=12,
                reason="abusive",
                details="The landlord sent abusive messages.",
            ),
        )

        created_report = self.reports.add.call_args.args[0]
        self.assertEqual(created_report.target_user_id, 9)

    def test_submit_lead_report_marks_lead_disputed_with_history(self) -> None:
        lead = Lead(
            lead_id=22,
            contact_request_id=5,
            tenant_id=7,
            landlord_id=9,
            listing_id=12,
            stage="NEW",
            created_at=datetime(2026, 10, 1),
            updated_at=datetime(2026, 10, 1),
        )
        self.leads.get_for_tenant.return_value = lead
        self.reports.add.side_effect = lambda report: self._assign_report(report)

        result = self.service.submit_report(
            7,
            ReportCreateRequest(
                target="lead",
                lead_id=22,
                reason="inaccurate_info",
                details="The recorded lead stage is not accurate.",
            ),
        )

        self.assertEqual(result.lead_id, 22)
        self.assertEqual(lead.stage, "NEW")
        self.assertEqual(lead.dispute_status, "open")
        self.assertFalse(lead.billing_eligible)
        self.assertEqual(result.status, "open")
        self.db.add.assert_not_called()
        self.db.commit.assert_called_once()

    def test_duplicate_open_dispute_is_rejected(self) -> None:
        lead = Lead(
            lead_id=22,
            contact_request_id=5,
            tenant_id=7,
            landlord_id=9,
            listing_id=12,
            stage="CONTACTED",
            dispute_status="open",
        )
        self.leads.get_for_tenant.return_value = lead

        with self.assertRaises(ReportStateError):
            self.service.submit_report(
                7,
                ReportCreateRequest(
                    target="lead",
                    lead_id=22,
                    reason="inaccurate_info",
                    details="The recorded lead stage is not accurate.",
                ),
            )

        self.reports.add.assert_not_called()
        self.db.commit.assert_not_called()

    @staticmethod
    def _assign_report(report: Report) -> Report:
        report.report_id = 5
        report.created_at = datetime(2026, 10, 1)
        return report

    def test_submit_user_report_checks_target_exists(self) -> None:
        self.users.get_by_id.return_value = None

        with self.assertRaises(ReportTargetNotFoundError):
            self.service.submit_report(
                7,
                ReportCreateRequest(
                    target="user",
                    target_user_id=99,
                    reason="abusive",
                    details="This user sent abusive messages.",
                ),
            )

        self.reports.add.assert_not_called()
        self.db.commit.assert_not_called()

    def test_tenant_cannot_report_their_own_account(self) -> None:
        self.users.get_by_id.return_value = Mock()

        with self.assertRaises(ReportTargetError):
            self.service.submit_report(
                7,
                ReportCreateRequest(
                    target="user",
                    target_user_id=7,
                    reason="other",
                    details="This is a sufficiently detailed reason.",
                ),
            )

        self.reports.add.assert_not_called()

    def test_non_public_listing_cannot_be_reported(self) -> None:
        self.public_listings.get_public_listing.return_value = None

        with self.assertRaises(ReportTargetNotFoundError):
            self.service.submit_report(7, self.listing_report_request())

        self.reports.add.assert_not_called()

    def test_duplicate_reports_are_throttled(self) -> None:
        self.public_listings.get_public_listing.return_value = Mock()
        self.listings.get_by_id.return_value = self.make_listing()
        self.reports.has_recent_duplicate.return_value = True

        with self.assertRaises(ReportDuplicateError):
            self.service.submit_report(7, self.listing_report_request())

        self.reports.add.assert_not_called()
        self.db.commit.assert_not_called()

    def test_daily_report_limit_is_enforced(self) -> None:
        self.public_listings.get_public_listing.return_value = Mock()
        self.listings.get_by_id.return_value = self.make_listing()
        self.reports.count_submissions_since.return_value = 10

        with self.assertRaises(ReportRateLimitError):
            self.service.submit_report(7, self.listing_report_request())

        self.reports.add.assert_not_called()
        self.db.commit.assert_not_called()

    def test_assigning_open_report_sets_admin_and_under_review(self) -> None:
        report = self.make_report()
        self.reports.get_by_id.return_value = report

        result = self.service.assign_to_self(5, 11)

        self.assertEqual(result.status, "under_review")
        self.assertEqual(result.admin_id, 11)
        self.reports.add_history.assert_called_once_with(
            5,
            11,
            "assigned",
            None,
        )
        self.db.commit.assert_called_once()

    def test_only_open_unassigned_reports_can_be_assigned(self) -> None:
        self.reports.get_by_id.return_value = self.make_report(
            status="under_review",
            admin_id=11,
        )

        with self.assertRaises(ReportStateError):
            self.service.assign_to_self(5, 12)

        self.reports.add_history.assert_not_called()
        self.db.commit.assert_not_called()

    def test_any_admin_can_resolve_a_report_under_review(self) -> None:
        report = self.make_report(status="under_review", admin_id=11)
        self.reports.get_by_id.return_value = report

        result = self.service.resolve_report(5, 12, "Investigated")

        self.assertEqual(result.status, "resolved")
        self.assertEqual(result.admin_id, 11)
        self.reports.add_history.assert_called_once_with(
            5,
            12,
            "resolved",
            "Investigated",
        )
        self.db.commit.assert_called_once()

    def test_resolving_lead_report_closes_dispute_and_requires_reason(self) -> None:
        report = self.make_report(
            status="under_review",
            admin_id=11,
            lead_id=22,
        )
        lead = Lead(
            lead_id=22,
            contact_request_id=5,
            tenant_id=7,
            landlord_id=9,
            listing_id=12,
            stage="INTERESTED",
            dispute_status="open",
            billing_eligible=False,
        )
        self.reports.get_by_id.return_value = report
        self.leads.get_for_admin.return_value = lead

        result = self.service.resolve_report(5, 12, "Reviewed the record.")

        self.assertEqual(result.status, "resolved")
        self.assertEqual(lead.stage, "INTERESTED")
        self.assertEqual(lead.dispute_status, "resolved")
        self.assertFalse(lead.billing_eligible)
        self.reports.add_history.assert_called_once_with(
            5,
            12,
            "resolved",
            "Reviewed the record.",
        )
        self.db.commit.assert_called_once()

        report.status = "under_review"
        lead.dispute_status = "open"
        self.db.reset_mock()
        self.reports.add_history.reset_mock()
        with self.assertRaises(ReportStateError):
            self.service.resolve_report(5, 12)
        self.reports.add_history.assert_not_called()
        self.db.commit.assert_not_called()

    def test_dismissing_lead_report_closes_dispute_with_audit_reason(self) -> None:
        report = self.make_report(
            status="under_review",
            admin_id=11,
            lead_id=22,
        )
        lead = Lead(
            lead_id=22,
            contact_request_id=5,
            tenant_id=7,
            landlord_id=9,
            listing_id=12,
            stage="NEW",
            dispute_status="open",
        )
        self.reports.get_by_id.return_value = report
        self.leads.get_for_admin.return_value = lead

        result = self.service.dismiss_report(
            5,
            12,
            "Investigation found the original record was accurate.",
        )

        self.assertEqual(result.status, "dismissed")
        self.assertEqual(lead.dispute_status, "dismissed")
        self.assertEqual(lead.stage, "NEW")
        self.reports.add_history.assert_called_once_with(
            5,
            12,
            "dismissed",
            "Investigation found the original record was accurate.",
        )

    def test_only_reports_under_review_can_be_dismissed(self) -> None:
        self.reports.get_by_id.return_value = self.make_report(status="open")

        with self.assertRaises(ReportStateError):
            self.service.dismiss_report(5, 12)

        self.reports.add_history.assert_not_called()
        self.db.commit.assert_not_called()

    def test_history_write_failure_rolls_back_transaction(self) -> None:
        report = self.make_report(status="under_review", admin_id=11)
        self.reports.get_by_id.return_value = report
        self.reports.add_history.side_effect = SQLAlchemyError(
            "database unavailable",
        )

        with self.assertRaises(SQLAlchemyError):
            self.service.resolve_report(5, 12)

        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()

    def test_internal_note_requires_report_under_review(self) -> None:
        self.reports.get_by_id.return_value = self.make_report(status="open")

        with self.assertRaises(ReportStateError):
            self.service.add_internal_note(5, 11, "Internal follow up.")

        self.reports.add_history.assert_not_called()
        self.db.commit.assert_not_called()

    def test_internal_note_is_audited_on_report_history(self) -> None:
        self.reports.get_by_id.return_value = self.make_report(
            status="under_review",
            admin_id=11,
        )

        self.service.add_internal_note(5, 11, "  Checked the documents.  ")

        self.reports.add_history.assert_called_once_with(
            5,
            11,
            "note_added",
            "Checked the documents.",
        )
        self.db.commit.assert_called_once()

    def _assign_report(self, report: Report) -> Report:
        report.report_id = 5
        report.created_at = datetime(2026, 10, 1)
        return report


if __name__ == "__main__":
    unittest.main()
