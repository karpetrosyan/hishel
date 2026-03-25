from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime
from typing import AsyncIterator
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import fakeredis.aioredis
import pytest
from time_machine import travel

from hishel import Request, Response
from hishel._core._storages._async_redis import AsyncRedisStorage
from hishel._utils import make_async_iterator


@pytest.fixture
def anyio_backend() -> str:
    # redis.asyncio is asyncio-only; restrict async tests to asyncio backend
    return "asyncio"


@pytest.mark.anyio
async def test_add_entry() -> None:
    """Test adding a complete entry with request and response."""
    client = fakeredis.aioredis.FakeRedis()
    storage = AsyncRedisStorage(client=client)

    entry = await storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator([b"response data"])),
        key="test_key",
        id_=uuid.UUID(int=0),
    )

    async for _ in entry.response._aiter_stream():
        ...

    entries = await storage.get_entries("test_key")
    assert len(entries) == 1
    assert entries[0].cache_key == b"test_key"


@pytest.mark.anyio
async def test_add_entry_with_stream() -> None:
    """Test adding an entry with a multi-chunk streaming response body."""
    client = fakeredis.aioredis.FakeRedis()
    storage = AsyncRedisStorage(client=client)

    entry = await storage.create_entry(
        request=Request(method="POST", url="https://example.com/upload"),
        response=Response(status_code=200, stream=make_async_iterator([b"chunk1", b"chunk2"])),
        key="stream_key",
        id_=uuid.UUID(int=0),
    )

    async for _ in entry.response._aiter_stream():
        ...

    entries = await storage.get_entries("stream_key")
    assert len(entries) == 1
    assert entries[0].cache_key == b"stream_key"


@pytest.mark.anyio
async def test_get_entries() -> None:
    """Test retrieving entries by cache key."""
    client = fakeredis.aioredis.FakeRedis()
    storage = AsyncRedisStorage(client=client)

    e1 = await storage.create_entry(
        request=Request(method="GET", url="https://example.com/1"),
        response=Response(status_code=200, stream=make_async_iterator([b"response1"])),
        key="shared_key",
        id_=uuid.UUID(int=1),
    )
    await e1.response.aread()

    e2 = await storage.create_entry(
        request=Request(method="GET", url="https://example.com/2"),
        response=Response(status_code=200, stream=make_async_iterator([b"response2"])),
        key="shared_key",
        id_=uuid.UUID(int=2),
    )
    await e2.response.aread()

    entries = await storage.get_entries("shared_key")
    assert len(entries) == 2
    assert all(entry.cache_key == b"shared_key" for entry in entries)


@pytest.mark.anyio
async def test_multiple_entries_same_key() -> None:
    """Test creating multiple entries with the same cache key."""
    client = fakeredis.aioredis.FakeRedis()
    storage = AsyncRedisStorage(client=client)

    e1 = await storage.create_entry(
        request=Request(method="GET", url="https://example.com/1"),
        response=Response(status_code=200, stream=make_async_iterator([b"response1"])),
        key="shared_key",
        id_=uuid.UUID(int=3),
    )
    await e1.response.aread()

    e2 = await storage.create_entry(
        request=Request(method="GET", url="https://example.com/2"),
        response=Response(status_code=200, stream=make_async_iterator([b"response2"])),
        key="shared_key",
        id_=uuid.UUID(int=4),
    )
    await e2.response.aread()

    entries = await storage.get_entries("shared_key")
    assert len(entries) == 2
    assert all(entry.response is not None for entry in entries)


@pytest.mark.anyio
async def test_multiple_entries_different_keys() -> None:
    """Test that entries with different keys are properly isolated."""
    client = fakeredis.aioredis.FakeRedis()
    storage = AsyncRedisStorage(client=client)

    for i in range(3):
        entry = await storage.create_entry(
            request=Request(method="GET", url=f"https://example.com/{i}"),
            response=Response(status_code=200, stream=make_async_iterator([f"data{i}".encode()])),
            key=f"key_{i}",
            id_=uuid.UUID(int=9 + i),
        )
        async for _ in entry.response._aiter_stream():
            ...

    for i in range(3):
        entries = await storage.get_entries(f"key_{i}")
        assert len(entries) == 1
        assert entries[0].request.url == f"https://example.com/{i}"


@pytest.mark.anyio
async def test_update_entry() -> None:
    """Test updating an existing entry with a callable."""
    client = fakeredis.aioredis.FakeRedis()
    storage = AsyncRedisStorage(client=client)

    entry = await storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator([b"original"])),
        key="original_key",
        id_=uuid.UUID(int=5),
    )
    await entry.response.aread()

    def updater(pair):
        return replace(pair, cache_key=b"updated_key")

    result = await storage.update_entry(entry.id, updater)
    assert result is not None
    assert result.cache_key == b"updated_key"

    entries = await storage.get_entries("updated_key")
    assert len(entries) == 1
    assert entries[0].cache_key == b"updated_key"


@pytest.mark.anyio
async def test_update_entry_with_new_entry() -> None:
    """Test updating an entry by providing a new entry directly."""
    client = fakeredis.aioredis.FakeRedis()
    storage = AsyncRedisStorage(client=client)

    entry = await storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator([b"data"])),
        key="key1",
        id_=uuid.UUID(int=6),
    )
    await entry.response.aread()

    new_entry = replace(entry, cache_key=b"key2")
    result = await storage.update_entry(entry.id, new_entry)

    assert result is not None
    assert result.cache_key == b"key2"


@pytest.mark.anyio
async def test_remove_entry() -> None:
    """Test that remove_entry hard-deletes all Redis keys for the entry."""
    client = fakeredis.aioredis.FakeRedis()
    storage = AsyncRedisStorage(client=client)

    entry = await storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator([b"data"])),
        key="test_key",
        id_=uuid.UUID(int=7),
    )
    await entry.response.aread()

    await storage.remove_entry(entry.id)

    hex_id = entry.id.hex
    assert await client.exists(f"hishel:entry:{hex_id}") == 0
    assert await client.exists(f"hishel:stream:{hex_id}") == 0
    assert await client.exists(f"hishel:stream_done:{hex_id}") == 0


@pytest.mark.anyio
async def test_stream_persistence() -> None:
    """Test that streams are properly saved and retrieved."""
    client = fakeredis.aioredis.FakeRedis()
    storage = AsyncRedisStorage(client=client)

    response_chunks = [b"resp1", b"resp2"]

    entry = await storage.create_entry(
        request=Request(method="POST", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator(response_chunks)),
        key="stream_test",
        id_=uuid.UUID(int=8),
    )

    async for _ in entry.response._aiter_stream():
        ...

    entries = await storage.get_entries("stream_test")
    assert len(entries) == 1

    retrieved_chunks = []
    async for chunk in entries[0].response._aiter_stream():
        retrieved_chunks.append(chunk)

    assert retrieved_chunks == response_chunks


@pytest.mark.anyio
async def test_remove_nonexistent_entry() -> None:
    """Test that removing a non-existent entry doesn't raise an error."""
    client = fakeredis.aioredis.FakeRedis()
    storage = AsyncRedisStorage(client=client)

    await storage.remove_entry(uuid.UUID(int=999))


@pytest.mark.anyio
async def test_update_nonexistent_entry() -> None:
    """Test that updating a non-existent entry returns None."""
    client = fakeredis.aioredis.FakeRedis()
    storage = AsyncRedisStorage(client=client)

    result = await storage.update_entry(uuid.UUID(int=999), lambda p: replace(p, cache_key=b"new_key"))
    assert result is None


@pytest.mark.anyio
async def test_close_connection() -> None:
    """Test that close() calls aclose() on the underlying async Redis client."""
    mock_client = AsyncMock()
    mock_client.aclose = AsyncMock()
    storage = AsyncRedisStorage(client=mock_client)

    await storage.close()

    mock_client.aclose.assert_awaited_once()


@pytest.mark.anyio
async def test_incomplete_entries() -> None:
    """Test that entries with an incomplete stream are excluded from get_entries."""
    client = fakeredis.aioredis.FakeRedis()
    storage = AsyncRedisStorage(client=client)

    entry = await storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator([b"chunk1", b"chunk2"])),
        key="incomplete_key",
        id_=uuid.UUID(int=10),
    )

    assert isinstance(entry.response.stream, AsyncIterator)
    await entry.response.stream.__anext__()

    entries = await storage.get_entries("incomplete_key")
    assert len(entries) == 0


@pytest.mark.anyio
async def test_expired_entries() -> None:
    """Test that entries past their TTL are excluded from get_entries."""
    client = fakeredis.aioredis.FakeRedis()
    # ttl=3600 (1h): large enough that fakeredis won't expire the key during the test,
    # but time_machine advances frozen time by 2h so the Python-level check triggers expiry.
    storage = AsyncRedisStorage(client=client, ttl=3600)

    with travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC"))):
        entry = await storage.create_entry(
            request=Request(method="GET", url="https://example.com"),
            response=Response(status_code=200, stream=make_async_iterator([b"data"])),
            key="expired_key",
            id_=uuid.UUID(int=11),
        )
        await entry.response.aread()

    with travel(datetime(2024, 1, 1, 2, 0, 0, tzinfo=ZoneInfo("UTC"))):
        entries = await storage.get_entries("expired_key")
        assert len(entries) == 0


@pytest.mark.anyio
async def test_soft_deleted_entries() -> None:
    """Test that entries marked as soft-deleted are excluded from get_entries."""
    client = fakeredis.aioredis.FakeRedis()
    storage = AsyncRedisStorage(client=client)

    entry = await storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator([b"data"])),
        key="soft_deleted_key",
        id_=uuid.UUID(int=12),
    )
    await entry.response.aread()

    await storage.update_entry(entry.id, storage.mark_pair_as_deleted)

    entries = await storage.get_entries("soft_deleted_key")
    assert len(entries) == 0


@pytest.mark.anyio
async def test_custom_ttl() -> None:
    """Test that hishel_ttl in request metadata overrides default_ttl for expiry checks."""
    client = fakeredis.aioredis.FakeRedis()
    # storage.ttl=3600 sets Redis TTL (key alive for 1h) and default Python TTL.
    # hishel_ttl=1 overrides the Python check to expire the entry sooner.
    storage = AsyncRedisStorage(client=client, ttl=3600)

    with travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC"))):
        entry = await storage.create_entry(
            request=Request(method="GET", url="https://example.com", metadata={"hishel_ttl": 1}),
            response=Response(status_code=200, stream=make_async_iterator([b"data"])),
            key="test_key",
            id_=uuid.UUID(int=13),
        )
        await entry.response.aread()

    with travel(datetime(2024, 1, 1, 0, 0, 2, tzinfo=ZoneInfo("UTC"))):
        entries = await storage.get_entries("test_key")
        assert len(entries) == 0


@pytest.mark.anyio
async def test_custom_prefix() -> None:
    """Test checking custom redis key prefix."""
    client = fakeredis.aioredis.FakeRedis()
    key_prefix = "a_key_prefix"
    storage = AsyncRedisStorage(client=client, key_prefix=key_prefix)

    entry = await storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator([b"response data"])),
        key="test_key",
        id_=uuid.UUID(int=0),
    )

    async for _ in entry.response._aiter_stream():
        ...

    hex_id = entry.id.hex
    assert await client.exists(f"{key_prefix}:entry:{hex_id}") == 1
    assert await client.exists(f"{key_prefix}:stream:{hex_id}") == 1
    assert await client.exists(f"{key_prefix}:stream_done:{hex_id}") == 1
