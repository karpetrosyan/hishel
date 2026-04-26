from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime
from typing import Iterator
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import fakeredis
import pytest
from time_machine import travel

from hishel import Request, Response
from hishel._core._storages._sync_redis import RedisStorage
from hishel._utils import make_sync_iterator


@pytest.fixture
def anyio_backend() -> str:
    # redis is asyncio-only; restrict async tests to asyncio backend
    return "asyncio"


def test_add_entry() -> None:
    """Test adding a complete entry with request and response."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"response data"])),
        key="test_key",
        id_=uuid.UUID(int=0),
    )

    for _ in entry.response._iter_stream():
        ...

    entries = storage.get_entries("test_key")
    assert len(entries) == 1
    assert entries[0].cache_key == b"test_key"


def test_add_entry_with_stream() -> None:
    """Test adding an entry with a multi-chunk streaming response body."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    entry = storage.create_entry(
        request=Request(method="POST", url="https://example.com/upload"),
        response=Response(status_code=200, stream=make_sync_iterator([b"chunk1", b"chunk2"])),
        key="stream_key",
        id_=uuid.UUID(int=0),
    )

    for _ in entry.response._iter_stream():
        ...

    entries = storage.get_entries("stream_key")
    assert len(entries) == 1
    assert entries[0].cache_key == b"stream_key"


def test_get_entries() -> None:
    """Test retrieving entries by cache key."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    e1 = storage.create_entry(
        request=Request(method="GET", url="https://example.com/1"),
        response=Response(status_code=200, stream=make_sync_iterator([b"response1"])),
        key="shared_key",
        id_=uuid.UUID(int=1),
    )
    e1.response.read()

    e2 = storage.create_entry(
        request=Request(method="GET", url="https://example.com/2"),
        response=Response(status_code=200, stream=make_sync_iterator([b"response2"])),
        key="shared_key",
        id_=uuid.UUID(int=2),
    )
    e2.response.read()

    entries = storage.get_entries("shared_key")
    assert len(entries) == 2
    assert all(entry.cache_key == b"shared_key" for entry in entries)


def test_multiple_entries_same_key() -> None:
    """Test creating multiple entries with the same cache key."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    e1 = storage.create_entry(
        request=Request(method="GET", url="https://example.com/1"),
        response=Response(status_code=200, stream=make_sync_iterator([b"response1"])),
        key="shared_key",
        id_=uuid.UUID(int=3),
    )
    e1.response.read()

    e2 = storage.create_entry(
        request=Request(method="GET", url="https://example.com/2"),
        response=Response(status_code=200, stream=make_sync_iterator([b"response2"])),
        key="shared_key",
        id_=uuid.UUID(int=4),
    )
    e2.response.read()

    entries = storage.get_entries("shared_key")
    assert len(entries) == 2
    assert all(entry.response is not None for entry in entries)


def test_multiple_entries_different_keys() -> None:
    """Test that entries with different keys are properly isolated."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    for i in range(3):
        entry = storage.create_entry(
            request=Request(method="GET", url=f"https://example.com/{i}"),
            response=Response(status_code=200, stream=make_sync_iterator([f"data{i}".encode()])),
            key=f"key_{i}",
            id_=uuid.UUID(int=9 + i),
        )
        for _ in entry.response._iter_stream():
            ...

    for i in range(3):
        entries = storage.get_entries(f"key_{i}")
        assert len(entries) == 1
        assert entries[0].request.url == f"https://example.com/{i}"


def test_update_entry() -> None:
    """Test updating an existing entry with a callable."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"original"])),
        key="original_key",
        id_=uuid.UUID(int=5),
    )
    entry.response.read()

    def updater(pair):
        return replace(pair, cache_key=b"updated_key")

    result = storage.update_entry(entry.id, updater)
    assert result is not None
    assert result.cache_key == b"updated_key"

    entries = storage.get_entries("updated_key")
    assert len(entries) == 1
    assert entries[0].cache_key == b"updated_key"


def test_update_entry_with_new_entry() -> None:
    """Test updating an entry by providing a new entry directly."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
        key="key1",
        id_=uuid.UUID(int=6),
    )
    entry.response.read()

    new_entry = replace(entry, cache_key=b"key2")
    result = storage.update_entry(entry.id, new_entry)

    assert result is not None
    assert result.cache_key == b"key2"


def test_update_entry_preserves_ttl() -> None:
    """Test that update_entry preserves the remaining Redis TTL rather than refreshing it."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    with travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC"))):
        entry = storage.create_entry(
            request=Request(method="GET", url="https://example.com", metadata={"hishel_ttl": 60}),
            response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
            key="test_key",
            id_=uuid.UUID(int=15),
        )
        entry.response.read()

    # Advance 30s — half the effective TTL consumed.
    # Safe TTL was (60 + 180) * 1000 = 240_000 ms; ~210_000 ms should remain.
    with travel(datetime(2024, 1, 1, 0, 0, 30, tzinfo=ZoneInfo("UTC"))):
        storage.update_entry(
            entry.id,
            lambda e: replace(e, cache_key=b"renamed_key"),
        )
        pttl = client.pttl(f"hishel:entry:{entry.id.hex}")
        # Should be roughly 210s remaining, definitely not reset to the full 240s
        assert 200_000 < pttl < 220_000


def test_refresh_entry_ttl() -> None:
    """Test that refresh_entry_ttl resets all key TTLs to the full safe TTL."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client, soft_delete_ttl=180)

    with travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC"))):
        entry = storage.create_entry(
            request=Request(method="GET", url="https://example.com", metadata={"hishel_ttl": 60}),
            response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
            key="test_key",
            id_=uuid.UUID(int=15),
        )
        entry.response.read()

    # Advance 30s — half the effective TTL consumed.
    with travel(datetime(2024, 1, 1, 0, 0, 30, tzinfo=ZoneInfo("UTC"))):
        storage.refresh_entry_ttl(entry.id)

        hex_id = entry.id.hex
        # Safe TTL = (60 + 180) * 1000 = 240_000 ms; all four keys should be reset to it.
        for suffix in ("entry", "stream", "stream_done"):
            pttl = client.pttl(f"hishel:{suffix}:{hex_id}")
            assert 230_000 < pttl <= 240_000, f"key {suffix} not refreshed (pttl={pttl})"

        idx_pttl = client.pttl("hishel:idx:test_key")
        assert 230_000 < idx_pttl <= 240_000


def test_refresh_nonexistent_entry_ttl() -> None:
    """Test that refresh_entry_ttl on a missing entry is a no-op."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    # Should not raise
    storage.refresh_entry_ttl(uuid.UUID(int=999))


def test_remove_entry() -> None:
    """Test that remove_entry soft-deletes the entry and hides it from get_entries."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
        key="test_key",
        id_=uuid.UUID(int=7),
    )
    entry.response.read()

    storage.remove_entry(entry.id)

    hex_id = entry.id.hex
    # Keys still exist (soft delete, not hard delete)
    assert client.exists(f"hishel:entry:{hex_id}") == 1
    # TTL on the entry key has been shrunk to soft_delete_ttl (default 180s)
    assert 0 < client.ttl(f"hishel:entry:{hex_id}") <= 180
    # Soft-deleted entry is invisible to get_entries
    assert storage.get_entries("test_key") == []


def test_remove_entry_custom_soft_delete_ttl() -> None:
    """Test that a custom soft_delete_ttl is applied to Redis keys after remove_entry."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client, soft_delete_ttl=60)

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
        key="test_key",
        id_=uuid.UUID(int=70),
    )
    entry.response.read()

    storage.remove_entry(entry.id)

    hex_id = entry.id.hex
    assert 0 < client.ttl(f"hishel:entry:{hex_id}") <= 60


def test_stream_persistence() -> None:
    """Test that streams are properly saved and retrieved."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    response_chunks = [b"resp1", b"resp2"]

    entry = storage.create_entry(
        request=Request(method="POST", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator(response_chunks)),
        key="stream_test",
        id_=uuid.UUID(int=8),
    )

    for _ in entry.response._iter_stream():
        ...

    entries = storage.get_entries("stream_test")
    assert len(entries) == 1

    retrieved_chunks = []
    for chunk in entries[0].response._iter_stream():
        retrieved_chunks.append(chunk)

    assert retrieved_chunks == response_chunks


def test_remove_nonexistent_entry() -> None:
    """Test that removing a non-existent entry doesn't raise an error."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    storage.remove_entry(uuid.UUID(int=999))


def test_update_nonexistent_entry() -> None:
    """Test that updating a non-existent entry returns None."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    result = storage.update_entry(uuid.UUID(int=999), lambda p: replace(p, cache_key=b"new_key"))
    assert result is None


def test_close_connection() -> None:
    """Test that close() calls close() on the underlying async Redis client."""
    mock_client = MagicMock()
    mock_client.close = MagicMock()
    storage = RedisStorage(client=mock_client)

    storage.close()

    mock_client.close.assert_called_once()


def test_incomplete_entries() -> None:
    """Test that entries with an incomplete stream are excluded from get_entries."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"chunk1", b"chunk2"])),
        key="incomplete_key",
        id_=uuid.UUID(int=10),
    )

    assert isinstance(entry.response.stream, Iterator)
    entry.response.stream.__next__()

    entries = storage.get_entries("incomplete_key")
    assert len(entries) == 0


def test_soft_deleted_entries() -> None:
    """Test that entries marked as soft-deleted are excluded from get_entries."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client)

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
        key="soft_deleted_key",
        id_=uuid.UUID(int=12),
    )
    entry.response.read()

    storage.update_entry(entry.id, storage.mark_pair_as_deleted)

    entries = storage.get_entries("soft_deleted_key")
    assert len(entries) == 0


def test_custom_ttl() -> None:
    """Test that hishel_ttl in request metadata overrides default_ttl for expiry checks."""
    client = fakeredis.FakeRedis()
    # storage.ttl=3600 sets the default. hishel_ttl=1 overrides it to expire the entry sooner.
    storage = RedisStorage(client=client, ttl=3600)

    with travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC"))):
        entry = storage.create_entry(
            request=Request(method="GET", url="https://example.com", metadata={"hishel_ttl": 1}),
            response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
            key="test_key",
            id_=uuid.UUID(int=13),
        )
        entry.response.read()

    with travel(datetime(2024, 1, 1, 0, 0, 2, tzinfo=ZoneInfo("UTC"))):
        entries = storage.get_entries("test_key")
        assert len(entries) == 0


def test_hishel_ttl_sets_redis_key_expiry() -> None:
    """Test that hishel_ttl sets the Redis key TTL to effective_ttl + soft_delete_ttl."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client, soft_delete_ttl=180)

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com", metadata={"hishel_ttl": 42}),
        response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
        key="test_key",
        id_=uuid.UUID(int=14),
    )
    entry.response.read()

    hex_id = entry.id.hex
    entry_pttl = client.pttl(f"hishel:entry:{hex_id}")
    assert isinstance(entry_pttl, int)
    # Safe TTL = (42 + 180) * 1000 = 222_000 ms
    assert 0 < entry_pttl <= 222_000
    # And it should be meaningfully larger than the bare effective TTL,
    # confirming the soft-delete buffer is being applied.
    assert entry_pttl > 42_000


def test_max_stream_size_aborts_caching() -> None:
    """Test that exceeding max_stream_size drops partial stream data and skips caching."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client, max_stream_size=8)

    response_chunks = [b"chunk1", b"chunk2", b"chunk3"]
    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator(response_chunks)),
        key="oversized_key",
        id_=uuid.UUID(int=0),
    )

    yielded = list(entry.response._iter_stream())
    assert yielded == response_chunks

    hex_id = entry.id.hex
    assert client.exists(f"hishel:stream:{hex_id}") == 0
    assert client.exists(f"hishel:stream_done:{hex_id}") == 0
    assert storage.get_entries("oversized_key") == []


def test_max_stream_size_within_limit_caches_normally() -> None:
    """Test that streams within max_stream_size are cached as usual."""
    client = fakeredis.FakeRedis()
    storage = RedisStorage(client=client, max_stream_size=64)

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"small", b"data"])),
        key="ok_key",
        id_=uuid.UUID(int=0),
    )
    entry.response.read()

    entries = storage.get_entries("ok_key")
    assert len(entries) == 1


def test_custom_prefix() -> None:
    """Test checking custom redis key prefix."""
    client = fakeredis.FakeRedis()
    key_prefix = "a_key_prefix"
    storage = RedisStorage(client=client, key_prefix=key_prefix)

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"response data"])),
        key="test_key",
        id_=uuid.UUID(int=0),
    )

    for _ in entry.response._iter_stream():
        ...

    hex_id = entry.id.hex
    assert client.exists(f"{key_prefix}:entry:{hex_id}") == 1
    assert client.exists(f"{key_prefix}:stream:{hex_id}") == 1
    assert client.exists(f"{key_prefix}:stream_done:{hex_id}") == 1
