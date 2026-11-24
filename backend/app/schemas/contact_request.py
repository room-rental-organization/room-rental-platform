from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class ContactRequestStatusUpdate(BaseModel):
    status: Literal["approved", "rejected", "cancelled"]


class ContactRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    request_id: int
    listing_id: int
    status: str
    requested_at: datetime


class LandlordContactRequestResponse(ContactRequestResponse):
    listing_title: str
    listing_address: str
    tenant_name: str
    conversation_id: int | None
