import unittest
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.area import Area
from app.models.contact_request import ContactRequest
from app.models.report import Report, ReportHistory
from app.models.listing import Listing
from app.models.user import User
from app.repositories.lead_repository import LeadRepository
from app.services.lead_service import LeadNotFoundError, LeadService, LeadStateError


class LeadServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )
        self.db = session_factory()
        self.db.add_all(
            [
                User(
                    user_id=user_id,
                    full_name=f"User {user_id}",
                    phone_no=f"+2782000000{user_id}",
                    email=f"user{user_id}@example.test",
                )
                for user_id in (7, 8, 9)
            ],
        )
        self.db.add(Area(area_id=12, name="Central"))
        self.db.flush()
        self.db.add(
            Listing(
                listing_id=14,
                landlord_id=8,
                area_id=12,
                title="Room",
                description="Room available",
                room_type="single_room",
                monthly_rent=Decimal("2500.00"),
                deposit_amount=Decimal("2500.00"),
                address="1 Main Road",
                date_available=date(2026, 11, 1),
                availability_status="available",
                status="active",
            ),
        )
        self.db.add(
            ContactRequest(
                request_id=5,
                listing_id=14,
                tenant_id=7,
                status="pending",
                requested_at=datetime(2026, 10, 30, 8, 0),
            ),
        )
        self.db.commit()
        self.lead = LeadRepository(self.db).ensure_for_contact_request(
            contact_request_id=5,
            tenant_id=7,
            landlord_id=8,
            listing_id=14,
            created_at=datetime(2026, 10, 30, 8, 0),
        )
        self.db.commit()
        self.service = LeadService(self.db)

    def tearDown(self) -> None:
        self.db.close()
        self.engine.dispose()

    def test_landlord_and_admin_enquiries_include_the_same_room_and_names(self) -> None:
        for result in (self.service.list_for_landlord(8)[0], self.service.list_for_admin()[0]):
            with self.subTest(role=result.landlord_id):
                self.assertEqual(result.listing_title, "Room")
                self.assertEqual(result.tenant_name, "User 7")
                self.assertEqual(result.landlord_name, "User 8")
                for private_field in ("phone_no", "password_hash", "email", "tenant", "landlord", "listing"):
                    self.assertNotIn(private_field, result.model_dump())

    def test_repeated_ensure_returns_one_lead_and_one_initial_history_entry(
        self,
    ) -> None:
        duplicate = LeadRepository(self.db).ensure_for_contact_request(
            contact_request_id=5,
            tenant_id=7,
            landlord_id=8,
            listing_id=14,
            created_at=datetime(2026, 10, 30, 8, 0),
        )

        self.assertEqual(self.lead.lead_id, duplicate.lead_id)
        self.assertEqual(len(LeadRepository(self.db).list_history(duplicate.lead_id)), 1)
        self.assertFalse(duplicate.billing_eligible)

    def test_forward_transitions_keep_history_and_rental_outcome(self) -> None:
        self.service.update_for_landlord(
            self.lead.lead_id,
            8,
            "CONTACTED",
            "Sent a message through platform chat.",
        )
        self.service.update_for_landlord(
            self.lead.lead_id,
            8,
            "VIEWING_SCHEDULED",
            None,
        )
        self.service.update_for_landlord(
            self.lead.lead_id,
            8,
            "VIEWING_COMPLETED",
            None,
        )
        self.service.update_for_landlord(
            self.lead.lead_id,
            8,
            "INTERESTED",
            None,
        )
        result = self.service.record_rented(self.lead.lead_id, 8, None)

        self.assertEqual(result.stage, "RENTED")
        self.assertIsNotNone(result.rented_at)
        self.assertEqual(
            [entry.to_stage for entry in result.history],
            [
                "NEW",
                "CONTACTED",
                "VIEWING_SCHEDULED",
                "VIEWING_COMPLETED",
                "INTERESTED",
                "RENTED",
            ],
        )
        with self.assertRaises(LeadStateError):
            self.service.update_for_landlord(
                self.lead.lead_id,
                8,
                "CONTACTED",
                None,
            )

    def test_invalid_transition_is_rejected_and_unsuccessful_requires_reason(
        self,
    ) -> None:
        with self.assertRaises(LeadStateError):
            self.service.update_for_landlord(
                self.lead.lead_id,
                8,
                "VIEWING_COMPLETED",
                None,
            )

        result = self.service.record_unsuccessful(
            self.lead.lead_id,
            8,
            "Tenant selected another property.",
        )

        self.assertEqual(result.stage, "UNSUCCESSFUL")
        self.assertEqual(
            result.unsuccessful_reason,
            "Tenant selected another property.",
        )
        self.assertEqual(
            result.history[-1].note,
            "Tenant selected another property.",
        )

    def test_landlord_ownership_and_tenant_scope_are_enforced(self) -> None:
        with self.assertRaises(LeadNotFoundError):
            self.service.get_for_landlord(self.lead.lead_id, 7)
        with self.assertRaises(LeadNotFoundError):
            self.service.get_for_tenant(self.lead.lead_id, 8)

        self.assertEqual(
            self.service.get_for_landlord(self.lead.lead_id, 8).lead_id,
            self.lead.lead_id,
        )
        self.assertEqual(
            self.service.get_for_tenant(self.lead.lead_id, 7).lead_id,
            self.lead.lead_id,
        )

    def test_tenant_detail_hides_internal_history_notes(self) -> None:
        self.service.update_for_landlord(
            self.lead.lead_id,
            8,
            "CONTACTED",
            "Internal landlord note.",
        )

        tenant_detail = self.service.get_for_tenant(self.lead.lead_id, 7)
        serialized = tenant_detail.model_dump()

        self.assertNotIn("Internal landlord note.", str(serialized))
        self.assertNotIn("actor_user_id", serialized["history"][0])
        self.assertNotIn("phone_no", serialized)
        self.assertNotIn("unsuccessful_reason", serialized)

    def test_tenant_lead_list_includes_only_own_listing_information(self) -> None:
        rows = self.service.list_for_tenant(7)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].listing_title, "Room")
        self.assertEqual(rows[0].listing_address, "1 Main Road")
        self.assertEqual(rows[0].dispute_status, "none")
        self.assertNotIn("tenant_id", rows[0].model_dump())

    def add_dispute_report(self) -> Report:
        report = Report(
            report_id=1,
            lead_id=self.lead.lead_id,
            tenant_id=7,
            reason="inaccurate_info",
            status="under_review",
            details="The recorded lead stage is not accurate.",
        )
        self.db.add(report)
        self.db.commit()
        return report

    def test_admin_resolves_dispute_without_losing_conversion_history(self) -> None:
        self.service.update_for_landlord(
            self.lead.lead_id,
            8,
            "CONTACTED",
            "Contacted the tenant.",
        )
        report = self.add_dispute_report()
        self.lead.billing_eligible = True
        self.service.prepare_report_dispute(self.lead)
        self.db.commit()
        stage_history_before_resolution = LeadRepository(self.db).list_history(
            self.lead.lead_id,
        )

        result = self.service.resolve_dispute(
            self.lead.lead_id,
            9,
            "INTERESTED",
            "Investigation confirmed the stage.",
        )

        self.assertEqual(result.stage, "INTERESTED")
        self.assertEqual(result.dispute_status, "resolved")
        self.assertEqual(
            result.history[-1].from_stage,
            "CONTACTED",
        )
        self.assertEqual(
            len(LeadRepository(self.db).list_history(self.lead.lead_id)),
            len(stage_history_before_resolution) + 1,
        )
        self.assertFalse(self.lead.billing_eligible)
        self.assertEqual(report.status, "resolved")
        report_history = list(
            self.db.query(ReportHistory)
            .filter(ReportHistory.report_id == report.report_id)
            .order_by(ReportHistory.history_id)
        )
        self.assertEqual(
            [entry.action for entry in report_history],
            ["assigned", "resolved"],
        )
        self.assertEqual(
            report_history[-1].note,
            "Investigation confirmed the stage.",
        )

    def test_admin_dismissal_preserves_conversion_stage_and_audits_reason(self) -> None:
        self.service.update_for_landlord(
            self.lead.lead_id,
            8,
            "CONTACTED",
            None,
        )
        report = self.add_dispute_report()
        self.service.prepare_report_dispute(self.lead)
        self.db.commit()
        history_before = LeadRepository(self.db).list_history(self.lead.lead_id)

        result = self.service.dismiss_dispute(
            self.lead.lead_id,
            9,
            "The original record was accurate.",
        )

        self.assertEqual(result.stage, "CONTACTED")
        self.assertEqual(result.dispute_status, "dismissed")
        self.assertEqual(
            len(LeadRepository(self.db).list_history(self.lead.lead_id)),
            len(history_before),
        )
        self.assertEqual(report.status, "dismissed")
        report_history = list(
            self.db.query(ReportHistory)
            .filter(ReportHistory.report_id == report.report_id)
            .order_by(ReportHistory.history_id)
        )
        self.assertEqual(report_history[-1].action, "dismissed")
        self.assertEqual(
            report_history[-1].note,
            "The original record was accurate.",
        )

    def test_open_dispute_disables_billing_and_pauses_landlord_updates(self) -> None:
        self.lead.billing_eligible = True
        self.service.prepare_report_dispute(self.lead)
        self.db.commit()

        self.assertEqual(self.lead.stage, "NEW")
        self.assertEqual(self.lead.dispute_status, "open")
        self.assertFalse(self.lead.billing_eligible)
        with self.assertRaises(LeadStateError):
            self.service.update_for_landlord(
                self.lead.lead_id,
                8,
                "CONTACTED",
                None,
            )


if __name__ == "__main__":
    unittest.main()
