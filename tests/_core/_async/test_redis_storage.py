import logging
import math
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import fakeredis.aioredis
import pytest
from redis import RedisError
from time_machine import travel

from hishel import Headers, Request, Response
from hishel._core._storages._async_redis import STORAGE_CHUNK_SIZE, AsyncRedisStorage
from hishel._utils import make_async_iterator

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def at(seconds):
    return travel(START + timedelta(seconds=seconds), tick=False)


def new_storage(**kwargs):
    kwargs.setdefault("default_ttl", None)
    return AsyncRedisStorage(fakeredis.aioredis.FakeRedis(), **kwargs)


def req():
    return Request(method="GET", url="https://example.com")


async def store(storage, key="k", body=b"data", **limits):
    entry = await storage.create_entry(
        req(), Response(status_code=200, stream=make_async_iterator([body])), key, **limits
    )
    await read(entry)
    return entry


async def read(entry):
    return b"".join([chunk async for chunk in entry.response.stream])


async def keys(storage):
    return sorted((await storage._client.keys("*")))


@pytest.mark.anyio
async def test_round_trip_rechunks_and_returns_exact_body():
    storage = new_storage()
    body = b"x" * (STORAGE_CHUNK_SIZE * 2 + 5)
    entry = await store(storage, body=body)
    [got] = await storage.get_entries("k")
    assert await read(got) == body
    assert await storage._client.llen(f"hishel:stream:{entry.id.hex}") == 3


@pytest.mark.anyio
async def test_empty_body():
    storage = new_storage()
    await store(storage, body=b"")
    [got] = await storage.get_entries("k")
    assert await read(got) == b""


@pytest.mark.anyio
async def test_incomplete_entry_is_invisible_until_stream_finishes():
    storage = new_storage()
    entry = await storage.create_entry(req(), Response(status_code=200, stream=make_async_iterator([b"a", b"b"])), "k")
    assert await storage.get_entries("k") == []
    await read(entry)
    assert len(await storage.get_entries("k")) == 1


@pytest.mark.anyio
async def test_ttl_hides_and_redis_reclaims_after_grace():
    storage = new_storage(default_ttl=100)
    with at(0):
        await store(storage)
    with at(99):
        assert len(await storage.get_entries("k")) == 1
    with at(101):
        assert await storage.get_entries("k") == []
        assert await keys(storage) != []
    with at(100 + 181):
        assert await keys(storage) == []


@pytest.mark.anyio
async def test_tti_extends_on_read_and_expires_when_idle():
    storage = new_storage(default_tti=100)
    with at(0):
        await store(storage)
    for t in (80, 160, 240):
        with at(t):
            assert len(await storage.get_entries("k")) == 1
    with at(339):
        assert len(await storage.get_entries("k")) == 1
    with at(450):
        assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_tti_keys_survive_as_long_as_entry_is_used():
    storage = new_storage(default_tti=100, soft_delete_ttl=10)
    with at(0):
        await store(storage)
    for t in range(60, 1000, 60):
        with at(t):
            [got] = await storage.get_entries("k")
            assert await read(got) == b"data"


@pytest.mark.anyio
async def test_ttl_caps_tti():
    storage = new_storage(default_ttl=200, default_tti=100)
    with at(0):
        await store(storage)
    for t in (80, 160):
        with at(t):
            assert len(await storage.get_entries("k")) == 1
    with at(201):
        assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_values_passed_to_create_entry_override_defaults_and_are_stored():
    storage = new_storage(default_ttl=1000, default_tti=1000)
    with at(0):
        await store(storage, ttl=500, tti=100)
    with at(99):
        assert len(await storage.get_entries("k")) == 1
    with at(250):
        assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_default_ttl_is_an_hour():
    storage = AsyncRedisStorage(fakeredis.aioredis.FakeRedis())
    with at(0):
        await store(storage)
    with at(3599):
        assert len(await storage.get_entries("k")) == 1
    with at(3601):
        assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_unlimited_entry_keys_never_expire():
    storage = new_storage()
    entry = await store(storage)
    for key in await keys(storage):
        assert await storage._client.pttl(key) == -1, key
    assert await storage._client.zscore("hishel:idx:k", entry.id.hex) == math.inf
    with at(10**7):
        assert len(await storage.get_entries("k")) == 1


@pytest.mark.anyio
async def test_index_outlives_every_entry_in_it():
    storage = new_storage(soft_delete_ttl=10)
    with at(0):
        await store(storage, ttl=1000)
        await store(storage, ttl=100)
    with at(500):
        assert len(await storage.get_entries("k")) == 1

    storage = new_storage(soft_delete_ttl=10)
    with at(0):
        await store(storage)
        await store(storage, ttl=100)
    with at(10**6):
        assert len(await storage.get_entries("k")) == 1


@pytest.mark.anyio
async def test_writing_clears_expired_members_from_index():
    storage = new_storage(soft_delete_ttl=10)
    with at(0):
        await store(storage, ttl=10)
    with at(100):
        await store(storage, ttl=1000)
        assert await storage._client.zcard("hishel:idx:k") == 1


@pytest.mark.anyio
async def test_frequent_reads_do_not_write():
    storage = new_storage(default_tti=1000)
    with at(0):
        await store(storage)
    with at(10):
        calls = []
        original = storage._extend_expiry

        async def spy(*args):
            calls.append(args)
            await original(*args)

        storage._extend_expiry = spy
        await storage.get_entries("k")
        assert calls == []
    with at(600):
        await storage.get_entries("k")
        assert len(calls) == 1


@pytest.mark.anyio
async def test_update_headers_keeps_limits_expiry_and_body():
    storage = new_storage()
    with at(0):
        entry = await store(storage, ttl=100, tti=50)
        ttl_before = await storage._client.pttl(f"hishel:entry:{entry.id.hex}")
        await storage.update_headers(entry.id, Headers({"etag": "new"}))
        assert await storage._client.pttl(f"hishel:entry:{entry.id.hex}") == ttl_before
        [got] = await storage.get_entries("k")
        assert got.response.headers["etag"] == "new"
        assert await read(got) == b"data"
    with at(40):
        assert len(await storage.get_entries("k")) == 1
    with at(80):
        assert len(await storage.get_entries("k")) == 1
    with at(101):
        assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_remove_and_update_missing_entry_are_noops():
    storage = new_storage()
    await storage.remove_entry(uuid.uuid4())
    await storage.update_headers(uuid.uuid4(), Headers({"a": "b"}))


@pytest.mark.anyio
async def test_remove_hides_immediately_but_reader_can_finish():
    storage = new_storage()
    with at(0):
        entry = await store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 2))
        [got] = await storage.get_entries("k")
        stream = got.response.stream
        await stream.__anext__()
        await storage.remove_entry(entry.id)
        assert await storage.get_entries("k") == []
    with at(100):
        await stream.__anext__()
    with at(100 + 181):
        assert await keys(storage) == []


@pytest.mark.anyio
async def test_remove_racing_with_lookup_extension_stays_removed():
    storage = new_storage(default_tti=100)
    with at(0):
        entry = await store(storage)
    with at(90):
        original = storage._extend_expiry

        async def remove_first(*args):
            await storage.remove_entry(entry.id)
            await original(*args)

        storage._extend_expiry = remove_first
        await storage.get_entries("k")
        storage._extend_expiry = original
        assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_remove_during_write_stays_removed_and_consumer_is_served():
    storage = new_storage()
    chunks = [b"x" * STORAGE_CHUNK_SIZE] * 3
    entry = await storage.create_entry(req(), Response(status_code=200, stream=make_async_iterator(chunks)), "k")
    stream = entry.response.stream
    received = [await stream.__anext__()]
    await storage.remove_entry(entry.id)
    async for chunk in stream:
        received.append(chunk)
    assert b"".join(received) == b"".join(chunks)
    assert await storage.get_entries("k") == []
    assert await keys(storage) == []


@pytest.mark.anyio
async def test_remove_just_before_publish_commits_stays_removed(caplog):
    storage = new_storage()
    entry = await storage.create_entry(req(), Response(status_code=200, stream=make_async_iterator([b"a"])), "k")
    stream = entry.response.stream
    await stream.__anext__()
    original = storage._client.pttl

    async def remove_then_pttl(key):
        await storage.remove_entry(entry.id)
        return await original(key)

    storage._client.pttl = remove_then_pttl
    with caplog.at_level(logging.CRITICAL):
        async for _ in stream:
            pass
    storage._client.pttl = original
    assert await storage.get_entries("k") == []
    assert await keys(storage) == []


@pytest.mark.anyio
async def test_reader_heartbeat_outlives_expiry():
    storage = new_storage(default_ttl=100)
    with at(0):
        await store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 8))
        [got] = await storage.get_entries("k")
    stream = got.response.stream
    total = 0
    for i in range(8):
        with at(i * 100):  # spans 700s, well past TTL and grace
            total += len(await stream.__anext__())
    assert total == STORAGE_CHUNK_SIZE * 8


@pytest.mark.anyio
async def test_reader_heartbeat_does_not_shorten_keys():
    storage = new_storage(default_ttl=10000)
    with at(0):
        entry = await store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 2))
        [got] = await storage.get_entries("k")
    with at(100):
        await read(got)
        assert await storage._client.pttl(f"hishel:stream:{entry.id.hex}") > 9_000_000


@pytest.mark.anyio
async def test_stalled_reader_past_grace_raises_instead_of_truncating():
    storage = new_storage(default_ttl=100)
    with at(0):
        await store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 2))
        [got] = await storage.get_entries("k")
    stream = got.response.stream
    with at(1):
        await stream.__anext__()
    with at(1000), pytest.raises(RuntimeError, match="deleted while"):
        await stream.__anext__()


@pytest.mark.anyio
async def test_evicted_stream_is_a_miss_not_an_empty_body():
    storage = new_storage()
    entry = await store(storage)
    await storage._client.delete(f"hishel:stream:{entry.id.hex}")
    assert await storage.get_entries("k") == []
    assert await storage._client.zcard("hishel:idx:k") == 0


@pytest.mark.anyio
@pytest.mark.parametrize("prefix", ["entry", "stream_done"])
async def test_evicted_metadata_keys_are_a_miss(prefix):
    storage = new_storage()
    entry = await store(storage)
    await storage._client.delete(f"hishel:{prefix}:{entry.id.hex}")
    assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_slow_writer_keeps_keys_alive_and_publishes():
    storage = new_storage()
    with at(0):
        entry = await storage.create_entry(
            req(), Response(status_code=200, stream=make_async_iterator([b"x" * STORAGE_CHUNK_SIZE] * 6)), "k"
        )
    stream = entry.response.stream
    for i in range(6):
        with at(i * 150):
            await stream.__anext__()
    with at(900), pytest.raises(StopAsyncIteration):
        await stream.__anext__()
    with at(900):
        [got] = await storage.get_entries("k")
        assert len(await read(got)) == STORAGE_CHUNK_SIZE * 6


@pytest.mark.anyio
async def test_writer_that_lost_its_data_does_not_publish():
    storage = new_storage()
    with at(0):
        entry = await storage.create_entry(
            req(), Response(status_code=200, stream=make_async_iterator([b"x" * STORAGE_CHUNK_SIZE] * 2)), "k"
        )
        stream = entry.response.stream
        await stream.__anext__()
    with at(10_000):  # stalled past the keys' short TTL
        async for _ in stream:
            pass
        assert await storage.get_entries("k") == []
        assert await keys(storage) == []


@pytest.mark.anyio
async def test_abandoned_stream_discards_partial_data_immediately():
    storage = new_storage()
    entry = await storage.create_entry(
        req(), Response(status_code=200, stream=make_async_iterator([b"x" * STORAGE_CHUNK_SIZE] * 3)), "k"
    )
    stream = entry.response.stream
    await stream.__anext__()
    await stream.__anext__()
    assert await keys(storage) != []
    await stream.aclose()
    assert await keys(storage) == []


@pytest.mark.anyio
async def test_crashed_writer_keys_expire_after_grace():
    storage = new_storage()
    with at(0):
        entry = await storage.create_entry(
            req(), Response(status_code=200, stream=make_async_iterator([b"x" * STORAGE_CHUNK_SIZE] * 2)), "k"
        )
        await entry.response.stream.__anext__()
        assert await keys(storage) != []
    with at(181):
        assert await keys(storage) == []


@pytest.mark.anyio
async def test_upstream_failure_discards_and_propagates():
    async def boom() -> AsyncIterator[bytes]:
        yield b"x" * STORAGE_CHUNK_SIZE
        raise ValueError("upstream")

    storage = new_storage()
    entry = await storage.create_entry(req(), Response(status_code=200, stream=boom()), "k")
    with pytest.raises(ValueError):
        await read(entry)
    assert await keys(storage) == []


@pytest.mark.anyio
async def test_too_big_response_is_not_cached_but_fully_delivered():
    storage = new_storage(max_stream_size=1000)
    chunks = [b"x" * 700] * 5
    entry = await storage.create_entry(req(), Response(status_code=200, stream=make_async_iterator(chunks)), "k")
    assert await read(entry) == b"".join(chunks)
    assert await storage.get_entries("k") == []
    assert await keys(storage) == []


@pytest.mark.anyio
async def test_storage_failure_mid_stream_does_not_fail_consumer(caplog):
    storage = new_storage()
    chunks = [b"x" * STORAGE_CHUNK_SIZE] * 4
    entry = await storage.create_entry(req(), Response(status_code=200, stream=make_async_iterator(chunks)), "k")
    stream = entry.response.stream
    received = [await stream.__anext__()]
    original = storage._client.pipeline

    def broken(*args, **kwargs):
        raise RedisError("down")

    storage._client.pipeline = broken
    with caplog.at_level(logging.CRITICAL):
        async for chunk in stream:
            received.append(chunk)
    storage._client.pipeline = original
    assert b"".join(received) == b"".join(chunks)
    assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_create_entry_failure_serves_uncached(caplog):
    storage = new_storage()

    async def broken(*args, **kwargs):
        raise RedisError("down")

    storage._client.set = broken
    with caplog.at_level(logging.CRITICAL):
        entry = await storage.create_entry(req(), Response(status_code=200, stream=make_async_iterator([b"d"])), "k")
    assert await read(entry) == b"d"


@pytest.mark.anyio
async def test_outage_does_not_fail_the_caller(caplog):
    storage = new_storage()
    entry = await store(storage)

    async def broken(*args, **kwargs):
        raise RedisError("down")

    for command in ("zrangebyscore", "get", "set", "zrem"):
        setattr(storage._client, command, broken)
    with caplog.at_level(logging.CRITICAL):
        assert await storage.get_entries("k") == []
        await storage.update_headers(entry.id, Headers({"x": "1"}))
        await storage.remove_entry(entry.id)
        without_body = await storage.create_entry(req(), Response(status_code=204), "k")
    assert await read(without_body) == b""


@pytest.mark.anyio
async def test_corrupt_entry_is_dropped_and_lookup_still_works(caplog):
    storage = new_storage()
    bad = await store(storage)
    await store(storage)
    await storage._client.set(f"hishel:entry:{bad.id.hex}", b"\xc1garbage")
    with caplog.at_level(logging.CRITICAL):
        assert len(await storage.get_entries("k")) == 1
    assert await storage._client.zcard("hishel:idx:k") == 1


@pytest.mark.anyio
async def test_defaults_apply_only_to_entries_created_under_them():
    client = fakeredis.aioredis.FakeRedis()
    first = AsyncRedisStorage(client, default_ttl=None, default_tti=100)
    with at(0):
        await store(first)

    second = AsyncRedisStorage(client, default_ttl=None, default_tti=1000)
    with at(90):
        assert len(await second.get_entries("k")) == 1
    with at(250):
        assert await second.get_entries("k") == []


@pytest.mark.anyio
async def test_corrupt_limits_are_dropped_and_lookup_still_works(caplog):
    storage = new_storage()
    bad = await store(storage)
    await store(storage)
    await storage._client.set(f"hishel:stream_done:{bad.id.hex}", b"\xc1garbage")
    with caplog.at_level(logging.CRITICAL):
        assert len(await storage.get_entries("k")) == 1
    assert await storage._client.zcard("hishel:idx:k") == 1


@pytest.mark.anyio
async def test_entries_get_their_id_and_key_without_the_blob():
    storage = new_storage()
    entry = await store(storage, key="some-key")
    [got] = await storage.get_entries("some-key")
    assert got.id == entry.id
    blob = await storage._client.get(f"hishel:entry:{entry.id.hex}")
    assert entry.id.bytes not in blob and b"some-key" not in blob


@pytest.mark.anyio
async def test_remove_finds_the_index_for_any_key():
    storage = new_storage()
    entry = await store(storage, key="some/key:with-symbols")
    await storage.remove_entry(entry.id)
    assert await storage.get_entries("some/key:with-symbols") == []
    assert await storage._client.zcard("hishel:idx:some/key:with-symbols") == 0


@pytest.mark.anyio
async def test_response_without_a_stream_is_stored_with_an_empty_body():
    storage = new_storage()
    entry = await storage.create_entry(req(), Response(status_code=204), "k")
    assert await read(entry) == b""
    [got] = await storage.get_entries("k")
    assert got.response.status_code == 204
    assert await read(got) == b""
