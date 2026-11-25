from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

ReportReason = Literal[
    "scam",
    "fake_listing",
    "inaccurate_info",
    "abusive",
    "misleading_price",
    "incorrect_availability",
    "unauthorized_property",
    "harassment",
    "fake_account",
    "other",
]
ReportStatus = Literal["open", "under_review", "resolved", "dismissed"]
ReportTarget = Literal["listing", "landlord", "user", "lead"]
ReportDetails = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=10, max_length=2000),
]
ReportNote = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
]


class ReportCreateRequest(BaseModel):
    target: ReportTarget
    listing_id: int | None = Field(default=None, gt=0)
    target_user_id: int | None = Field(default=None, gt=0)
    lead_id: int | None = Field(default=None, gt=0)
    reason: ReportReason
    details: ReportDetails

    @model_validator(mode="after")
    def validate_target(self) -> "ReportCreateRequest":
        if self.target in {"listing", "landlord"}:
            if (
                self.listing_id is None
                or self.target_user_id is not None
                or self.lead_id is not None
            ):
                raise ValueError(
                    "Listing and landlord reports require a listing_id only.",
                )
        elif self.target == "user":
            if (
                self.target_user_id is None
                or self.listing_id is not None
                or self.lead_id is not None
            ):
                raise ValueError("User reports require a target_user_id only.")
        elif (
            self.lead_id is None
            or self.listing_id is not None
            or self.target_user_id is not None
        ):
            raise ValueError("Lead reports require a lead_id only.")
        if self.target == "lead" and self.reason != "inaccurate_info":
            raise ValueError("Lead reports must use the inaccurate_info reason.")
        return self


class ReportResolutionRequest(BaseModel):
    note: ReportNote | None = None


class ReportNoteRequest(BaseModel):
    note: ReportNote


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: int = Field(gt=0)
    listing_id: int | None = Field(default=None, gt=0)
    target_user_id: int | None = Field(default=None, gt=0)
    lead_id: int | None = Field(default=None, gt=0)
    tenant_id: int = Field(gt=0)
    admin_id: int | None = Field(default=None, gt=0)
    reason: ReportReason
    status: ReportStatus
    details: str | None
    created_at: datetime


class ReportHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    history_id: int = Field(gt=0)
    report_id: int = Field(gt=0)
    actor_user_id: int = Field(gt=0)
    action: Literal[
        "submitted",
        "assigned",
        "resolved",
        "dismissed",
        "note_added",
    ]
    note: str | None
    created_at: datetime
