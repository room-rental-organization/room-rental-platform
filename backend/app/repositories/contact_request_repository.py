from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.contact_request import ContactRequest
from app.models.listing import Listing
from app.models.user import User


class ContactRequestRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, contact_request: ContactRequest) -> ContactRequest:
        self._db.add(contact_request)
        self._db.flush()
        return contact_request

    def get_pending_for_tenant_listing(
        self,
        tenant_id: int,
        listing_id: int,
    ) -> ContactRequest | None:
        statement = select(ContactRequest).where(
            ContactRequest.tenant_id == tenant_id,
            ContactRequest.listing_id == listing_id,
            ContactRequest.status == "pending",
        )
        return self._db.scalar(statement)

    def list_for_tenant(self, tenant_id: int) -> list[ContactRequest]:
        statement = (
            select(ContactRequest)
            .where(ContactRequest.tenant_id == tenant_id)
            .order_by(
                ContactRequest.requested_at.desc(),
                ContactRequest.request_id.desc(),
            )
        )
        return list(self._db.scalars(statement).all())

    def list_for_landlord(self, landlord_id: int) -> list[ContactRequest]:
        statement = (
            select(ContactRequest)
            .join(Listing, Listing.listing_id == ContactRequest.listing_id)
            .where(Listing.landlord_id == landlord_id)
            .order_by(
                ContactRequest.requested_at.desc(),
                ContactRequest.request_id.desc(),
            )
        )
        return list(self._db.scalars(statement).all())

    def list_for_landlord_with_details(
        self,
        landlord_id: int,
    ) -> list[tuple[ContactRequest, str, str, str, int | None]]:
        statement = (
            select(
                ContactRequest,
                Listing.title,
                Listing.address,
                User.full_name,
                Conversation.conversation_id,
            )
            .join(Listing, Listing.listing_id == ContactRequest.listing_id)
            .join(User, User.user_id == ContactRequest.tenant_id)
            .outerjoin(
                Conversation,
                Conversation.contact_request_id == ContactRequest.request_id,
            )
            .where(Listing.landlord_id == landlord_id)
            .order_by(
                ContactRequest.requested_at.desc(),
                ContactRequest.request_id.desc(),
            )
        )
        return list(self._db.execute(statement).all())

    def get_with_listing_landlord(
        self,
        request_id: int,
    ) -> tuple[ContactRequest, int] | None:
        statement = (
            select(ContactRequest, Listing.landlord_id)
            .join(Listing, Listing.listing_id == ContactRequest.listing_id)
            .where(ContactRequest.request_id == request_id)
        )
        result = self._db.execute(statement).one_or_none()
        if result is None:
            return None

        contact_request, landlord_id = result
        return contact_request, landlord_id
