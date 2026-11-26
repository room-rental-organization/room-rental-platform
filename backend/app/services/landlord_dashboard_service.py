from collections import Counter
from datetime import date

from sqlalchemy.orm import Session

from app.repositories.contact_request_repository import (
    ContactRequestRepository,
)
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.listing_repository import ListingRepository
from app.schemas.landlord_dashboard import (
    LandlordBusinessDashboardResponse,
    ListingEnquiryCount,
    MonthlyEnquiryCount,
)


class LandlordBusinessDashboardService:
    def __init__(self, db: Session) -> None:
        self._listings = ListingRepository(db)
        self._requests = ContactRequestRepository(db)
        self._conversations = ConversationRepository(db)

    def get_summary(
        self,
        landlord_id: int,
        *,
        today: date | None = None,
    ) -> LandlordBusinessDashboardResponse:
        listings = self._listings.dashboard_rows(landlord_id)
        # Scalar projections avoid loading room descriptions, photos and amenities
        # through ContactRequest.listing just to count enquiries.
        requests = self._requests.dashboard_rows(landlord_id)
        active_listing_ids = [
            listing.listing_id
            for listing in listings
            if listing.status == "active"
            and listing.availability_status == "available"
        ]
        latest_decisions = self._listings.get_latest_moderation_decisions(
            active_listing_ids,
        )
        enquiries_by_listing = Counter(
            request.listing_id for request in requests
        )
        months = self._last_six_months(today or date.today())
        monthly_counts = Counter(
            request.requested_at.strftime("%Y-%m")
            for request in requests
            if request.requested_at.strftime("%Y-%m") in months
        )

        return LandlordBusinessDashboardResponse(
            total_listings=len(listings),
            available_rooms=sum(
                listing.status == "active"
                and listing.availability_status == "available"
                and latest_decisions.get(listing.listing_id) == "approved"
                for listing in listings
            ),
            occupied_rooms=sum(
                listing.availability_status == "occupied"
                for listing in listings
            ),
            reserved_rooms=sum(
                listing.availability_status == "reserved"
                for listing in listings
            ),
            total_enquiries=len(requests),
            new_enquiries=sum(
                request.status == "pending" for request in requests
            ),
            active_conversations=self._conversations.count_open_for_landlord(
                landlord_id,
            ),
            listing_performance=[
                ListingEnquiryCount(
                    listing_id=listing.listing_id,
                    enquiry_count=enquiries_by_listing[listing.listing_id],
                )
                for listing in sorted(
                    listings,
                    key=lambda item: (
                        -enquiries_by_listing[item.listing_id],
                        item.listing_id,
                    ),
                )
            ],
            monthly_enquiries=[
                MonthlyEnquiryCount(
                    month=month,
                    enquiry_count=monthly_counts[month],
                )
                for month in months
            ],
        )

    @staticmethod
    def _last_six_months(today: date) -> list[str]:
        current_month = today.year * 12 + today.month - 1
        return [
            f"{month_index // 12:04d}-{month_index % 12 + 1:02d}"
            for month_index in range(current_month - 5, current_month + 1)
        ]
