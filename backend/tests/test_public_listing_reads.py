from datetime import datetime
from unittest.mock import patch
import unittest

from sqlalchemy import event, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
import test_listing_repository as fixtures
from app.models.listing import Listing
from app.models.listing import ListingPhoto
from app.models.amenity import Amenity
from app.models.saved_listing import SavedListing
from app.repositories.listing_repository import ListingRepository
from app.services.public_cache import MemoryPublicCache
from app.services.public_listing_reads import PublicListingReads
from app.services.saved_listing_service import SavedListingService
from app.services.saved_listing_service import SavedListingUnavailableError


class PublicReadTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ListingRepositoryTests()
        create_engine = fixtures.create_engine
        with patch.object(fixtures, 'create_engine', side_effect=lambda url: create_engine(
                url, connect_args={'check_same_thread': False}, poolclass=StaticPool)):
            self.fixture.setUp()
        self.cache = MemoryPublicCache()
        self.patch = patch('app.services.public_cache.get_public_cache', return_value=self.cache)
        self.patch.start()
        self.session = self.fixture.session
        for number in range(1, 25):
            row = self.fixture.make_listing(number, 'active' if number <= 18 else 'draft',
                                            datetime(2026, 11, number))
            row.latitude, row.longitude = -29.85871, 31.02184
            self.session.add(row)
        self.session.flush()
        for number in range(1, 13):
            self.fixture.repository.add_moderation_decision(number, 1, 'approved', None)
        for number in range(1, 7):
            self.session.add(SavedListing(saved_listing_id=number, tenant_id=1, listing_id=number))
        self.session.commit()
        self.selects = 0
        @event.listens_for(self.fixture.engine, 'before_cursor_execute')
        def count(connection, cursor, statement, parameters, context, executemany):
            self.selects += int(statement.lstrip().upper().startswith('SELECT'))

    def tearDown(self):
        self.patch.stop()
        self.fixture.tearDown()

    def page(self, **changes):
        params = dict(offset=0, limit=8, search='', room_type='', minimum_rent=None,
                      maximum_rent=None, amenities=(), available_by=None, sort='recent')
        with Session(self.fixture.engine) as session:
            return PublicListingReads(ListingRepository(session), self.cache).page(**(params | changes))

    def detail(self, number=1):
        with Session(self.fixture.engine) as session:
            return PublicListingReads(ListingRepository(session), self.cache).detail(number)

    def test_pages_filter_in_sql_and_cache_hits_execute_no_queries(self):
        first = self.page()
        assert [item.listing_id for item in first.items] == list(range(12, 4, -1))
        assert first.next_offset == 8
        assert self.selects == 3
        self.selects = 0
        assert self.page() == first
        assert self.selects == 0
        assert first.items[0].area_name == 'Test area'
        second = self.page(offset=8)
        assert [item.listing_id for item in second.items] == [4, 3, 2, 1]
        assert second.next_offset is None
        assert self.page(minimum_rent=5000).items == []
        assert len(self.page(search='test area').items) == 8
        assert self.page(search='%').items == []
        assert self.page(room_type='shared_room').items == []

    def test_detail_is_complete_validated_and_private_fields_are_absent(self):
        result = self.detail()
        assert self.selects == 3
        self.selects = 0
        assert self.detail() == result
        assert self.selects == 0
        assert result.approximate_latitude == -29.86
        assert result.approximate_longitude == 31.02
        assert not {'landlord_id', 'google_place_id', 'latitude', 'longitude'} & result.model_dump().keys()
        assert self.detail(13) is None  # Unapproved active room.
        assert self.detail(19) is None  # Draft room.

    def test_updates_only_invalidate_after_outer_commit(self):
        self.detail()
        count = self.cache.stats['invalidation']
        row = self.session.get(Listing, 1)
        row.title = 'Changed title'
        self.session.flush()
        assert self.cache.stats['invalidation'] == count
        self.session.commit()
        assert self.cache.stats['invalidation'] == count + 1
        assert self.detail().title == 'Changed title'

    def test_rollback_does_not_invalidate(self):
        self.detail()
        count = self.cache.stats['invalidation']
        self.session.get(Listing, 1).title = 'Rolled back'
        self.session.flush()
        self.session.rollback()
        assert self.cache.stats['invalidation'] == count
        assert self.detail().title == 'Room 1'

    def test_savepoint_commit_waits_for_outer_commit(self):
        self.detail()
        count = self.cache.stats['invalidation']
        with self.session.begin_nested():
            self.session.get(Listing, 1).title = 'Savepoint'
        assert self.cache.stats['invalidation'] == count
        self.session.commit()
        assert self.cache.stats['invalidation'] == count + 1
        assert self.detail().title == 'Savepoint'

    def test_visibility_and_latest_moderation_changes_invalidate_pages_and_details(self):
        self.detail()
        self.page()
        self.session.get(Listing, 1).availability_status = 'occupied'
        self.session.commit()
        assert self.detail() is None
        assert 1 not in [item.listing_id for item in self.page(offset=8).items]
        self.fixture.repository.add_moderation_decision(12, 1, 'rejected', None)
        self.session.commit()
        assert self.detail(12) is None
        assert 12 not in [item.listing_id for item in self.page().items]

    def test_saved_listing_batch_has_constant_query_count(self):
        with Session(self.fixture.engine) as session:
            result = SavedListingService(session).list_for_tenant(1)
        assert len(result) == 6
        assert self.selects == 4

    def test_photo_and_amenity_changes_invalidate_and_survive_serialization(self):
        self.detail()
        row = self.session.get(Listing, 1)
        row.photos.append(ListingPhoto(photo_id=1, url='https://example.test/photo.jpg'))
        row.amenities.append(Amenity(amenity_id=1, name='Wi-Fi'))
        self.session.commit()
        response = self.detail()
        assert response.amenities == ['Wi-Fi']
        assert response.photos[0].url == 'https://example.test/photo.jpg'
        assert self.detail() == response
        assert self.page(amenities=('Wi-Fi',)).items[0].listing_id == 1

    def test_card_projection_does_not_replace_complete_detail(self):
        row = self.session.get(Listing, 1)
        row.description = 'A' * 500
        row.photos.extend(ListingPhoto(photo_id=number, url=f'https://example.test/{number}.jpg')
                          for number in range(1, 4))
        self.session.commit()
        page = self.page(search='Room 1')
        card = next(item for item in page.items if item.listing_id == 1)
        assert len(card.photos) == 1 and len(card.description) == 240
        detail = self.detail()
        assert len(detail.photos) == 3 and len(detail.description) == 500

    def test_stale_public_cache_cannot_authorize_saving_an_unavailable_room(self):
        self.detail(12)
        # Simulate a write from another worker/process, which has its own cache.
        self.session.execute(update(Listing).where(Listing.listing_id == 12)
                             .values(availability_status='occupied'))
        self.session.commit()
        assert self.detail(12) is not None
        with self.assertRaises(SavedListingUnavailableError):
            SavedListingService(self.session).save_for_tenant(1, 12)

    def test_http_cache_hits_have_zero_selects_and_log_only_route_metrics(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.db.session import get_db
        def db():
            with Session(self.fixture.engine) as session:
                yield session
        app.dependency_overrides[get_db] = db
        try:
            with patch('app.api.v1.endpoints.listings.get_public_cache', return_value=self.cache):
                with TestClient(app) as client, self.assertLogs('app.main', level='INFO') as logs:
                    first = client.get('/api/v1/listings/search')
                    second = client.get('/api/v1/listings/search')
                    invalid = client.get('/api/v1/listings/search?limit=51')
                    detail = client.get('/api/v1/listings/1')
            assert first.status_code == second.status_code == detail.status_code == 200
            assert len(first.json()['items']) == 8
            assert invalid.status_code == 422
            assert first.json() == second.json()
            assert 'selects=3' in logs.output[0]
            assert 'selects=0' in logs.output[1]
            assert 'route=/listings/search' in logs.output[0]
            assert 'route=/listings/{listing_id}' in logs.output[-1]
        finally:
            app.dependency_overrides.pop(get_db, None)

    def test_query_count_comparison(self):
        import json
        from app.services.listing_service import ListingService
        def measure(action):
            self.selects = 0
            with Session(self.fixture.engine) as session:
                result = action(session)
            return self.selects, len(result) if isinstance(result, list) else None
        before_page = measure(lambda db: ListingService(ListingRepository(db)).list_public_listings())
        before_detail = measure(lambda db: ListingService(ListingRepository(db)).get_public_listing(1))[0]
        def old_saved(db):
            saved = SavedListingService(db)._saved_listings.list_for_tenant(1)
            service = ListingService(ListingRepository(db))
            return [service.get_public_listing(item.listing_id) for item in saved]
        before_saved = measure(old_saved)[0]
        self.selects = 0
        page = self.page()
        after_page = self.selects
        self.selects = 0
        self.page()
        page_hit = self.selects
        self.selects = 0
        self.detail()
        detail_miss = self.selects
        self.selects = 0
        self.detail()
        detail_hit = self.selects
        after_saved = measure(lambda db: SavedListingService(db).list_for_tenant(1))[0]
        counts = dict(before_page=before_page[0], before_rows=before_page[1],
                      after_page=after_page, after_rows=len(page.items), page_hit=page_hit,
                      before_detail=before_detail, detail_miss=detail_miss, detail_hit=detail_hit,
                      before_saved=before_saved, after_saved=after_saved)
        assert counts == dict(before_page=4, before_rows=12, after_page=3, after_rows=8,
                              page_hit=0, before_detail=4, detail_miss=3, detail_hit=0,
                              before_saved=25, after_saved=4)
        print('\nSynthetic SQLite query comparison: ' + json.dumps(counts, sort_keys=True))
