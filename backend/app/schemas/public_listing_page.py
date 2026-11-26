from pydantic import BaseModel
from app.schemas.listing import PublicListingResponse


class PublicListingPage(BaseModel):
    items: list[PublicListingResponse]
    next_offset: int | None
