import logging
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.listing_repository import ListingRepository
from app.schemas.listing import PublicListingResponse
from app.schemas.location import PublicListingLocationResponse
from app.services.google_places import GooglePlacesError
from app.services.listing_service import ListingService
from app.schemas.public_listing_page import PublicListingPage
from app.services.public_listing_reads import PublicListingReads, PublicReadService
from app.services.public_cache import get_public_cache


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/listings", tags=["listings"])


def get_listing_service(db: Session = Depends(get_db)) -> ListingService:
    # Only HTTP public reads receive this adapter. Business services stay uncached.
    return PublicReadService(ListingRepository(db), get_public_cache())


@router.get('/search', response_model=PublicListingPage)
def search_public_listings(
    offset: int = Query(default=0, ge=0, le=100000),
    limit: int = Query(default=8, ge=1, le=50),
    search: str = Query(default='', max_length=150),
    room_type: Literal['', 'single_room', 'shared_room', 'bachelor_flat', 'self_contained'] = '',
    minimum_rent: Decimal | None = Query(default=None, ge=0, le=99999999),
    maximum_rent: Decimal | None = Query(default=None, ge=0, le=99999999),
    amenity: list[str] = Query(default=[], max_length=50),
    available_by: date | None = None,
    sort: Literal['recent', 'rent_asc'] = 'recent',
    db: Session = Depends(get_db),
) -> PublicListingPage:
    if minimum_rent is not None and maximum_rent is not None and minimum_rent > maximum_rent:
        raise HTTPException(status_code=422, detail='Minimum rent must not exceed maximum rent.')
    try:
        return PublicListingReads(ListingRepository(db), get_public_cache()).page(
            offset=offset, limit=limit, search=search.strip().lower(), room_type=room_type,
            minimum_rent=minimum_rent, maximum_rent=maximum_rent,
            amenities=tuple(sorted(set(amenity))), available_by=available_by, sort=sort)
    except SQLAlchemyError as exc:
        logger.error('Public listing page query failed')
        raise HTTPException(status_code=503, detail='Listing data is temporarily unavailable.') from exc


@router.get("", response_model=list[PublicListingResponse])
def list_public_listings(
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    radius_km: int | None = Query(default=None, ge=5, le=10),
    service: ListingService = Depends(get_listing_service),
) -> list[PublicListingResponse]:
    try:
        if latitude is None and longitude is None and radius_km is None:
            return service.list_public_listings()
        if latitude is None or longitude is None or radius_km is None:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Latitude, longitude, and radius_km must be provided together."
                ),
            )
        if radius_km not in {5, 10}:
            raise HTTPException(
                status_code=422,
                detail="radius_km must be 5 or 10.",
            )
        return service.list_public_listings(
            center=(latitude, longitude),
            radius_km=radius_km,
        )
    except GooglePlacesError as exc:
        logger.exception("Failed to resolve listings for radius search")
        raise HTTPException(
            status_code=503,
            detail="Map locations are temporarily unavailable for radius search.",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception("Failed to retrieve public listings")
        raise HTTPException(
            status_code=503,
            detail="Listing data is temporarily unavailable.",
        ) from exc


@router.get("/{listing_id}", response_model=PublicListingResponse)
def get_public_listing(
    listing_id: int = Path(gt=0),
    service: ListingService = Depends(get_listing_service),
) -> PublicListingResponse:
    try:
        listing = service.get_public_listing(listing_id)
    except SQLAlchemyError as exc:
        logger.exception("Failed to retrieve public listing %s", listing_id)
        raise HTTPException(
            status_code=503,
            detail="Listing data is temporarily unavailable.",
        ) from exc

    if listing is None:
        raise HTTPException(status_code=404, detail="Listing not found.")

    return listing


@router.get(
    "/{listing_id}/map-location",
    response_model=PublicListingLocationResponse,
)
def get_public_listing_map_location(
    response: Response,
    listing_id: int = Path(gt=0),
    service: ListingService = Depends(get_listing_service),
) -> PublicListingLocationResponse:
    response.headers["Cache-Control"] = "no-store"
    try:
        location = service.get_public_listing_location(listing_id)
    except GooglePlacesError as exc:
        logger.exception("Failed to resolve public map location")
        raise HTTPException(
            status_code=503,
            detail="Map location is temporarily unavailable.",
        ) from exc
    except SQLAlchemyError as exc:
        logger.exception(
            "Failed to retrieve map location for listing %s",
            listing_id,
        )
        raise HTTPException(
            status_code=503,
            detail="Listing data is temporarily unavailable.",
        ) from exc

    if location is None:
        raise HTTPException(status_code=404, detail="Map location not found.")

    return location
