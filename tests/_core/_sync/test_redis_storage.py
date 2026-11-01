import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import Iterator

import fakeredis
import pytest
from redis import RedisError
from time_machine import travel

from hishel import Headers, Request, Response
from hishel._core._storages._sync_redis import STORAGE_CHUNK_SIZE, RedisStorage
from hishel._utils import make_sync_iterator

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def at(seconds):
    return travel(START + timedelta(seconds=seconds), tick=False)


def new_storage(**kwargs):
    kwargs.setdefault("default_ttl", None)
    return RedisStorage(fakeredis.FakeRedis(), **kwargs)


def req():
    return Request(method="GET", url="https://example.com")


def store(storage, key="k", body=b"data", **limits):
    entry = storage.create_entry(
        req(), Response(status_code=200, stream=make_sync_iterator([body])), key, **limits
    )
    read(entry)
    return entry


def read(entry):
    return b"".join([chunk for chunk in entry.response.stream])


def keys(storage):
    return sorted((storage._client.keys("*")))



def test_round_trip_rechunks_and_returns_exact_body():
    storage = new_storage()
    body = b"x" * (STORAGE_CHUNK_SIZE * 2 + 5)
    entry = store(storage, body=body)
    [got] = storage.get_entries("k")
    assert read(got) == body
    assert storage._client.llen(f"hishel:stream:{entry.id.hex}") == 3



def test_empty_body():
    storage = new_storage()
    store(storage, body=b"")
    [got] = storage.get_entries("k")
    assert read(got) == b""



def test_incomplete_entry_is_invisible_until_stream_finishes():
    storage = new_storage()
    entry = storage.create_entry(req(), Response(status_code=200, stream=make_sync_iterator([b"a", b"b"])), "k")
    assert storage.get_entries("k") == []
    read(entry)
    assert len(storage.get_entries("k")) == 1



def test_ttl_hides_and_redis_reclaims_after_grace():
    storage = new_storage(default_ttl=100)
    with at(0):
        store(storage)
    with at(99):
        assert len(storage.get_entries("k")) == 1
    with at(101):
        assert storage.get_entries("k") == []
        assert keys(storage) != []
    with at(100 + 181):
        assert keys(storage) == []



def test_tti_extends_on_read_and_expires_when_idle():
    storage = new_storage(default_tti=100)
    with at(0):
        store(storage)
    for t in (80, 160, 240):
        with at(t):
            assert len(storage.get_entries("k")) == 1
    with at(339):
        assert len(storage.get_entries("k")) == 1
    with at(450):
        assert storage.get_entries("k") == []



def test_tti_keys_survive_as_long_as_entry_is_used():
    storage = new_storage(default_tti=100, soft_delete_ttl=10)
    with at(0):
        store(storage)
    for t in range(60, 1000, 60):
        with at(t):
            [got] = storage.get_entries("k")
            assert read(got) == b"data"



def test_ttl_caps_tti():
    storage = new_storage(default_ttl=200, default_tti=100)
    with at(0):
        store(storage)
    for t in (80, 160):
        with at(t):
            assert len(storage.get_entries("k")) == 1
    with at(201):
        assert storage.get_entries("k") == []



def test_values_passed_to_create_entry_override_defaults_and_are_stored():
    storage = new_storage(default_ttl=1000, default_tti=1000)
    with at(0):
        store(storage, ttl=500, tti=100)
    with at(99):
        assert len(storage.get_entries("k")) == 1
    with at(250):
        assert storage.get_entries("k") == []



def test_default_ttl_is_an_hour():
    storage = RedisStorage(fakeredis.FakeRedis())
    with at(0):
        store(storage)
    with at(3599):
        assert len(storage.get_entries("k")) == 1
    with at(3601):
        assert storage.get_entries("k") == []



def test_unlimited_entry_keys_never_expire():
    storage = new_storage()
    entry = store(storage)
    for key in keys(storage):
        assert storage._client.pttl(key) == -1, key
    assert storage._client.zscore("hishel:idx:k", entry.id.hex) == math.inf
    with at(10**7):
        assert len(storage.get_entries("k")) == 1



def test_index_outlives_every_entry_in_it():
    storage = new_storage(soft_delete_ttl=10)
    with at(0):
        store(storage, ttl=1000)
        store(storage, ttl=100)
    with at(500):
        assert len(storage.get_entries("k")) == 1

    storage = new_storage(soft_delete_ttl=10)
    with at(0):
        store(storage)
        store(storage, ttl=100)
    with at(10**6):
        assert len(storage.get_entries("k")) == 1



def test_writing_clears_expired_members_from_index():
    storage = new_storage(soft_delete_ttl=10)
    with at(0):
        store(storage, ttl=10)
    with at(100):
        store(storage, ttl=1000)
        assert storage._client.zcard("hishel:idx:k") == 1



def test_frequent_reads_do_not_write():
    storage = new_storage(default_tti=1000)
    with at(0):
        store(storage)
    with at(10):
        calls = []
        original = storage._extend_expiry

        def spy(*args):
            calls.append(args)
            original(*args)

        storage._extend_expiry = spy
        storage.get_entries("k")
        assert calls == []
    with at(600):
        storage.get_entries("k")
        assert len(calls) == 1



def test_update_headers_keeps_limits_expiry_and_body():
    storage = new_storage()
    with at(0):
        entry = store(storage, ttl=100, tti=50)
        ttl_before = storage._client.pttl(f"hishel:entry:{entry.id.hex}")
        storage.update_headers(entry.id, Headers({"etag": "new"}))
        assert storage._client.pttl(f"hishel:entry:{entry.id.hex}") == ttl_before
        [got] = storage.get_entries("k")
        assert got.response.headers["etag"] == "new"
        assert read(got) == b"data"
    with at(40):
        assert len(storage.get_entries("k")) == 1
    with at(80):
        assert len(storage.get_entries("k")) == 1
    with at(101):
        assert storage.get_entries("k") == []



def test_remove_and_update_missing_entry_are_noops():
    storage = new_storage()
    storage.remove_entry(uuid.uuid4())
    storage.update_headers(uuid.uuid4(), Headers({"a": "b"}))



def test_remove_hides_immediately_but_reader_can_finish():
    storage = new_storage()
    with at(0):
        entry = store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 2))
        [got] = storage.get_entries("k")
        stream = got.response.stream
        stream.__next__()
        storage.remove_entry(entry.id)
        assert storage.get_entries("k") == []
    with at(100):
        stream.__next__()
    with at(100 + 181):
        assert keys(storage) == []



def test_remove_racing_with_lookup_extension_stays_removed():
    storage = new_storage(default_tti=100)
    with at(0):
        entry = store(storage)
    with at(90):
        original = storage._extend_expiry

        def remove_first(*args):
            storage.remove_entry(entry.id)
            original(*args)

        storage._extend_expiry = remove_first
        storage.get_entries("k")
        storage._extend_expiry = original
        assert storage.get_entries("k") == []



def test_remove_during_write_stays_removed_and_consumer_is_served():
    storage = new_storage()
    chunks = [b"x" * STORAGE_CHUNK_SIZE] * 3
    entry = storage.create_entry(req(), Response(status_code=200, stream=make_sync_iterator(chunks)), "k")
    stream = entry.response.stream
    received = [stream.__next__()]
    storage.remove_entry(entry.id)
    for chunk in stream:
        received.append(chunk)
    assert b"".join(received) == b"".join(chunks)
    assert storage.get_entries("k") == []
    assert keys(storage) == []



def test_remove_just_before_publish_commits_stays_removed(caplog):
    storage = new_storage()
    entry = storage.create_entry(req(), Response(status_code=200, stream=make_sync_iterator([b"a"])), "k")
    stream = entry.response.stream
    stream.__next__()
    original = storage._client.pttl

    def remove_then_pttl(key):
        storage.remove_entry(entry.id)
        return original(key)

    storage._client.pttl = remove_then_pttl
    with caplog.at_level(logging.CRITICAL):
        for _ in stream:
            pass
    storage._client.pttl = original
    assert storage.get_entries("k") == []
    assert keys(storage) == []



def test_reader_heartbeat_outlives_expiry():
    storage = new_storage(default_ttl=100)
    with at(0):
        store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 8))
        [got] = storage.get_entries("k")
    stream = got.response.stream
    total = 0
    for i in range(8):
        with at(i * 100):  # spans 700s, well past TTL and grace
            total += len(stream.__next__())
    assert total == STORAGE_CHUNK_SIZE * 8



def test_reader_heartbeat_does_not_shorten_keys():
    storage = new_storage(default_ttl=10000)
    with at(0):
        entry = store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 2))
        [got] = storage.get_entries("k")
    with at(100):
        read(got)
        assert storage._client.pttl(f"hishel:stream:{entry.id.hex}") > 9_000_000



def test_stalled_reader_past_grace_raises_instead_of_truncating():
    storage = new_storage(default_ttl=100)
    with at(0):
        store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 2))
        [got] = storage.get_entries("k")
    stream = got.response.stream
    with at(1):
        stream.__next__()
    with at(1000), pytest.raises(RuntimeError, match="deleted while"):
        stream.__next__()



def test_evicted_stream_is_a_miss_not_an_empty_body():
    storage = new_storage()
    entry = store(storage)
    storage._client.delete(f"hishel:stream:{entry.id.hex}")
    assert storage.get_entries("k") == []
    assert storage._client.zcard("hishel:idx:k") == 0



@pytest.mark.parametrize("prefix", ["entry", "stream_done"])
def test_evicted_metadata_keys_are_a_miss(prefix):
    storage = new_storage()
    entry = store(storage)
    storage._client.delete(f"hishel:{prefix}:{entry.id.hex}")
    assert storage.get_entries("k") == []



def test_slow_writer_keeps_keys_alive_and_publishes():
    storage = new_storage()
    with at(0):
        entry = storage.create_entry(
            req(), Response(status_code=200, stream=make_sync_iterator([b"x" * STORAGE_CHUNK_SIZE] * 6)), "k"
        )
    stream = entry.response.stream
    for i in range(6):
        with at(i * 150):
            stream.__next__()
    with at(900), pytest.raises(StopIteration):
        stream.__next__()
    with at(900):
        [got] = storage.get_entries("k")
        assert len(read(got)) == STORAGE_CHUNK_SIZE * 6



def test_writer_that_lost_its_data_does_not_publish():
    storage = new_storage()
    with at(0):
        entry = storage.create_entry(
            req(), Response(status_code=200, stream=make_sync_iterator([b"x" * STORAGE_CHUNK_SIZE] * 2)), "k"
        )
        stream = entry.response.stream
        stream.__next__()
    with at(10_000):  # stalled past the keys' short TTL
        for _ in stream:
            pass
        assert storage.get_entries("k") == []
        assert keys(storage) == []



def test_abandoned_stream_discards_partial_data_immediately():
    storage = new_storage()
    entry = storage.create_entry(
        req(), Response(status_code=200, stream=make_sync_iterator([b"x" * STORAGE_CHUNK_SIZE] * 3)), "k"
    )
    stream = entry.response.stream
    stream.__next__()
    stream.__next__()
    assert keys(storage) != []
    stream.close()
    assert keys(storage) == []



def test_crashed_writer_keys_expire_after_grace():
    storage = new_storage()
    with at(0):
        entry = storage.create_entry(
            req(), Response(status_code=200, stream=make_sync_iterator([b"x" * STORAGE_CHUNK_SIZE] * 2)), "k"
        )
        entry.response.stream.__next__()
        assert keys(storage) != []
    with at(181):
        assert keys(storage) == []



def test_upstream_failure_discards_and_propagates():
    def boom() -> Iterator[bytes]:
        yield b"x" * STORAGE_CHUNK_SIZE
        raise ValueError("upstream")

    storage = new_storage()
    entry = storage.create_entry(req(), Response(status_code=200, stream=boom()), "k")
    with pytest.raises(ValueError):
        read(entry)
    assert keys(storage) == []



def test_too_big_response_is_not_cached_but_fully_delivered():
    storage = new_storage(max_stream_size=1000)
    chunks = [b"x" * 700] * 5
    entry = storage.create_entry(req(), Response(status_code=200, stream=make_sync_iterator(chunks)), "k")
    assert read(entry) == b"".join(chunks)
    assert storage.get_entries("k") == []
    assert keys(storage) == []



def test_storage_failure_mid_stream_does_not_fail_consumer(caplog):
    storage = new_storage()
    chunks = [b"x" * STORAGE_CHUNK_SIZE] * 4
    entry = storage.create_entry(req(), Response(status_code=200, stream=make_sync_iterator(chunks)), "k")
    stream = entry.response.stream
    received = [stream.__next__()]
    original = storage._client.pipeline

    def broken(*args, **kwargs):
        raise RedisError("down")

    storage._client.pipeline = broken
    with caplog.at_level(logging.CRITICAL):
        for chunk in stream:
            received.append(chunk)
    storage._client.pipeline = original
    assert b"".join(received) == b"".join(chunks)
    assert storage.get_entries("k") == []



def test_create_entry_failure_serves_uncached(caplog):
    storage = new_storage()

    def broken(*args, **kwargs):
        raise RedisError("down")

    storage._client.set = broken
    with caplog.at_level(logging.CRITICAL):
        entry = storage.create_entry(req(), Response(status_code=200, stream=make_sync_iterator([b"d"])), "k")
    assert read(entry) == b"d"



def test_outage_does_not_fail_the_caller(caplog):
    storage = new_storage()
    entry = store(storage)

    def broken(*args, **kwargs):
        raise RedisError("down")

    for command in ("zrangebyscore", "get", "set", "zrem"):
        setattr(storage._client, command, broken)
    with caplog.at_level(logging.CRITICAL):
        assert storage.get_entries("k") == []
        storage.update_headers(entry.id, Headers({"x": "1"}))
        storage.remove_entry(entry.id)
        without_body = storage.create_entry(req(), Response(status_code=204), "k")
    assert read(without_body) == b""



def test_corrupt_entry_is_dropped_and_lookup_still_works(caplog):
    storage = new_storage()
    bad = store(storage)
    store(storage)
    storage._client.set(f"hishel:entry:{bad.id.hex}", b"\xc1garbage")
    with caplog.at_level(logging.CRITICAL):
        assert len(storage.get_entries("k")) == 1
    assert storage._client.zcard("hishel:idx:k") == 1



def test_defaults_apply_only_to_entries_created_under_them():
    client = fakeredis.FakeRedis()
    first = RedisStorage(client, default_ttl=None, default_tti=100)
    with at(0):
        store(first)

    second = RedisStorage(client, default_ttl=None, default_tti=1000)
    with at(90):
        assert len(second.get_entries("k")) == 1
    with at(250):
        assert second.get_entries("k") == []



def test_corrupt_limits_are_dropped_and_lookup_still_works(caplog):
    storage = new_storage()
    bad = store(storage)
    store(storage)
    storage._client.set(f"hishel:stream_done:{bad.id.hex}", b"\xc1garbage")
    with caplog.at_level(logging.CRITICAL):
        assert len(storage.get_entries("k")) == 1
    assert storage._client.zcard("hishel:idx:k") == 1



def test_entries_get_their_id_and_key_without_the_blob():
    storage = new_storage()
    entry = store(storage, key="some-key")
    [got] = storage.get_entries("some-key")
    assert got.id == entry.id
    blob = storage._client.get(f"hishel:entry:{entry.id.hex}")
    assert entry.id.bytes not in blob and b"some-key" not in blob



def test_remove_finds_the_index_for_any_key():
    storage = new_storage()
    entry = store(storage, key="some/key:with-symbols")
    storage.remove_entry(entry.id)
    assert storage.get_entries("some/key:with-symbols") == []
    assert storage._client.zcard("hishel:idx:some/key:with-symbols") == 0



def test_response_without_a_stream_is_stored_with_an_empty_body():
    storage = new_storage()
    entry = storage.create_entry(req(), Response(status_code=204), "k")
    assert read(entry) == b""
    [got] = storage.get_entries("k")
    assert got.response.status_code == 204
    assert read(got) == b""
