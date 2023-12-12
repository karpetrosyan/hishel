import pytest

from hishel import LFUCache


def test_lfu_cache():
    cache: LFUCache[int, int] = LFUCache(2)

    cache.put(1, 2)
    a = cache.get(1)

    assert a == 2


def test_lfu_cache_delete():
    cache: LFUCache[int, int] = LFUCache(2)

    cache.put(1, 2)
    cache.put(3, 4)
    cache.put(5, 6)
    cache.get(3)
    cache.get(3)

    with pytest.raises(KeyError):
        cache.get(1)


def test_lfu_cache_invalid_capacity():
    with pytest.raises(ValueError, match="Capacity must be positive"):
        LFUCache(0)


def test_lfu_cache_delete_least_frequently():
    cache: LFUCache[int, int] = LFUCache(2)

    cache.put(1, 10)
    cache.put(2, 10)

    cache.get(1)
    cache.put(3, 10)

    with pytest.raises(KeyError):
        cache.get(2)

    cache: LFUCache[int, int] = LFUCache(2)  # type: ignore[no-redef]

    cache.put(1, 10)
    cache.put(2, 10)

    cache.get(2)
    cache.put(3, 10)

    with pytest.raises(KeyError):
        cache.get(1)


def test_lfu_cache_remove_key():
    cache: LFUCache[int, int] = LFUCache(2)

    cache.put(1, 10)
    cache.put(2, 10)

    cache.remove_key(1)

    with pytest.raises(KeyError):
        cache.get(1)

    cache.put(1, 10)
    cache.get(1)

    assert cache.min_freq == 1
    cache.remove_key(2)
    assert cache.min_freq == 2


def test_lfu_cache_put_existing():
    cache: LFUCache[int, int] = LFUCache(2)

    cache.put(1, 10)
    cache.put(2, 10)

    cache.put(1, 20)

    assert cache.get(1) == 20

    cache: LFUCache[int, int] = LFUCache(2)  # type: ignore[no-redef]

    cache.put(1, 10)
    cache.put(1, 20)

    assert cache.get(1) == 20
