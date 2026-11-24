import logging
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import require_role
from app.db.session import get_db
from app.models.user import User
from app.schemas.lead import (
    AdminLeadDisputeResponse,
    AdminLeadDetailResponse,
    LandlordLeadDetailResponse,
    LandlordLeadResponse,
    LeadDismissRequest,
    LeadConversionSummary,
    LeadResolutionRequest,
    LeadRentedRequest,
    LeadStage,
    LeadStageUpdateRequest,
    LeadUnsuccessfulRequest,
    TenantLeadDetailResponse,
    TenantLeadResponse,
)
from app.services.lead_service import (
    LeadNotFoundError,
    LeadService,
    LeadStateError,
)


logger = logging.getLogger(__name__)
router = APIRouter(tags=["lead conversion"])
landlord_dependency = require_role("landlord")
tenant_dependency = require_role("tenant")
admin_dependency = require_role("admin")


def get_lead_service(
    db: Session = Depends(get_db),
) -> LeadService:
    return LeadService(db)


def _raise_lead_http_error(
    error: Exception,
    lead_id: int | None = None,
) -> NoReturn:
    if isinstance(error, LeadNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    if isinstance(error, LeadStateError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    logger.exception("Lead request failed for %s", lead_id)
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Lead information is temporarily unavailable.",
    ) from error


@router.get(
    "/users/me/leads",
    response_model=list[LandlordLeadResponse],
)
def list_my_leads(
    current_landlord: User = Depends(landlord_dependency),
    service: LeadService = Depends(get_lead_service),
) -> list[LandlordLeadResponse]:
    try:
        return service.list_for_landlord(current_landlord.user_id)
    except SQLAlchemyError as exc:
        _raise_lead_http_error(exc)


@router.get(
    "/users/me/leads/summary",
    response_model=LeadConversionSummary,
)
def get_my_lead_summary(
    current_landlord: User = Depends(landlord_dependency),
    service: LeadService = Depends(get_lead_service),
) -> LeadConversionSummary:
    try:
        return service.summary_for_landlord(current_landlord.user_id)
    except SQLAlchemyError as exc:
        _raise_lead_http_error(exc)


@router.get(
    "/users/me/leads/{lead_id}",
    response_model=LandlordLeadDetailResponse,
)
def get_my_lead(
    lead_id: Annotated[int, Path(gt=0)],
    current_landlord: User = Depends(landlord_dependency),
    service: LeadService = Depends(get_lead_service),
) -> LandlordLeadDetailResponse:
    try:
        return service.get_for_landlord(lead_id, current_landlord.user_id)
    except (LeadNotFoundError, SQLAlchemyError) as exc:
        _raise_lead_http_error(exc, lead_id)


@router.patch(
    "/users/me/leads/{lead_id}/stage",
    response_model=LandlordLeadDetailResponse,
)
def update_lead_stage(
    changes: LeadStageUpdateRequest,
    lead_id: Annotated[int, Path(gt=0)],
    current_landlord: User = Depends(landlord_dependency),
    service: LeadService = Depends(get_lead_service),
) -> LandlordLeadDetailResponse:
    try:
        return service.update_for_landlord(
            lead_id,
            current_landlord.user_id,
            changes.stage,
            changes.note,
        )
    except (LeadNotFoundError, LeadStateError, SQLAlchemyError) as exc:
        _raise_lead_http_error(exc, lead_id)


@router.post(
    "/users/me/leads/{lead_id}/rental",
    response_model=LandlordLeadDetailResponse,
)
def record_rented_lead(
    request: LeadRentedRequest,
    lead_id: Annotated[int, Path(gt=0)],
    current_landlord: User = Depends(landlord_dependency),
    service: LeadService = Depends(get_lead_service),
) -> LandlordLeadDetailResponse:
    try:
        return service.record_rented(
            lead_id,
            current_landlord.user_id,
            request.note,
        )
    except (LeadNotFoundError, LeadStateError, SQLAlchemyError) as exc:
        _raise_lead_http_error(exc, lead_id)


@router.post(
    "/users/me/leads/{lead_id}/unsuccessful",
    response_model=LandlordLeadDetailResponse,
)
def record_unsuccessful_lead(
    request: LeadUnsuccessfulRequest,
    lead_id: Annotated[int, Path(gt=0)],
    current_landlord: User = Depends(landlord_dependency),
    service: LeadService = Depends(get_lead_service),
) -> LandlordLeadDetailResponse:
    try:
        return service.record_unsuccessful(
            lead_id,
            current_landlord.user_id,
            request.reason,
        )
    except (LeadNotFoundError, LeadStateError, SQLAlchemyError) as exc:
        _raise_lead_http_error(exc, lead_id)


@router.get(
    "/users/me/lead-enquiries",
    response_model=list[TenantLeadResponse],
)
def list_my_lead_enquiries(
    current_tenant: User = Depends(tenant_dependency),
    service: LeadService = Depends(get_lead_service),
) -> list[TenantLeadResponse]:
    try:
        return service.list_for_tenant(current_tenant.user_id)
    except SQLAlchemyError as exc:
        _raise_lead_http_error(exc)


@router.get(
    "/users/me/lead-enquiries/{lead_id}",
    response_model=TenantLeadDetailResponse,
)
def get_my_lead_enquiry(
    lead_id: Annotated[int, Path(gt=0)],
    current_tenant: User = Depends(tenant_dependency),
    service: LeadService = Depends(get_lead_service),
) -> TenantLeadDetailResponse:
    try:
        return service.get_for_tenant(lead_id, current_tenant.user_id)
    except (LeadNotFoundError, SQLAlchemyError) as exc:
        _raise_lead_http_error(exc, lead_id)


@router.get(
    "/admin/leads",
    response_model=list[LandlordLeadResponse],
    dependencies=[Depends(admin_dependency)],
)
def list_admin_leads(
    stage: Annotated[LeadStage | None, Query()] = None,
    service: LeadService = Depends(get_lead_service),
) -> list[LandlordLeadResponse]:
    try:
        return service.list_for_admin(stage)
    except SQLAlchemyError as exc:
        _raise_lead_http_error(exc)


@router.get(
    "/admin/lead-disputes",
    response_model=list[AdminLeadDisputeResponse],
    dependencies=[Depends(admin_dependency)],
)
def list_admin_lead_disputes(
    service: LeadService = Depends(get_lead_service),
) -> list[AdminLeadDisputeResponse]:
    try:
        return service.list_open_disputes_for_admin()
    except SQLAlchemyError as exc:
        _raise_lead_http_error(exc)


@router.get(
    "/admin/leads/{lead_id}",
    response_model=AdminLeadDetailResponse,
    dependencies=[Depends(admin_dependency)],
)
def get_admin_lead(
    lead_id: Annotated[int, Path(gt=0)],
    service: LeadService = Depends(get_lead_service),
) -> AdminLeadDetailResponse:
    try:
        return service.get_for_admin(lead_id)
    except (LeadNotFoundError, SQLAlchemyError) as exc:
        _raise_lead_http_error(exc, lead_id)


@router.patch(
    "/admin/leads/{lead_id}/stage",
    response_model=AdminLeadDetailResponse,
)
def resolve_admin_lead(
    request: LeadResolutionRequest,
    lead_id: Annotated[int, Path(gt=0)],
    current_admin: User = Depends(admin_dependency),
    service: LeadService = Depends(get_lead_service),
) -> AdminLeadDetailResponse:
    try:
        return service.resolve_dispute(
            lead_id,
            current_admin.user_id,
            request.stage,
            request.note,
        )
    except (LeadNotFoundError, LeadStateError, SQLAlchemyError) as exc:
        _raise_lead_http_error(exc, lead_id)


@router.post(
    "/admin/leads/{lead_id}/dismiss-dispute",
    response_model=AdminLeadDetailResponse,
)
def dismiss_admin_lead_dispute(
    request: LeadDismissRequest,
    lead_id: Annotated[int, Path(gt=0)],
    current_admin: User = Depends(admin_dependency),
    service: LeadService = Depends(get_lead_service),
) -> AdminLeadDetailResponse:
    try:
        return service.dismiss_dispute(
            lead_id,
            current_admin.user_id,
            request.reason,
        )
    except (LeadNotFoundError, LeadStateError, SQLAlchemyError) as exc:
        _raise_lead_http_error(exc, lead_id)
