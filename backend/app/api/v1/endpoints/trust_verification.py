import logging
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.trust_verification import (
    AccountPhoneVerificationStartRequest,
    AccountPhoneVerificationStatusResponse,
    AdminVerificationRequestResponse,
    PublicLandlordTrustResponse,
    VerificationDecisionRequest,
    VerificationHistoryResponse,
    VerificationRequestResponse,
    VerificationResubmissionRequest,
    VerificationStatus,
    VerificationSubmissionRequest,
)
from app.services.whatsapp_provider import WhatsAppProviderError
from app.services.whatsapp_service import (
    WhatsAppService,
    WhatsAppVerificationError,
)
from app.services.trust_verification_service import (
    TrustVerificationService,
    VerificationListingError,
    VerificationRateLimitError,
    VerificationRequestNotFoundError,
    VerificationSubmissionStateError,
)


logger = logging.getLogger(__name__)
router = APIRouter(tags=["trust and verification"])
landlord_dependency = require_role("landlord")
admin_dependency = require_role("admin")


def get_trust_verification_service(
    db: Session = Depends(get_db),
) -> TrustVerificationService:
    return TrustVerificationService(db)


def get_whatsapp_service(
    db: Session = Depends(get_db),
) -> WhatsAppService:
    return WhatsAppService(db)


def _raise_http_error(error: Exception, request_id: int | None = None) -> NoReturn:
    if isinstance(error, (VerificationRequestNotFoundError, VerificationListingError)):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    if isinstance(error, VerificationSubmissionStateError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    if isinstance(error, VerificationRateLimitError):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(error),
        ) from error
    logger.exception("Trust verification request failed for %s", request_id)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Trust verification is temporarily unavailable.",
    ) from error


@router.get(
    "/users/me/trust-verifications",
    response_model=list[VerificationRequestResponse],
)
def list_my_verifications(
    current_landlord: User = Depends(landlord_dependency),
    service: TrustVerificationService = Depends(
        get_trust_verification_service,
    ),
) -> list[VerificationRequestResponse]:
    try:
        return service.list_for_user(current_landlord.user_id)
    except SQLAlchemyError as exc:
        _raise_http_error(exc)


@router.get(
    "/users/me/phone-verification",
    response_model=AccountPhoneVerificationStatusResponse,
)
def get_account_phone_verification_status(
    current_landlord: User = Depends(landlord_dependency),
) -> AccountPhoneVerificationStatusResponse:
    return AccountPhoneVerificationStatusResponse(
        verified=current_landlord.phone_verified_at is not None,
    )


@router.post(
    "/users/me/phone-verification",
    status_code=status.HTTP_202_ACCEPTED,
)
def start_account_phone_verification(
    request: AccountPhoneVerificationStartRequest,
    current_landlord: User = Depends(landlord_dependency),
    service: WhatsAppService = Depends(get_whatsapp_service),
) -> dict[str, str]:
    try:
        service.start_verification(
            current_landlord.user_id,
            current_landlord.phone_no,
        )
    except WhatsAppVerificationError:
        logger.info("Account phone verification request was not eligible")
    except WhatsAppProviderError as exc:
        logger.exception("Account phone verification message could not be sent")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Phone verification is temporarily unavailable.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="The phone number on this account cannot be verified.",
        ) from exc
    except (RuntimeError, SQLAlchemyError) as exc:
        logger.exception("Account phone verification could not be started")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Phone verification is temporarily unavailable.",
        ) from exc
    return {
        "detail": (
            "If eligible, a verification message will be sent to the phone "
            "number on your account."
        ),
    }


@router.post(
    "/users/me/trust-verifications",
    response_model=VerificationRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def submit_verification(
    request: VerificationSubmissionRequest,
    current_landlord: User = Depends(landlord_dependency),
    service: TrustVerificationService = Depends(
        get_trust_verification_service,
    ),
) -> VerificationRequestResponse:
    try:
        return service.submit(current_landlord.user_id, request)
    except (
        VerificationListingError,
        VerificationSubmissionStateError,
        VerificationRateLimitError,
        SQLAlchemyError,
    ) as exc:
        _raise_http_error(exc)


@router.post(
    "/users/me/trust-verifications/{request_id}/resubmit",
    response_model=VerificationRequestResponse,
)
def resubmit_verification(
    request_id: Annotated[int, Path(gt=0)],
    request: VerificationResubmissionRequest,
    current_landlord: User = Depends(landlord_dependency),
    service: TrustVerificationService = Depends(
        get_trust_verification_service,
    ),
) -> VerificationRequestResponse:
    try:
        return service.resubmit(
            request_id,
            current_landlord.user_id,
            request,
        )
    except (
        VerificationRequestNotFoundError,
        VerificationSubmissionStateError,
        VerificationRateLimitError,
        SQLAlchemyError,
    ) as exc:
        _raise_http_error(exc, request_id)


@router.get(
    "/admin/trust-verifications",
    response_model=list[AdminVerificationRequestResponse],
)
def list_admin_verifications(
    request_status: Annotated[
        VerificationStatus | None,
        Query(alias="status"),
    ] = None,
    current_admin: User = Depends(admin_dependency),
    service: TrustVerificationService = Depends(
        get_trust_verification_service,
    ),
) -> list[AdminVerificationRequestResponse]:
    try:
        return service.list_for_admin(request_status)
    except SQLAlchemyError as exc:
        _raise_http_error(exc)


@router.get(
    "/admin/trust-verifications/{request_id}/history",
    response_model=list[VerificationHistoryResponse],
)
def get_verification_history(
    request_id: Annotated[int, Path(gt=0)],
    current_admin: User = Depends(admin_dependency),
    service: TrustVerificationService = Depends(
        get_trust_verification_service,
    ),
) -> list[VerificationHistoryResponse]:
    try:
        return [
            VerificationHistoryResponse.model_validate(entry)
            for entry in service.get_history(request_id)
        ]
    except (VerificationRequestNotFoundError, SQLAlchemyError) as exc:
        _raise_http_error(exc, request_id)


@router.post(
    "/admin/trust-verifications/{request_id}/decision",
    response_model=AdminVerificationRequestResponse,
)
def decide_verification(
    request_id: Annotated[int, Path(gt=0)],
    request: VerificationDecisionRequest,
    current_admin: User = Depends(admin_dependency),
    service: TrustVerificationService = Depends(
        get_trust_verification_service,
    ),
) -> AdminVerificationRequestResponse:
    try:
        return service.decide(
            request_id,
            current_admin.user_id,
            request,
        )
    except (
        VerificationRequestNotFoundError,
        VerificationSubmissionStateError,
        SQLAlchemyError,
    ) as exc:
        _raise_http_error(exc, request_id)


@router.get(
    "/listings/{listing_id}/trust",
    response_model=PublicLandlordTrustResponse,
)
def get_owned_listing_trust(
    listing_id: Annotated[int, Path(gt=0)],
    response: Response,
    current_landlord: User = Depends(landlord_dependency),
    service: TrustVerificationService = Depends(
        get_trust_verification_service,
    ),
) -> PublicLandlordTrustResponse:
    try:
        trust = service.trust_for_owned_listing(listing_id, current_landlord.user_id)
    except SQLAlchemyError as exc:
        _raise_http_error(exc)
    if trust is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Listing not found.",
        )
    response.headers["Cache-Control"] = "no-store"
    return trust
