from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import Mock

from app.services.public_cache import MemoryPublicCache


def test_hit_miss_and_expiry():
    now = [0.0]
    cache = MemoryPublicCache(ttl=5, clock=lambda: now[0])
    load = Mock(return_value=b'validated')
    assert cache.get_or_load(('one',), load) == b'validated'
    assert cache.get_or_load(('one',), load) == b'validated'
    assert load.call_count == 1
    now[0] = 5
    cache.get_or_load(('one',), load)
    assert load.call_count == 2
    assert cache.stats == dict(hit=1, miss=2, expired=1, eviction=0, invalidation=0)


def test_lru_and_byte_bounds_and_oversized_values():
    cache = MemoryPublicCache(max_entries=2, max_bytes=6)
    for key in ['a', 'b']:
        cache.get_or_load((key,), lambda: b'123')
    cache.get_or_load(('a',), lambda: b'bad')
    cache.get_or_load(('c',), lambda: b'123')
    load = Mock(return_value=b'456')
    cache.get_or_load(('b',), load)
    assert load.call_count == 1
    assert cache._bytes <= 6 and len(cache._entries) <= 2
    huge = Mock(return_value=b'1234567')
    cache.get_or_load(('huge',), huge)
    cache.get_or_load(('huge',), huge)
    assert huge.call_count == 2


def test_concurrent_identical_misses_only_load_once():
    cache = MemoryPublicCache()
    entered, release = Event(), Event()
    def load():
        entered.set()
        assert release.wait(5)
        return b'public'
    loader = Mock(side_effect=load)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(cache.get_or_load, ('same',), loader) for _ in range(4)]
        assert entered.wait(5)
        release.set()
        assert [f.result(5) for f in futures] == [b'public'] * 4
    assert loader.call_count == 1


def test_invalidation_prevents_stale_inflight_fill():
    cache = MemoryPublicCache()
    entered, release = Event(), Event()
    def old():
        entered.set()
        assert release.wait(5)
        return b'old'
    with ThreadPoolExecutor() as pool:
        future = pool.submit(cache.get_or_load, ('same',), old)
        assert entered.wait(5)
        cache.invalidate()
        assert cache.get_or_load(('same',), lambda: b'new') == b'new'
        release.set()
        assert future.result(5) == b'old'
    assert cache.get_or_load(('same',), lambda: b'wrong') == b'new'


def test_exceptions_are_not_cached_or_left_pending():
    cache = MemoryPublicCache()
    def fail():
        raise RuntimeError('database unavailable')
    import pytest
    with pytest.raises(RuntimeError):
        cache.get_or_load(('same',), fail)
    assert not cache._pending
    assert cache.get_or_load(('same',), lambda: b'recovered') == b'recovered'
