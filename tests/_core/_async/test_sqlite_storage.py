import uuid
from dataclasses import replace
from datetime import datetime
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import anysqlite
import pytest
from inline_snapshot import snapshot
from time_machine import travel

from hishel import AsyncSqliteStorage, Request, Response
from hishel._utils import make_async_iterator
from tests.conftest import aprint_sqlite_state


@pytest.mark.anyio
async def test_custom_connection_does_not_create_directory() -> None:
    """Test that providing a custom connection doesn't call ensure_cache_dict."""
    with patch("hishel._core._storages._async_sqlite.ensure_cache_dict") as mock_ensure:
        storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))
        # Create an entry to trigger _ensure_connection
        entry = await storage.create_entry(
            request=Request(method="GET", url="https://example.com"),
            response=Response(status_code=200, stream=make_async_iterator([b"data"])),
            key="test_key",
        )
        # Consume the stream
        await entry.response.aread()
        # ensure_cache_dict should still not have been called
        mock_ensure.assert_not_called()


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_add_entry() -> None:
    """Test adding a complete entry with request and response."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

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
    async for _ in entry.response._aiter_stream():
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
async def test_add_entry_with_stream() -> None:
    """Test adding an entry with a streaming response body."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

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
    async for _ in entry.response._aiter_stream():
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
async def test_get_entries() -> None:
    """Test retrieving entries by cache key."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

    # Create two entries with the same cache key
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

    # Retrieve entries
    entries = await storage.get_entries("shared_key")
    assert len(entries) == 2
    assert all(entry.cache_key == b"shared_key" for entry in entries)


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_multiple_entries_same_key() -> None:
    """Test creating multiple entries with the same cache key."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

    # Create multiple complete entries with the same key
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

    # Should return both complete entries
    entries = await storage.get_entries("shared_key")
    assert len(entries) == 2
    assert all(entry.response is not None for entry in entries)


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_update_entry() -> None:
    """Test updating an existing entry."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

    entry = await storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator([b"original"])),
        key="original_key",
        id_=uuid.UUID(int=5),
    )

    await entry.response.aread()

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
async def test_update_entry_with_new_entry() -> None:
    """Test updating an entry by providing a new entry directly."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

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
async def test_remove_entry() -> None:
    """Test soft-deleting an entry."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

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
async def test_stream_persistence() -> None:
    """Test that streams are properly saved and retrieved."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

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

    async for _ in entry.response._aiter_stream():
        ...

    # Retrieve and verify streams
    entries = await storage.get_entries("stream_test")
    assert len(entries) == 1

    retrieved_response_chunks = []
    async for chunk in entries[0].response._aiter_stream():
        retrieved_response_chunks.append(chunk)

    assert retrieved_response_chunks == response_chunks


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_multiple_entries_different_keys() -> None:
    """Test that entries with different keys are properly isolated."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

    # Create entries with different keys
    for i in range(3):
        entry = await storage.create_entry(
            request=Request(method="GET", url=f"https://example.com/{i}"),
            response=Response(
                status_code=200,
                stream=make_async_iterator([f"data{i}".encode()]),
            ),
            key=f"key_{i}",
            id_=uuid.UUID(int=9 + i),
        )

        # Consume the stream to save it
        async for _ in entry.response._aiter_stream():
            ...

    # Verify each key returns only its own entry
    for i in range(3):
        entries = await storage.get_entries(f"key_{i}")
        assert len(entries) == 1
        assert entries[0].request.url == f"https://example.com/{i}"


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_remove_nonexistent_entry() -> None:
    """Test that removing a non-existent entry doesn't raise an error."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

    # Should not raise
    await storage.remove_entry(uuid.UUID(int=999))


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_update_nonexistent_entry() -> None:
    """Test that updating a non-existent entry returns None."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

    result = await storage.update_entry(uuid.UUID(int=999), lambda p: replace(p, cache_key=b"new_key"))
    assert result is None


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_close_connection(monkeypatch: Any) -> None:
    """Test that close() properly closes the underlying SQLite connection."""

    mock_connection = AsyncMock()
    mock_connection.close = AsyncMock()

    async def mock_connect(*args, **kwargs):
        return mock_connection

    monkeypatch.setattr("anysqlite.connect", mock_connect)

    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

    conn = await storage._ensure_connection()
    assert conn is not None
    assert storage.connection is not None
    assert storage.connection is mock_connection

    await storage.close()

    assert storage.connection is None

    mock_connection.close.assert_awaited_once()


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
async def test_incomplete_entries() -> None:
    """Test incomplete entries"""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

    entry = await storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator([b"chunk1", b"chunk2"])),
        key="incomplete_key",
        id_=uuid.UUID(int=10),
    )

    # read only part of the stream
    assert isinstance(entry.response.stream, AsyncIterator)
    await entry.response.stream.__anext__()

    # Verify the entry was created but is incomplete, so get_entries should skip it
    entries = await storage.get_entries("incomplete_key")

    assert len(entries) == 0

    assert await aprint_sqlite_state(await storage._ensure_connection()) == snapshot("""\
================================================================================
DATABASE SNAPSHOT
================================================================================

TABLE: entries
--------------------------------------------------------------------------------
Rows: 1

  Row 1:
    id              = (bytes) 0x0000000000000000000000000000000a (16 bytes)
    cache_key       = (str) 'incomplete_key'
    data            = (bytes) 0x85a26964c4100000000000000000000000000000000aa772657175657374... (186 bytes)
    created_at      = 2024-01-01
    deleted_at      = NULL

TABLE: streams
--------------------------------------------------------------------------------
Rows: 1

  Row 1:
    entry_id        = (bytes) 0x0000000000000000000000000000000a (16 bytes)
    chunk_number    = 0
    chunk_data      = (str) 'chunk1'

================================================================================\
""")


@pytest.mark.anyio
async def test_expired_entries() -> None:
    """Test expired entries"""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"), default_ttl=0)

    entry = await storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator([b"data"])),
        key="expired_key",
        id_=uuid.UUID(int=11),
    )

    await entry.response.aread()

    # Verify the entry is expired, so get_entries should skip it
    entries = await storage.get_entries("expired_key")
    assert len(entries) == 0


@pytest.mark.anyio
async def test_soft_deleted_entries() -> None:
    """Test soft-deleted entries"""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

    entry = await storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_async_iterator([b"data"])),
        key="soft_deleted_key",
        id_=uuid.UUID(int=12),
    )

    await entry.response.aread()

    # Soft delete the entry
    await storage.remove_entry(entry.id)

    # Verify the entry is soft deleted, so get_entries should skip it
    entries = await storage.get_entries("soft_deleted_key")
    assert len(entries) == 0
