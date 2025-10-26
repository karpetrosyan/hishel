import uuid
from dataclasses import replace
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from inline_snapshot import snapshot
from time_machine import travel

from hishel import AsyncSqliteStorage, Request, Response
from hishel._utils import make_async_iterator
from tests.conftest import aprint_sqlite_state


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_add_entry(use_temp_dir: Any) -> None:
    """Test adding a complete entry with request and response."""
    storage = AsyncSqliteStorage()

    entry = await storage.create_entry(
        request=Request(
            method="GET",
            url="https://example.com",
        ),
        response=Response(
            status_code=200,
            stream=make_async_iterator([b"response data"]),
        ),
        key="test_key",
        id_=uuid.UUID(int=0),
    )

    # Consume the stream to save it
    async for _ in entry.response.aiter_stream():
        ...

    conn = await storage._ensure_connection()
    assert await aprint_sqlite_state(conn) == snapshot("""\
================================================================================
DATABASE SNAPSHOT
================================================================================

TABLE: entries
--------------------------------------------------------------------------------
Rows: 1

  Row 1:
    id              = (bytes) 0x00000000000000000000000000000000 (16 bytes)
    cache_key       = (str) 'test_key'
    data            = (bytes) 0x85a26964c41000000000000000000000000000000000a772657175657374... (180 bytes)
    created_at      = 2024-01-01
    deleted_at      = NULL

TABLE: streams
--------------------------------------------------------------------------------
Rows: 2

  Row 1:
    entry_id        = (bytes) 0x00000000000000000000000000000000 (16 bytes)
    chunk_number    = 0
    chunk_data      = (str) 'response data'

  Row 2:
    entry_id        = (bytes) 0x00000000000000000000000000000000 (16 bytes)
    chunk_number    = -1
    chunk_data      = (str) ''

================================================================================\
""")


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_add_entry_with_stream(use_temp_dir: Any) -> None:
    """Test adding an entry with a streaming response body."""
    storage = AsyncSqliteStorage()

    entry = await storage.create_entry(
        request=Request(
            method="POST",
            url="https://example.com/upload",
        ),
        response=Response(
            status_code=200,
            stream=make_async_iterator([b"chunk1", b"chunk2"]),
        ),
        key="stream_key",
        id_=uuid.UUID(int=0),
    )

    # Consume the stream
    async for _ in entry.response.aiter_stream():
        ...

    # Verify the entry was created with cache_key set
    conn = await storage._ensure_connection()
    assert await aprint_sqlite_state(conn) == snapshot("""\
================================================================================
DATABASE SNAPSHOT
================================================================================

TABLE: entries
--------------------------------------------------------------------------------
Rows: 1

  Row 1:
    id              = (bytes) 0x00000000000000000000000000000000 (16 bytes)
    cache_key       = (str) 'stream_key'
    data            = (bytes) 0x85a26964c41000000000000000000000000000000000a772657175657374... (190 bytes)
    created_at      = 2024-01-01
    deleted_at      = NULL

TABLE: streams
--------------------------------------------------------------------------------
Rows: 3

  Row 1:
    entry_id        = (bytes) 0x00000000000000000000000000000000 (16 bytes)
    chunk_number    = 0
    chunk_data      = (str) 'chunk1'

  Row 2:
    entry_id        = (bytes) 0x00000000000000000000000000000000 (16 bytes)
    chunk_number    = 1
    chunk_data      = (str) 'chunk2'

  Row 3:
    entry_id        = (bytes) 0x00000000000000000000000000000000 (16 bytes)
    chunk_number    = -1
    chunk_data      = (str) ''

================================================================================\
""")


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_get_entries(use_temp_dir: Any) -> None:
    """Test retrieving entries by cache key."""
    storage = AsyncSqliteStorage()

    # Create two entries with the same cache key
    await storage.create_entry(
        request=Request(method="GET", url="https://example.com/1"),
        response=Response(status_code=200, stream=make_async_iterator([b"response1"])),
        key="shared_key",
        id_=uuid.UUID(int=1),
    )

    await storage.create_entry(
        request=Request(method="GET", url="https://example.com/2"),
        response=Response(status_code=200, stream=make_async_iterator([b"response2"])),
        key="shared_key",
        id_=uuid.UUID(int=2),
    )

    # Retrieve entries
    entries = await storage.get_entries("shared_key")
    assert len(entries) == 2
    assert all(entry.cache_key == b"shared_key" for entry in entries)


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_multiple_entries_same_key(use_temp_dir: Any) -> None:
    """Test creating multiple entries with the same cache key."""
    storage = AsyncSqliteStorage()

    # Create multiple complete entries with the same key
    await storage.create_entry(
        request=Request(method="GET", url="https://example.com/1"),
        response=Response(status_code=200, stream=make_async_iterator([b"response1"])),
        key="shared_key",
        id_=uuid.UUID(int=3),
    )

    await storage.create_entry(
        request=Request(method="GET", url="https://example.com/2"),
        response=Response(status_code=200, stream=make_async_iterator([b"response2"])),
        key="shared_key",
        id_=uuid.UUID(int=4),
    )

    # Should return both complete entries
    entries = await storage.get_entries("shared_key")
    assert len(entries) == 2
    assert all(entry.response is not None for entry in entries)


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_update_entry(use_temp_dir: Any) -> None:
    """Test updating an existing entry."""
    storage = AsyncSqliteStorage()

    entry = await storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator([b"original"])),
        key="original_key",
        id_=uuid.UUID(int=5),
    )

    # Update with a callable
    def updater(pair):
        return replace(pair, cache_key=b"updated_key")

    result = await storage.update_entry(entry.id, updater)
    assert result is not None
    assert result.cache_key == b"updated_key"

    # Verify the update persisted
    entries = await storage.get_entries("updated_key")
    assert len(entries) == 1
    assert entries[0].cache_key == b"updated_key"


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_update_entry_with_new_entry(use_temp_dir: Any) -> None:
    """Test updating an entry by providing a new entry directly."""
    storage = AsyncSqliteStorage()

    entry = await storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator([b"data"])),
        key="key1",
        id_=uuid.UUID(int=6),
    )

    # Update with a new entry object
    new_entry = replace(entry, cache_key=b"key2")
    result = await storage.update_entry(entry.id, new_entry)

    assert result is not None
    assert result.cache_key == b"key2"


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_remove_entry(use_temp_dir: Any) -> None:
    """Test soft-deleting an entry."""
    storage = AsyncSqliteStorage()

    entry = await storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator([b"data"])),
        key="test_key",
        id_=uuid.UUID(int=7),
    )

    # Remove the entry
    await storage.remove_entry(entry.id)

    # Verify deleted_at is set
    conn = await storage._ensure_connection()
    cursor = await conn.cursor()
    await cursor.execute("SELECT deleted_at FROM entries WHERE id = ?", (entry.id.bytes,))
    result = await cursor.fetchone()
    assert result is not None
    assert result[0] is not None  # deleted_at should be set


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_stream_persistence(use_temp_dir: Any) -> None:
    """Test that streams are properly saved and retrieved."""
    storage = AsyncSqliteStorage()

    response_chunks = [b"resp1", b"resp2"]

    entry = await storage.create_entry(
        request=Request(
            method="POST",
            url="https://example.com",
        ),
        response=Response(status_code=200, stream=make_async_iterator(response_chunks)),
        key="stream_test",
        id_=uuid.UUID(int=8),
    )

    async for _ in entry.response.aiter_stream():
        ...

    # Retrieve and verify streams
    entries = await storage.get_entries("stream_test")
    assert len(entries) == 1

    retrieved_response_chunks = []
    async for chunk in entries[0].response.aiter_stream():
        retrieved_response_chunks.append(chunk)

    assert retrieved_response_chunks == response_chunks


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_multiple_entries_different_keys(use_temp_dir: Any) -> None:
    """Test that entries with different keys are properly isolated."""
    storage = AsyncSqliteStorage()

    # Create entries with different keys
    for i in range(3):
        await storage.create_entry(
            request=Request(method="GET", url=f"https://example.com/{i}"),
            response=Response(
                status_code=200,
                stream=make_async_iterator([f"data{i}".encode()]),
            ),
            key=f"key_{i}",
            id_=uuid.UUID(int=9 + i),
        )

    # Verify each key returns only its own entry
    for i in range(3):
        entries = await storage.get_entries(f"key_{i}")
        assert len(entries) == 1
        assert entries[0].request.url == f"https://example.com/{i}"


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_remove_nonexistent_entry(use_temp_dir: Any) -> None:
    """Test that removing a non-existent entry doesn't raise an error."""
    storage = AsyncSqliteStorage()

    # Should not raise
    await storage.remove_entry(uuid.UUID(int=999))


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_update_nonexistent_entry(use_temp_dir: Any) -> None:
    """Test that updating a non-existent entry returns None."""
    storage = AsyncSqliteStorage()

    result = await storage.update_entry(uuid.UUID(int=999), lambda p: replace(p, cache_key=b"new_key"))
    assert result is None
