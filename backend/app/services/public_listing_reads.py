"""Cache-aside read projection; never used to authorize a write."""
from pydantic import TypeAdapter
from app.repositories.listing_repository import ListingRepository
from app.schemas.public_listing_page import PublicListingPage
from app.schemas.listing import PublicListingResponse
from app.services.listing_service import ListingService
from app.services.public_cache import PublicCache


class PublicListingReads:
    def __init__(self, repository: ListingRepository, cache: PublicCache) -> None:
        self.repository, self.cache = repository, cache

    def page(self, **filters) -> PublicListingPage:
        key = ('listing-page-v1', tuple(sorted(filters.items())))
        def load():
            limit = filters['limit']
            rows = self.repository.public_page(**{**filters, 'limit': limit + 1})
            covers = self.repository.cover_photos([row.listing_id for row in rows[:limit]])
            items = []
            for row in rows[:limit]:
                item = ListingService._to_public_response(row, cover_photos=(
                    [covers[row.listing_id]] if row.listing_id in covers else []))
                # Cards need a preview and cover image; detail stays a separate projection.
                items.append(item.model_copy(update={'description': item.description[:240],
                                                     'photos': item.photos[:1]}))
            return PublicListingPage(items=items, next_offset=(
                filters['offset'] + limit if len(rows) > limit else None)).model_dump_json().encode()
        return PublicListingPage.model_validate_json(self.cache.get_or_load(key, load))

    def detail(self, listing_id: int) -> PublicListingResponse | None:
        def load():
            rows = self.repository.public_by_ids([listing_id])
            return ListingService._to_public_response(rows[0]).model_dump_json().encode() if rows else b'null'
        value = self.cache.get_or_load(('listing-detail-v1', listing_id), load)
        return None if value == b'null' else PublicListingResponse.model_validate_json(value)

    def legacy(self) -> list[PublicListingResponse]:
        schema = TypeAdapter(list[PublicListingResponse])
        def load() -> bytes:
            rows = self.repository.public_page(limit=None)
            return schema.dump_json([ListingService._to_public_response(row) for row in rows])
        return schema.validate_json(self.cache.get_or_load(('listing-legacy-v1',), load))


class PublicReadService(ListingService):
    """HTTP read adapter. Business services continue to construct ListingService."""
    def __init__(self, repository: ListingRepository, cache: PublicCache) -> None:
        super().__init__(repository)
        self._reads = PublicListingReads(repository, cache)

    def list_public_listings(self, *, center: tuple[float, float] | None = None,
                             radius_km: int | None = None) -> list[PublicListingResponse]:
        if center is not None or radius_km is not None:
            # Google-derived coordinates are deliberately excluded from the cache.
            return super().list_public_listings(center=center, radius_km=radius_km)
        return self._reads.legacy()

    def get_public_listing(self, listing_id: int) -> PublicListingResponse | None:
        return self._reads.detail(listing_id)
