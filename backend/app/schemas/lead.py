from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    AliasChoices,
    AliasPath,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
)

from app.schemas.report import ReportHistoryResponse, ReportReason, ReportStatus


LeadStage = Literal[
    "NEW",
    "CONTACTED",
    "VIEWING_SCHEDULED",
    "VIEWING_COMPLETED",
    "INTERESTED",
    "RENTED",
    "UNSUCCESSFUL",
]
LeadHistoryStage = Literal[
    "NEW",
    "CONTACTED",
    "VIEWING_SCHEDULED",
    "VIEWING_COMPLETED",
    "INTERESTED",
    "RENTED",
    "UNSUCCESSFUL",
    "DISPUTED",
]
LeadDisputeStatus = Literal["none", "open", "resolved", "dismissed"]
LeadResolutionStage = Literal[
    "NEW",
    "CONTACTED",
    "VIEWING_SCHEDULED",
    "VIEWING_COMPLETED",
    "INTERESTED",
    "RENTED",
    "UNSUCCESSFUL",
]
LeadNote = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]


class LeadStageUpdateRequest(BaseModel):
    stage: LeadStage
    note: LeadNote | None = None


class LeadRentedRequest(BaseModel):
    note: LeadNote | None = None


class LeadUnsuccessfulRequest(BaseModel):
    reason: LeadNote


class LeadResolutionRequest(BaseModel):
    stage: LeadResolutionStage
    note: LeadNote


class LeadDismissRequest(BaseModel):
    reason: LeadNote


class LeadStageHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    history_id: int
    from_stage: LeadHistoryStage | None
    to_stage: LeadHistoryStage
    actor_user_id: int
    changed_at: datetime
    note: str | None


class TenantLeadStageHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    history_id: int
    from_stage: LeadHistoryStage | None
    to_stage: LeadHistoryStage
    changed_at: datetime


class LandlordLeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lead_id: int
    contact_request_id: int
    tenant_id: int
    landlord_id: int
    listing_id: int
    listing_title: str | None = Field(
        default=None,
        validation_alias=AliasChoices("listing_title", AliasPath("listing", "title")),
    )
    tenant_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("tenant_name", AliasPath("tenant", "full_name")),
    )
    landlord_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("landlord_name", AliasPath("landlord", "full_name")),
    )
    stage: LeadStage
    dispute_status: LeadDisputeStatus
    rented_at: datetime | None
    unsuccessful_reason: str | None
    created_at: datetime
    updated_at: datetime


class LandlordLeadDetailResponse(LandlordLeadResponse):
    history: list[LeadStageHistoryResponse]


class TenantLeadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lead_id: int
    contact_request_id: int
    listing_id: int
    listing_title: str
    listing_address: str
    stage: LeadStage
    dispute_status: LeadDisputeStatus
    rented_at: datetime | None
    created_at: datetime
    updated_at: datetime


class TenantLeadDetailResponse(TenantLeadResponse):
    history: list[TenantLeadStageHistoryResponse]


class AdminLeadDetailResponse(LandlordLeadResponse):
    history: list[LeadStageHistoryResponse]


class AdminLeadDisputeResponse(BaseModel):
    lead_id: int
    contact_request_id: int
    tenant_id: int
    tenant_name: str
    landlord_id: int
    landlord_name: str
    listing_id: int
    listing_title: str
    listing_address: str
    stage: LeadStage
    dispute_status: LeadDisputeStatus
    rented_at: datetime | None
    unsuccessful_reason: str | None
    created_at: datetime
    updated_at: datetime
    report_id: int
    report_status: ReportStatus
    report_reason: ReportReason
    report_details: str | None
    report_created_at: datetime
    history: list[LeadStageHistoryResponse]
    report_history: list[ReportHistoryResponse]


class LeadStageCounts(BaseModel):
    new: int = Field(ge=0)
    contacted: int = Field(ge=0)
    viewing_scheduled: int = Field(ge=0)
    viewing_completed: int = Field(ge=0)
    interested: int = Field(ge=0)
    rented: int = Field(ge=0)
    unsuccessful: int = Field(ge=0)
    disputed: int = Field(ge=0)


class LeadConversionSummary(BaseModel):
    total_leads: int = Field(ge=0)
    closed_leads: int = Field(ge=0)
    conversion_rate: float = Field(ge=0, le=100)
    stages: LeadStageCounts
