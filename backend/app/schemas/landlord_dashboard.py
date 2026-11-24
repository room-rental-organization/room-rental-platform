from pydantic import BaseModel


class ListingEnquiryCount(BaseModel):
    listing_id: int
    enquiry_count: int


class MonthlyEnquiryCount(BaseModel):
    month: str
    enquiry_count: int


class LandlordBusinessDashboardResponse(BaseModel):
    total_listings: int
    available_rooms: int
    occupied_rooms: int
    reserved_rooms: int
    total_enquiries: int
    new_enquiries: int
    active_conversations: int
    listing_performance: list[ListingEnquiryCount]
    monthly_enquiries: list[MonthlyEnquiryCount]
