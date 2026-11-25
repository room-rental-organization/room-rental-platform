import unittest
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models.area import Area
from app.models.contact_request import ContactRequest
from app.models.conversation import Conversation
from app.models.listing import Listing
from app.models.listing_moderation import ListingModeration
from app.models.user import User
from app.repositories.contact_request_repository import (
    ContactRequestRepository,
)
from app.services.landlord_dashboard_service import (
    LandlordBusinessDashboardService,
)


class LandlordBusinessDashboardServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.session.add_all(
            [
                User(
                    user_id=user_id,
                    full_name=f"User {user_id}",
                    phone_no=f"555-01{user_id:02d}",
                    email=f"user{user_id}@example.test",
                )
                for user_id in (6, 7, 8, 9)
            ],
        )
        self.session.add(Area(area_id=1, name="Test area"))
        self.session.flush()
        self.session.add_all(
            [
                self.make_listing(10, 8, "active", "available"),
                self.make_listing(11, 8, "active", "reserved"),
                self.make_listing(12, 8, "draft", "occupied"),
                self.make_listing(20, 9, "active", "available"),
            ],
        )
        self.session.flush()
        self.session.add_all(
            [
                ListingModeration(
                    moderation_id=1,
                    listing_id=10,
                    admin_id=9,
                    decision="approved",
                    decided_at=datetime(2026, 9, 2),
                ),
                ListingModeration(
                    moderation_id=2,
                    listing_id=11,
                    admin_id=9,
                    decision="approved",
                    decided_at=datetime(2026, 9, 2),
                ),
            ],
        )
        self.session.flush()
        self.session.add_all(
            [
                ContactRequest(
                    request_id=1,
                    listing_id=10,
                    tenant_id=6,
                    status="pending",
                    requested_at=datetime(2026, 11, 15),
                ),
                ContactRequest(
                    request_id=2,
                    listing_id=10,
                    tenant_id=7,
                    status="approved",
                    requested_at=datetime(2026, 10, 2),
                ),
                ContactRequest(
                    request_id=3,
                    listing_id=11,
                    tenant_id=6,
                    status="rejected",
                    requested_at=datetime(2026, 8, 2),
                ),
                ContactRequest(
                    request_id=4,
                    listing_id=20,
                    tenant_id=6,
                    status="pending",
                    requested_at=datetime(2026, 11, 16),
                ),
            ],
        )
        self.session.flush()
        self.session.add_all(
            [
                Conversation(conversation_id=101, contact_request_id=1),
                Conversation(conversation_id=102, contact_request_id=2),
                Conversation(conversation_id=103, contact_request_id=3),
                Conversation(conversation_id=104, contact_request_id=4),
            ],
        )
        self.session.commit()
        self.service = LandlordBusinessDashboardService(self.session)

    def tearDown(self) -> None:
        self.session.close()
        self.engine.dispose()

    @staticmethod
    def make_listing(
        listing_id: int,
        landlord_id: int,
        status: str,
        availability_status: str,
    ) -> Listing:
        return Listing(
            listing_id=listing_id,
            landlord_id=landlord_id,
            area_id=1,
            title=f"Room {listing_id}",
            description="A test room.",
            room_type="single_room",
            monthly_rent=Decimal("4200.00"),
            deposit_amount=Decimal("4200.00"),
            address="Test address",
            date_available=date(2026, 11, 1),
            status=status,
            availability_status=availability_status,
            created_at=datetime(2026, 9, 1),
        )

    def test_summary_counts_only_authenticated_landlords_business_data(
        self,
    ) -> None:
        summary = self.service.get_summary(
            8,
            today=date(2026, 11, 24),
        )

        self.assertEqual(summary.total_listings, 3)
        self.assertEqual(summary.available_rooms, 1)
        self.assertEqual(summary.occupied_rooms, 1)
        self.assertEqual(summary.reserved_rooms, 1)
        self.assertEqual(summary.total_enquiries, 3)
        self.assertEqual(summary.new_enquiries, 1)
        self.assertEqual(summary.active_conversations, 2)
        self.assertEqual(
            [
                (item.listing_id, item.enquiry_count)
                for item in summary.listing_performance
            ],
            [(10, 2), (11, 1), (12, 0)],
        )
        self.assertEqual(
            [
                (item.month, item.enquiry_count)
                for item in summary.monthly_enquiries
                if item.enquiry_count > 0
            ],
            [("2026-08", 1), ("2026-10", 1), ("2026-11", 1)],
        )

    def test_enquiry_details_are_scoped_to_landlords_listings(self) -> None:
        rows = ContactRequestRepository(
            self.session,
        ).list_for_landlord_with_details(8)

        self.assertEqual(
            [row[0].request_id for row in rows],
            [1, 2, 3],
        )
        self.assertTrue(
            all(row[4] is not None for row in rows),
        )
        self.assertEqual(rows[0][3], "User 6")

    def test_summary_is_empty_for_landlord_without_business_data(self) -> None:
        summary = self.service.get_summary(
            99,
            today=date(2026, 11, 24),
        )

        self.assertEqual(summary.total_listings, 0)
        self.assertEqual(summary.available_rooms, 0)
        self.assertEqual(summary.total_enquiries, 0)
        self.assertEqual(summary.active_conversations, 0)
        self.assertEqual(summary.listing_performance, [])
        self.assertEqual(
            [month.enquiry_count for month in summary.monthly_enquiries],
            [0, 0, 0, 0, 0, 0],
        )


if __name__ == "__main__":
    unittest.main()
