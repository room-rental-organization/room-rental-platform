import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.api.v1.endpoints.trust_verification import (
    admin_dependency,
    get_trust_verification_service,
    get_whatsapp_service,
    landlord_dependency,
)
from app.api.v1.router import api_router
from app.models.role import Role
from app.models.user import User
from app.schemas.trust_verification import (
    AdminVerificationRequestResponse,
    PublicLandlordTrustResponse,
    VerificationRequestResponse,
)


class TrustVerificationEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(api_router)
        self.service = Mock()
        self.whatsapp_service = Mock()
        self.landlord = User(
            user_id=8,
            phone_no="+27123456789",
            phone_verified_at=datetime(2026, 11, 24),
        )
        self.admin = User(user_id=4)
        self.app.dependency_overrides[get_trust_verification_service] = (
            lambda: self.service
        )
        self.app.dependency_overrides[get_whatsapp_service] = (
            lambda: self.whatsapp_service
        )
        self.app.dependency_overrides[landlord_dependency] = (
            lambda: self.landlord
        )
        self.app.dependency_overrides[admin_dependency] = lambda: self.admin
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()

    def test_landlord_submission_uses_authenticated_user_and_hides_statement(self) -> None:
        self.service.submit.return_value = VerificationRequestResponse(
            request_id=11,
            verification_type="identity",
            listing_id=None,
            status="pending",
            decision_reason=None,
            expires_at=None,
            submitted_at=datetime(2026, 11, 24),
            updated_at=datetime(2026, 11, 24),
        )

        response = self.client.post(
            "/api/v1/users/me/trust-verifications",
            json={
                "verification_type": "identity",
                "evidence_statement": "I can present identity evidence securely.",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertNotIn("evidence_statement", response.json())
        self.assertEqual(self.service.submit.call_args.args[0], 8)

    def test_property_authorization_requires_listing_id(self) -> None:
        response = self.client.post(
            "/api/v1/users/me/trust-verifications",
            json={
                "verification_type": "property_authorization",
                "evidence_statement": "I have permission to advertise the home.",
            },
        )

        self.assertEqual(response.status_code, 422)
        self.service.submit.assert_not_called()

    def test_admin_can_review_request_and_record_reason(self) -> None:
        self.service.decide.return_value = AdminVerificationRequestResponse(
            request_id=11,
            user_id=8,
            verification_type="identity",
            listing_id=None,
            status="approved",
            evidence_statement="I can present identity evidence securely.",
            decision_reason="Checked using approved secure process.",
            expires_at=None,
            submitted_at=datetime(2026, 11, 24),
            updated_at=datetime(2026, 11, 24),
        )

        response = self.client.post(
            "/api/v1/admin/trust-verifications/11/decision",
            json={
                "action": "approve",
                "reason": "Checked using approved secure process.",
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("evidence_statement", response.json())
        self.service.decide.assert_called_once()
        self.assertEqual(self.service.decide.call_args.args[1], 4)

    def test_admin_route_rejects_non_admin_role(self) -> None:
        self.app.dependency_overrides.pop(admin_dependency)
        self.app.dependency_overrides[get_current_user] = lambda: User(user_id=7)
        roles = Mock()
        roles.list_for_user.return_value = [Role(role_id=3, name="tenant")]

        with patch(
            "app.api.dependencies.RoleRepository",
            return_value=roles,
        ):
            response = self.client.get("/api/v1/admin/trust-verifications")

        self.assertEqual(response.status_code, 403)
        self.service.list_for_admin.assert_not_called()

    def test_account_phone_verification_does_not_expose_phone_or_code(self) -> None:
        response = self.client.post(
            "/api/v1/users/me/phone-verification",
            json={"consent": True},
        )

        self.assertEqual(response.status_code, 202)
        self.assertNotIn(self.landlord.phone_no, response.text)
        self.assertNotIn("code", response.text.casefold())
        self.whatsapp_service.start_verification.assert_called_once_with(
            8,
            self.landlord.phone_no,
        )

    def test_public_trust_endpoint_returns_safe_status_only(self) -> None:
        self.service.public_trust_for_listing.return_value = (
            PublicLandlordTrustResponse(
                phone_verified=True,
                identity_status="unverified",
                property_authorization_status="under_review",
                listing_verification_status="under_review",
                active_listing_count=2,
                account_created_at=datetime(2025, 1, 1),
            )
        )

        response = self.client.get("/api/v1/listings/12/trust")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["listing_verification_status"], "under_review")
        for sensitive_field in (
            "phone_no",
            "identity_number",
            "evidence_statement",
            "decision_reason",
        ):
            self.assertNotIn(sensitive_field, response.json())


if __name__ == "__main__":
    unittest.main()
