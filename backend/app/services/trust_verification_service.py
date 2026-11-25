from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.trust_verification import (
    TrustVerificationHistory,
    TrustVerificationRequest,
)
from app.models.user import User
from app.repositories.listing_repository import ListingRepository
from app.repositories.trust_verification_repository import (
    TrustVerificationRepository,
)
from app.schemas.trust_verification import (
    AdminVerificationRequestResponse,
    PublicLandlordTrustResponse,
    PublicTrustStatus,
    VerificationDecisionRequest,
    VerificationRequestResponse,
    VerificationResubmissionRequest,
    VerificationSubmissionRequest,
)


class TrustVerificationError(Exception):
    pass


class VerificationRequestNotFoundError(TrustVerificationError):
    pass


class VerificationSubmissionStateError(TrustVerificationError):
    pass


class VerificationRateLimitError(TrustVerificationError):
    pass


class VerificationListingError(TrustVerificationError):
    pass


class TrustVerificationService:
    PENDING = "pending"
    NEEDS_INFORMATION = "needs_information"
    APPROVED = "approved"
    REJECTED = "rejected"
    MAX_SUBMISSIONS_PER_DAY = 5
    PROPERTY_AUTHORIZATION_VALIDITY = timedelta(days=365)
    ACTIVE_REQUEST_CONSTRAINTS = {
        "uq_trust_verification_active_profile",
        "uq_trust_verification_active_listing",
    }

    def __init__(self, db: Session) -> None:
        self._db = db
        self._requests = TrustVerificationRepository(db)
        self._listings = ListingRepository(db)
        self._max_submissions_per_day = (
            get_settings().trust_verification_max_submissions_per_day
        )

    def list_for_user(self, user_id: int) -> list[VerificationRequestResponse]:
        return [
            VerificationRequestResponse.model_validate(request)
            for request in self._requests.list_for_user(user_id)
        ]

    def submit(
        self,
        user_id: int,
        submission: VerificationSubmissionRequest,
    ) -> VerificationRequestResponse:
        if submission.verification_type == "property_authorization":
            listing = self._listings.get_owned(
                submission.listing_id or 0,
                user_id,
            )
            if listing is None:
                raise VerificationListingError(
                    "The listing does not belong to this landlord.",
                )
            if listing.status in {"removed", "closed"}:
                raise VerificationListingError(
                    "This listing is not eligible for authorization review.",
                )

        latest = self._requests.latest_for_subject(
            user_id,
            submission.verification_type,
            submission.listing_id,
        )
        if latest is not None and latest.status in {
            self.PENDING,
            self.NEEDS_INFORMATION,
        }:
            raise VerificationSubmissionStateError(
                "A verification request is already awaiting action.",
            )

        now = self._now()
        self._enforce_submission_limit(user_id, now)
        request = TrustVerificationRequest(
            user_id=user_id,
            verification_type=submission.verification_type,
            listing_id=submission.listing_id,
            status=self.PENDING,
            evidence_statement=submission.evidence_statement,
        )
        try:
            self._requests.add(request)
            self._requests.add_history(
                request.request_id,
                user_id,
                "submitted",
            )
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            self._raise_duplicate_submission(exc)
        except SQLAlchemyError:
            self._db.rollback()
            raise
        return VerificationRequestResponse.model_validate(request)

    def resubmit(
        self,
        request_id: int,
        user_id: int,
        submission: VerificationResubmissionRequest,
    ) -> VerificationRequestResponse:
        request = self._requests.get_for_user(
            request_id,
            user_id,
            for_update=True,
        )
        if request is None:
            raise VerificationRequestNotFoundError(
                "Verification request does not exist.",
            )
        if request.status not in {self.REJECTED, self.NEEDS_INFORMATION}:
            raise VerificationSubmissionStateError(
                "Only rejected or information-requested submissions can be resubmitted.",
            )

        now = self._now()
        self._enforce_submission_limit(user_id, now)
        request.evidence_statement = submission.evidence_statement
        request.status = self.PENDING
        request.decision_reason = None
        request.expires_at = None
        request.submitted_at = now
        request.updated_at = now
        self._requests.add_history(
            request.request_id,
            user_id,
            "resubmitted",
        )
        self._commit()
        return VerificationRequestResponse.model_validate(request)

    def list_for_admin(
        self,
        status_filter: str | None = None,
    ) -> list[AdminVerificationRequestResponse]:
        return [
            AdminVerificationRequestResponse.model_validate(request)
            for request in self._requests.list_for_admin(status_filter)
        ]

    def get_history(
        self,
        request_id: int,
    ) -> list[TrustVerificationHistory]:
        if self._requests.get_for_admin(request_id) is None:
            raise VerificationRequestNotFoundError(
                "Verification request does not exist.",
            )
        return self._requests.list_history(request_id)

    def decide(
        self,
        request_id: int,
        admin_id: int,
        decision: VerificationDecisionRequest,
    ) -> AdminVerificationRequestResponse:
        request = self._requests.get_for_admin(request_id, for_update=True)
        if request is None:
            raise VerificationRequestNotFoundError(
                "Verification request does not exist.",
            )
        if request.status != self.PENDING:
            raise VerificationSubmissionStateError(
                "Only pending verification requests can be reviewed.",
            )

        action_map = {
            "approve": (self.APPROVED, "approved"),
            "reject": (self.REJECTED, "rejected"),
            "request_information": (
                self.NEEDS_INFORMATION,
                "information_requested",
            ),
        }
        decision_time = self._now()
        request.status, action = action_map[decision.action]
        request.decision_reason = (
            decision.reason.strip()
            if decision.reason is not None
            else None
        )
        if (
            decision.action == "approve"
            and request.verification_type == "property_authorization"
        ):
            request.expires_at = (
                decision_time + self.PROPERTY_AUTHORIZATION_VALIDITY
            )
        else:
            request.expires_at = None
        request.updated_at = decision_time
        self._requests.add_history(
            request.request_id,
            admin_id,
            action,
            request.decision_reason,
        )
        self._commit()
        return AdminVerificationRequestResponse.model_validate(request)

    def trust_for_owned_listing(
        self,
        listing_id: int,
        landlord_id: int,
    ) -> PublicLandlordTrustResponse | None:
        listing = self._listings.get_owned(listing_id, landlord_id)
        if listing is None:
            return None
        landlord = self._db.get(User, listing.landlord_id)
        if landlord is None:
            return None

        identity = self._requests.latest_for_subject(
            landlord.user_id,
            "identity",
        )
        property_authorization = self._requests.latest_for_subject(
            landlord.user_id,
            "property_authorization",
            listing_id,
        )
        identity_status = self._public_status(identity)
        property_status = self._public_status(property_authorization)
        return PublicLandlordTrustResponse(
            phone_verified=landlord.phone_verified_at is not None,
            identity_status=identity_status,
            property_authorization_status=property_status,
            listing_verification_status=property_status,
            active_listing_count=self._requests.count_active_listings(
                landlord.user_id,
            ),
            account_created_at=landlord.created_at,
        )

    def _enforce_submission_limit(self, user_id: int, now: datetime) -> None:
        if (
            self._requests.count_submissions_since(
                user_id,
                now - timedelta(days=1),
            )
            >= self._max_submissions_per_day
        ):
            raise VerificationRateLimitError(
                "Daily verification submission limit reached. Try again later.",
            )

    def _commit(self) -> None:
        try:
            self._db.commit()
        except IntegrityError as exc:
            self._db.rollback()
            self._raise_duplicate_submission(exc)
        except SQLAlchemyError:
            self._db.rollback()
            raise

    @classmethod
    def _raise_duplicate_submission(cls, error: IntegrityError) -> None:
        constraint_name = getattr(
            getattr(error.orig, "diag", None),
            "constraint_name",
            None,
        )
        if constraint_name in cls.ACTIVE_REQUEST_CONSTRAINTS:
            raise VerificationSubmissionStateError(
                "A verification request is already awaiting action.",
            ) from error
        raise error

    @classmethod
    def _public_status(
        cls,
        request: TrustVerificationRequest | None,
    ) -> PublicTrustStatus:
        if request is None:
            return "unverified"
        if request.status == cls.APPROVED:
            if request.expires_at is None or request.expires_at > cls._now():
                return "verified"
            return "unverified"
        if request.status in {cls.PENDING, cls.NEEDS_INFORMATION}:
            return "under_review"
        return "unverified"

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)
