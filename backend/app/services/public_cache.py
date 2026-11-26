"""Process-local public response cache. Values are validated, serialized schemas."""
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
import logging
from threading import Event, RLock
from time import monotonic
from typing import Protocol
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class PublicCache(Protocol):
    def get_or_load(self, key: tuple, load: Callable[[], bytes]) -> bytes: ...
    def invalidate(self) -> None: ...


@dataclass(frozen=True)
class Entry:
    value: bytes
    expires: float


class MemoryPublicCache:
    def __init__(self, ttl: float = 30, max_entries: int = 128,
                 max_bytes: int = 4 * 1024 * 1024,
                 clock: Callable[[], float] = monotonic) -> None:
        self.ttl, self.max_entries, self.max_bytes = ttl, max_entries, max_bytes
        self._clock = clock
        self._lock = RLock()
        self._entries: OrderedDict[tuple, Entry] = OrderedDict()
        self._pending: dict[tuple, Event] = {}
        self._bytes = 0
        self._generation = 0
        self.stats = dict(hit=0, miss=0, expired=0, eviction=0, invalidation=0)

    def get_or_load(self, key: tuple, load: Callable[[], bytes]) -> bytes:
        while True:
            with self._lock:
                now = self._clock()
                for expired in [k for k, v in self._entries.items() if v.expires <= now]:
                    self._bytes -= len(self._entries.pop(expired).value)
                    self.stats['expired'] += 1
                entry = self._entries.get(key)
                if entry is not None:
                    self._entries.move_to_end(key)
                    self.stats['hit'] += 1
                    logger.info('public_cache result=hit')
                    return entry.value
                generation = self._generation
                flight = (generation, key)
                pending = self._pending.get(flight)
                if pending is None:
                    pending = self._pending[flight] = Event()
                    self.stats['miss'] += 1
                    break
            pending.wait()
        try:
            # Database I/O never holds the shared lock. Unrelated keys run concurrently.
            value = load()
            with self._lock:
                if generation == self._generation and len(value) <= self.max_bytes:
                    self._entries[key] = Entry(value, self._clock() + self.ttl)
                    self._bytes += len(value)
                    while len(self._entries) > self.max_entries or self._bytes > self.max_bytes:
                        self._bytes -= len(self._entries.popitem(last=False)[1].value)
                        self.stats['eviction'] += 1
            logger.info('public_cache result=miss bytes=%d', len(value))
            return value
        finally:
            with self._lock:
                self._pending.pop(flight, None)
                pending.set()

    def invalidate(self) -> None:
        with self._lock:
            self._generation += 1
            self._entries.clear()
            self._bytes = 0
            self.stats['invalidation'] += 1
        logger.info('public_cache result=invalidation')


@lru_cache
def get_public_cache() -> MemoryPublicCache:
    settings = get_settings()
    return MemoryPublicCache(settings.public_cache_ttl_seconds,
                             settings.public_cache_max_entries,
                             settings.public_cache_max_bytes)


def install_invalidation() -> None:
    """Track ORM changes through the outer transaction, including commit=False flows.

    Savepoint rollback may cause an extra invalidation on outer commit, which is safe.
    Never invalidate on a savepoint commit or publish an uncommitted response.
    """
    from sqlalchemy import event
    from sqlalchemy.orm import Session
    from app.models.listing import Listing, ListingPhoto
    from app.models.listing_moderation import ListingModeration
    from app.models.area import Area
    from app.models.amenity import Amenity

    @event.listens_for(Session, 'before_flush')
    def track(session, context, instances):
        relevant = (Listing, ListingPhoto, ListingModeration, Area, Amenity)
        if any(isinstance(item, relevant) for item in session.new | session.dirty | session.deleted):
            session.info['public_listing_changed'] = True

    @event.listens_for(Session, 'after_commit')
    def committed(session):
        if not session.in_nested_transaction() and session.info.pop('public_listing_changed', False):
            get_public_cache().invalidate()

    @event.listens_for(Session, 'after_soft_rollback')
    def rolled_back(session, previous):
        if previous.parent is None:
            session.info.pop('public_listing_changed', None)


install_invalidation()
