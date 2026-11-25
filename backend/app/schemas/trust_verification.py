from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


VerificationType = Literal["identity", "property_authorization"]
VerificationStatus = Literal[
    "pending",
    "needs_information",
    "approved",
    "rejected",
]
class AccountPhoneVerificationStartRequest(BaseModel):
    consent: Literal[True]


class AccountPhoneVerificationStatusResponse(BaseModel):
    verified: bool


EvidenceStatement = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=10, max_length=1000),
]
DecisionReason = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
]


class VerificationSubmissionRequest(BaseModel):
    verification_type: VerificationType
    listing_id: int | None = Field(default=None, gt=0)
    evidence_statement: EvidenceStatement

    @model_validator(mode="after")
    def validate_subject(self) -> "VerificationSubmissionRequest":
        if self.verification_type == "identity" and self.listing_id is not None:
            raise ValueError("Identity verification cannot reference a listing.")
        if (
            self.verification_type == "property_authorization"
            and self.listing_id is None
        ):
            raise ValueError("Property authorization requires a listing.")
        return self


class VerificationResubmissionRequest(BaseModel):
    evidence_statement: EvidenceStatement


class VerificationDecisionRequest(BaseModel):
    action: Literal["approve", "reject", "request_information"]
    reason: DecisionReason | None = None

    @model_validator(mode="after")
    def require_decision_note(self) -> "VerificationDecisionRequest":
        if self.reason is None:
            raise ValueError("A decision note is required.")
        return self


class VerificationRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: int
    verification_type: VerificationType
    listing_id: int | None
    status: VerificationStatus
    decision_reason: str | None
    expires_at: datetime | None
    submitted_at: datetime
    updated_at: datetime


class AdminVerificationRequestResponse(VerificationRequestResponse):
    user_id: int
    evidence_statement: str


class VerificationHistoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    history_id: int
    request_id: int
    actor_user_id: int
    action: Literal[
        "submitted",
        "resubmitted",
        "approved",
        "rejected",
        "information_requested",
    ]
    note: str | None
    created_at: datetime


PublicTrustStatus = Literal["verified", "under_review", "unverified"]


class PublicLandlordTrustResponse(BaseModel):
    phone_verified: bool
    identity_status: PublicTrustStatus
    property_authorization_status: PublicTrustStatus
    listing_verification_status: PublicTrustStatus
    active_listing_count: int = Field(ge=0)
    account_created_at: datetime
