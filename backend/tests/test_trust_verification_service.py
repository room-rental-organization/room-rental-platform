import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.models.listing import Listing
from app.models.trust_verification import TrustVerificationRequest
from app.models.user import User
from app.schemas.trust_verification import (
    VerificationDecisionRequest,
    VerificationResubmissionRequest,
    VerificationSubmissionRequest,
)
from app.services.trust_verification_service import (
    TrustVerificationService,
    VerificationListingError,
    VerificationRateLimitError,
    VerificationRequestNotFoundError,
    VerificationSubmissionStateError,
)


class TrustVerificationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = Mock()
        self.settings = SimpleNamespace(
            trust_verification_max_submissions_per_day=5,
        )
        with patch(
            "app.services.trust_verification_service.get_settings",
            return_value=self.settings,
        ):
            self.service = TrustVerificationService(self.db)
        self.requests = Mock()
        self.listings = Mock()
        self.service._requests = self.requests
        self.service._listings = self.listings
        self.requests.count_submissions_since.return_value = 0
        self.requests.latest_for_subject.return_value = None

    def test_submit_identity_request_keeps_statement_private(self) -> None:
        now = datetime.now(timezone.utc)

        def assign_id(request: TrustVerificationRequest) -> TrustVerificationRequest:
            request.request_id = 12
            request.submitted_at = now
            request.updated_at = now
            return request

        self.requests.add.side_effect = assign_id
        result = self.service.submit(
            7,
            VerificationSubmissionRequest(
                verification_type="identity",
                evidence_statement="I can present identity evidence securely.",
            ),
        )

        self.assertEqual(result.status, "pending")
        self.assertEqual(result.request_id, 12)
        self.assertFalse(hasattr(result, "evidence_statement"))
        self.requests.add_history.assert_called_once_with(12, 7, "submitted")
        self.db.commit.assert_called_once()

    def test_property_authorization_requires_landlord_listing_ownership(self) -> None:
        self.listings.get_owned.return_value = None

        with self.assertRaises(VerificationListingError):
            self.service.submit(
                7,
                VerificationSubmissionRequest(
                    verification_type="property_authorization",
                    listing_id=24,
                    evidence_statement="I have authority to advertise this room.",
                ),
            )

        self.requests.add.assert_not_called()
        self.db.commit.assert_not_called()

    def test_duplicate_pending_request_is_rejected(self) -> None:
        self.requests.latest_for_subject.return_value = TrustVerificationRequest(
            request_id=5,
            user_id=7,
            verification_type="identity",
            status="pending",
            evidence_statement="I can present identity evidence securely.",
        )

        with self.assertRaises(VerificationSubmissionStateError):
            self.service.submit(
                7,
                VerificationSubmissionRequest(
                    verification_type="identity",
                    evidence_statement="I can present identity evidence securely.",
                ),
            )

        self.requests.add.assert_not_called()

    def test_daily_submission_limit_counts_resubmission_events(self) -> None:
        self.requests.count_submissions_since.return_value = 5

        with self.assertRaises(VerificationRateLimitError):
            self.service.submit(
                7,
                VerificationSubmissionRequest(
                    verification_type="identity",
                    evidence_statement="I can present identity evidence securely.",
                ),
            )

        self.requests.add.assert_not_called()

    def test_resubmission_is_owner_scoped(self) -> None:
        self.requests.get_for_user.return_value = None

        with self.assertRaises(VerificationRequestNotFoundError):
            self.service.resubmit(
                5,
                7,
                VerificationResubmissionRequest(
                    evidence_statement="Updated evidence will be shown securely.",
                ),
            )

        self.requests.get_for_user.assert_called_once_with(
            5,
            7,
            for_update=True,
        )
        self.db.commit.assert_not_called()

    def test_rejected_request_can_be_resubmitted_with_audit_history(self) -> None:
        now = datetime.now(timezone.utc)
        request = TrustVerificationRequest(
            request_id=5,
            user_id=7,
            verification_type="identity",
            status="rejected",
            evidence_statement="Previous statement.",
            decision_reason="Please provide a clearer statement.",
            submitted_at=now - timedelta(days=1),
            updated_at=now - timedelta(days=1),
        )
        self.requests.get_for_user.return_value = request

        result = self.service.resubmit(
            5,
            7,
            VerificationResubmissionRequest(
                evidence_statement="Updated evidence will be shown securely.",
            ),
        )

        self.assertEqual(result.status, "pending")
        self.assertIsNone(result.decision_reason)
        self.assertEqual(
            request.evidence_statement,
            "Updated evidence will be shown securely.",
        )
        self.requests.add_history.assert_called_once_with(5, 7, "resubmitted")
        self.db.commit.assert_called_once()

    def test_admin_approval_expires_property_authorization_and_is_audited(self) -> None:
        request = TrustVerificationRequest(
            request_id=5,
            user_id=7,
            listing_id=24,
            verification_type="property_authorization",
            status="pending",
            evidence_statement="I have authority to advertise this room.",
            submitted_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.requests.get_for_admin.return_value = request

        result = self.service.decide(
            5,
            2,
            VerificationDecisionRequest(
                action="approve",
                reason="Authority checked through secure manual review.",
            ),
        )

        self.assertEqual(result.status, "approved")
        self.assertIsNotNone(result.expires_at)
        self.assertEqual(request.expires_at - request.updated_at, timedelta(days=365))
        self.requests.add_history.assert_called_once_with(
            5,
            2,
            "approved",
            "Authority checked through secure manual review.",
        )
        self.db.commit.assert_called_once()

    def test_owner_summary_exposes_status_but_not_private_statement(self) -> None:
        now = datetime.now(timezone.utc)
        landlord = User(
            user_id=7,
            full_name="Landlord",
            phone_no="+27123456789",
            email="landlord@example.test",
            created_at=now,
            phone_verified_at=now,
        )
        listing = Listing(
            listing_id=24,
            landlord_id=7,
            area_id=3,
            title="Room",
            description="A room description",
            room_type="single_room",
            monthly_rent=4000,
            deposit_amount=4000,
            address="A street",
            date_available=now.date(),
            status="active",
            created_at=now,
        )
        identity = TrustVerificationRequest(
            user_id=7,
            verification_type="identity",
            status="pending",
            evidence_statement="Private applicant statement.",
        )
        property_request = TrustVerificationRequest(
            user_id=7,
            listing_id=24,
            verification_type="property_authorization",
            status="approved",
            evidence_statement="Private property statement.",
            expires_at=now + timedelta(days=10),
        )
        self.listings.get_owned.return_value = listing
        self.db.get.return_value = landlord
        self.requests.latest_for_subject.side_effect = [
            identity,
            property_request,
        ]
        self.requests.count_active_listings.return_value = 2

        result = self.service.trust_for_owned_listing(24, 7)

        self.assertTrue(result.phone_verified)
        self.assertEqual(result.identity_status, "under_review")
        self.assertEqual(result.listing_verification_status, "verified")
        self.assertEqual(result.active_listing_count, 2)
        self.assertFalse(hasattr(result, "evidence_statement"))
        self.listings.get_owned.assert_called_once_with(24, 7)

    def test_trust_summary_rejects_a_listing_owned_by_someone_else(self) -> None:
        self.listings.get_owned.return_value = None

        result = self.service.trust_for_owned_listing(24, 99)

        self.assertIsNone(result)
        self.listings.get_owned.assert_called_once_with(24, 99)
        self.db.get.assert_not_called()
        self.requests.latest_for_subject.assert_not_called()


if __name__ == "__main__":
    unittest.main()
