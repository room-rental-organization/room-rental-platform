import unittest
from datetime import datetime
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.api.dependencies import get_current_user
from app.api.v1.endpoints.leads import (
    admin_dependency,
    get_lead_service,
    landlord_dependency,
    router,
    tenant_dependency,
)
from app.db.session import get_db
from app.models.role import Role
from app.models.user import User
from app.services.lead_service import LeadNotFoundError, LeadStateError


class LeadEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(router, prefix="/api/v1")
        self.landlord = User(user_id=8)
        self.tenant = User(user_id=7)
        self.admin = User(user_id=9)
        self.user = self.landlord
        self.service = Mock()
        self.db = Mock()
        self.app.dependency_overrides[get_lead_service] = lambda: self.service
        self.app.dependency_overrides[landlord_dependency] = (
            lambda: self.landlord
        )
        self.app.dependency_overrides[tenant_dependency] = lambda: self.tenant
        self.app.dependency_overrides[admin_dependency] = lambda: self.admin
        self.app.dependency_overrides[get_current_user] = lambda: self.user
        self.app.dependency_overrides[get_db] = lambda: self.db
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()

    @staticmethod
    def landlord_detail() -> dict[str, object]:
        return {
            "lead_id": 1,
            "contact_request_id": 5,
            "tenant_id": 7,
            "landlord_id": 8,
            "listing_id": 14,
            "stage": "NEW",
            "dispute_status": "none",
            "rented_at": None,
            "unsuccessful_reason": None,
            "created_at": datetime(2026, 10, 30, 8, 0),
            "updated_at": datetime(2026, 10, 30, 8, 0),
            "history": [],
        }

    def test_landlord_reads_only_own_leads(self) -> None:
        self.service.list_for_landlord.return_value = []
        self.service.get_for_landlord.side_effect = LeadNotFoundError(
            "Lead does not exist.",
        )

        list_response = self.client.get("/api/v1/users/me/leads")
        detail_response = self.client.get("/api/v1/users/me/leads/1")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(detail_response.status_code, 404)
        self.service.list_for_landlord.assert_called_once_with(8)
        self.service.get_for_landlord.assert_called_once_with(1, 8)

    def test_landlord_updates_stage_and_conflicts_are_explicit(self) -> None:
        self.service.update_for_landlord.return_value = self.landlord_detail()
        response = self.client.patch(
            "/api/v1/users/me/leads/1/stage",
            json={"stage": "CONTACTED", "note": "Contacted in platform chat."},
        )

        self.assertEqual(response.status_code, 200)
        self.service.update_for_landlord.assert_called_once_with(
            1,
            8,
            "CONTACTED",
            "Contacted in platform chat.",
        )

        self.service.update_for_landlord.side_effect = LeadStateError(
            "Invalid stage transition.",
        )
        conflict = self.client.patch(
            "/api/v1/users/me/leads/1/stage",
            json={"stage": "RENTED", "note": "Not a valid direct transition."},
        )
        self.assertEqual(conflict.status_code, 409)

    def test_tenant_detail_response_does_not_expose_internal_fields(self) -> None:
        self.service.get_for_tenant.return_value = {
            "lead_id": 1,
            "contact_request_id": 5,
            "listing_id": 14,
            "listing_title": "Room",
            "listing_address": "1 Main Road",
            "stage": "CONTACTED",
            "dispute_status": "none",
            "rented_at": None,
            "created_at": datetime(2026, 10, 30, 8, 0),
            "updated_at": datetime(2026, 10, 30, 9, 0),
            "history": [
                {
                    "history_id": 2,
                    "from_stage": "NEW",
                    "to_stage": "CONTACTED",
                    "changed_at": datetime(2026, 10, 30, 9, 0),
                },
            ],
        }
        response = self.client.get(
            "/api/v1/users/me/lead-enquiries/1",
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("actor_user_id", response.json()["history"][0])
        self.assertNotIn("note", response.json()["history"][0])
        self.assertNotIn("tenant_id", response.json())
        self.assertNotIn("landlord_id", response.json())

    def test_admin_can_inspect_and_resolve_a_lead(self) -> None:
        self.service.get_for_admin.return_value = self.landlord_detail()
        response = self.client.get("/api/v1/admin/leads/1")

        self.assertEqual(response.status_code, 200)
        self.service.get_for_admin.assert_called_once_with(1)

        self.service.resolve_dispute.return_value = self.landlord_detail()
        response = self.client.patch(
            "/api/v1/admin/leads/1/stage",
            json={"stage": "INTERESTED", "note": "Reviewed."},
        )
        self.assertEqual(response.status_code, 200)
        self.service.resolve_dispute.assert_called_once_with(
            1,
            9,
            "INTERESTED",
            "Reviewed.",
        )

    def test_admin_can_list_open_disputes_and_dismiss_through_lead_workflow(
        self,
    ) -> None:
        self.service.list_open_disputes_for_admin.return_value = []
        response = self.client.get("/api/v1/admin/lead-disputes")
        self.assertEqual(response.status_code, 200)
        self.service.list_open_disputes_for_admin.assert_called_once_with()

        self.service.dismiss_dispute.return_value = {
            **self.landlord_detail(),
            "dispute_status": "dismissed",
        }
        response = self.client.post(
            "/api/v1/admin/leads/1/dismiss-dispute",
            json={"reason": "The original record was accurate."},
        )
        self.assertEqual(response.status_code, 200)
        self.service.dismiss_dispute.assert_called_once_with(
            1,
            9,
            "The original record was accurate.",
        )

    def test_admin_routes_enforce_admin_role(self) -> None:
        self.app.dependency_overrides.pop(admin_dependency)
        self.user = User(user_id=7)
        roles = Mock()
        roles.list_for_user.return_value = [Role(role_id=1, name="tenant")]

        with patch(
            "app.api.dependencies.RoleRepository",
            return_value=roles,
        ):
            response = self.client.get("/api/v1/admin/leads")

        self.assertEqual(response.status_code, 403)
        self.service.list_for_admin.assert_not_called()

    def test_tenant_lead_route_rejects_landlord_only_user(self) -> None:
        self.app.dependency_overrides.pop(tenant_dependency)
        self.user = self.landlord
        roles = Mock()
        roles.list_for_user.return_value = [Role(role_id=2, name="landlord")]

        with patch(
            "app.api.dependencies.RoleRepository",
            return_value=roles,
        ):
            response = self.client.get("/api/v1/users/me/lead-enquiries")

        self.assertEqual(response.status_code, 403)
        self.service.list_for_tenant.assert_not_called()

    def test_database_errors_return_service_unavailable(self) -> None:
        self.service.list_for_landlord.side_effect = SQLAlchemyError(
            "database failure",
        )

        response = self.client.get("/api/v1/users/me/leads")

        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
