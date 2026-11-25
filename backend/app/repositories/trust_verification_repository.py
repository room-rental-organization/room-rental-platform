from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.listing import Listing
from app.models.trust_verification import (
    TrustVerificationHistory,
    TrustVerificationRequest,
)


class TrustVerificationRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, request: TrustVerificationRequest) -> TrustVerificationRequest:
        self._db.add(request)
        self._db.flush()
        return request

    def add_history(
        self,
        request_id: int,
        actor_user_id: int,
        action: str,
        note: str | None = None,
    ) -> TrustVerificationHistory:
        history = TrustVerificationHistory(
            request_id=request_id,
            actor_user_id=actor_user_id,
            action=action,
            note=note,
        )
        self._db.add(history)
        self._db.flush()
        return history

    def list_for_user(self, user_id: int) -> list[TrustVerificationRequest]:
        statement = (
            select(TrustVerificationRequest)
            .where(TrustVerificationRequest.user_id == user_id)
            .order_by(
                TrustVerificationRequest.submitted_at.desc(),
                TrustVerificationRequest.request_id.desc(),
            )
        )
        return list(self._db.scalars(statement).all())

    def latest_for_subject(
        self,
        user_id: int,
        verification_type: str,
        listing_id: int | None = None,
    ) -> TrustVerificationRequest | None:
        statement = select(TrustVerificationRequest).where(
            TrustVerificationRequest.user_id == user_id,
            TrustVerificationRequest.verification_type == verification_type,
        )
        if listing_id is None:
            statement = statement.where(
                TrustVerificationRequest.listing_id.is_(None),
            )
        else:
            statement = statement.where(
                TrustVerificationRequest.listing_id == listing_id,
            )
        statement = statement.order_by(
            TrustVerificationRequest.submitted_at.desc(),
            TrustVerificationRequest.request_id.desc(),
        )
        return self._db.scalar(statement)

    def get_for_user(
        self,
        request_id: int,
        user_id: int,
        *,
        for_update: bool = False,
    ) -> TrustVerificationRequest | None:
        statement = select(TrustVerificationRequest).where(
            TrustVerificationRequest.request_id == request_id,
            TrustVerificationRequest.user_id == user_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self._db.scalar(statement)

    def get_for_admin(
        self,
        request_id: int,
        *,
        for_update: bool = False,
    ) -> TrustVerificationRequest | None:
        statement = select(TrustVerificationRequest).where(
            TrustVerificationRequest.request_id == request_id,
        )
        if for_update:
            statement = statement.with_for_update()
        return self._db.scalar(statement)

    def list_for_admin(
        self,
        status_filter: str | None = None,
    ) -> list[TrustVerificationRequest]:
        statement = select(TrustVerificationRequest)
        if status_filter is not None:
            statement = statement.where(
                TrustVerificationRequest.status == status_filter,
            )
        statement = statement.order_by(
            TrustVerificationRequest.submitted_at,
            TrustVerificationRequest.request_id,
        )
        return list(self._db.scalars(statement).all())

    def list_history(self, request_id: int) -> list[TrustVerificationHistory]:
        statement = (
            select(TrustVerificationHistory)
            .where(TrustVerificationHistory.request_id == request_id)
            .order_by(
                TrustVerificationHistory.created_at,
                TrustVerificationHistory.history_id,
            )
        )
        return list(self._db.scalars(statement).all())

    def count_submissions_since(
        self,
        user_id: int,
        since: datetime,
    ) -> int:
        statement = select(func.count()).select_from(
            TrustVerificationHistory,
        ).join(
            TrustVerificationRequest,
            TrustVerificationRequest.request_id
            == TrustVerificationHistory.request_id,
        ).where(
            TrustVerificationRequest.user_id == user_id,
            TrustVerificationHistory.action.in_(("submitted", "resubmitted")),
            TrustVerificationHistory.created_at >= since,
        )
        return int(self._db.scalar(statement) or 0)

    def get_listing(self, listing_id: int) -> Listing | None:
        return self._db.get(Listing, listing_id)

    def count_active_listings(self, user_id: int) -> int:
        statement = select(func.count()).select_from(Listing).where(
            Listing.landlord_id == user_id,
            Listing.status == "active",
        )
        return int(self._db.scalar(statement) or 0)
