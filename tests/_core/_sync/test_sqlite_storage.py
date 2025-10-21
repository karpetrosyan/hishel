import uuid
from dataclasses import replace
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from inline_snapshot import snapshot
from time_machine import travel

from hishel import SyncSqliteStorage, Request, Response
from hishel._utils import make_sync_iterator
from tests.conftest import print_sqlite_state



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_create_pair(use_temp_dir: Any) -> None:
    storage = SyncSqliteStorage()

    storage.create_pair(
        id=uuid.UUID(int=0),
        request=Request(
            method="GET",
            url="https://example.com",
        ),
    )

    conn = storage._ensure_connection()
    assert print_sqlite_state(conn) == snapshot("""\
================================================================================
DATABASE SNAPSHOT
================================================================================

TABLE: entries
--------------------------------------------------------------------------------
Rows: 1

  Row 1:
    id              = (bytes) 0x00000000000000000000000000000000 (16 bytes)
    cache_key       = NULL
    data            = (bytes) 0x84a26964c41000000000000000000000000000000000a772657175657374... (130 bytes)
    created_at      = 2024-01-01
    deleted_at      = NULL

TABLE: streams
--------------------------------------------------------------------------------
Rows: 0

  (empty)

================================================================================\
""")



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_create_pair_with_stream(use_temp_dir: Any) -> None:
    """Test creating a pair with a streaming request body."""
    storage = SyncSqliteStorage()

    pair_id = uuid.UUID(int=1)
    incomplete_pair = storage.create_pair(
        id=pair_id,
        request=Request(
            method="POST",
            url="https://example.com/upload",
            stream=make_sync_iterator([b"chunk1", b"chunk2"]),
        ),
    )

    for _ in incomplete_pair.request.iter_stream():
        ...

    # Verify the pair was created with cache_key = NULL
    conn = storage._ensure_connection()
    assert print_sqlite_state(conn) == snapshot("""\
================================================================================
DATABASE SNAPSHOT
================================================================================

TABLE: entries
--------------------------------------------------------------------------------
Rows: 1

  Row 1:
    id              = (bytes) 0x00000000000000000000000000000001 (16 bytes)
    cache_key       = NULL
    data            = (bytes) 0x84a26964c41000000000000000000000000000000001a772657175657374... (138 bytes)
    created_at      = 2024-01-01
    deleted_at      = NULL

TABLE: streams
--------------------------------------------------------------------------------
Rows: 3

  Row 1:
    entry_id        = (bytes) 0x00000000000000000000000000000001 (16 bytes)
    kind            = 0
    chunk_number    = 0
    chunk_data      = (str) 'chunk1'

  Row 2:
    entry_id        = (bytes) 0x00000000000000000000000000000001 (16 bytes)
    kind            = 0
    chunk_number    = 1
    chunk_data      = (str) 'chunk2'

  Row 3:
    entry_id        = (bytes) 0x00000000000000000000000000000001 (16 bytes)
    kind            = 0
    chunk_number    = -1
    chunk_data      = (str) ''

================================================================================\
""")



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_add_response(use_temp_dir: Any) -> None:
    """Test adding a response to an existing pair."""
    storage = SyncSqliteStorage()

    pair_id = uuid.UUID(int=2)
    inc_pair = storage.create_pair(
        id=pair_id,
        request=Request(
            method="GET",
            url="https://example.com/api",
        ),
    )

    for _ in inc_pair.request.iter_stream():
        ...

    comp_pair = storage.add_response(
        pair_id=pair_id,
        response=Response(
            status_code=200,
            stream=make_sync_iterator([b"response data"]),
        ),
        key="test_key",
    )

    for _ in comp_pair.response.iter_stream():
        ...

    # Verify cache_key is now set and response is added
    conn = storage._ensure_connection()
    assert print_sqlite_state(conn) == snapshot("""\
================================================================================
DATABASE SNAPSHOT
================================================================================

TABLE: entries
--------------------------------------------------------------------------------
Rows: 1

  Row 1:
    id              = (bytes) 0x00000000000000000000000000000002 (16 bytes)
    cache_key       = (str) 'test_key'
    data            = (bytes) 0x85a26964c41000000000000000000000000000000002a772657175657374... (184 bytes)
    created_at      = 2024-01-01
    deleted_at      = NULL

TABLE: streams
--------------------------------------------------------------------------------
Rows: 3

  Row 1:
    entry_id        = (bytes) 0x00000000000000000000000000000002 (16 bytes)
    kind            = 0
    chunk_number    = -1
    chunk_data      = (str) ''

  Row 2:
    entry_id        = (bytes) 0x00000000000000000000000000000002 (16 bytes)
    kind            = 1
    chunk_number    = 0
    chunk_data      = (str) 'response data'

  Row 3:
    entry_id        = (bytes) 0x00000000000000000000000000000002 (16 bytes)
    kind            = 1
    chunk_number    = -1
    chunk_data      = (str) ''

================================================================================\
""")



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_get_pairs(use_temp_dir: Any) -> None:
    """Test retrieving pairs by cache key."""
    storage = SyncSqliteStorage()

    # Create two pairs with the same cache key
    pair_id_1 = uuid.UUID(int=3)
    storage.create_pair(
        id=pair_id_1,
        request=Request(method="GET", url="https://example.com/1"),
    )
    storage.add_response(
        pair_id=pair_id_1,
        response=Response(status_code=200, stream=make_sync_iterator([b"response1"])),
        key="shared_key",
    )

    pair_id_2 = uuid.UUID(int=4)
    storage.create_pair(
        id=pair_id_2,
        request=Request(method="GET", url="https://example.com/2"),
    )
    storage.add_response(
        pair_id=pair_id_2,
        response=Response(status_code=200, stream=make_sync_iterator([b"response2"])),
        key="shared_key",
    )

    # Retrieve pairs
    pairs = storage.get_pairs("shared_key")
    assert len(pairs) == 2
    assert all(pair.cache_key == b"shared_key" for pair in pairs)



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_get_pairs_filters_incomplete(use_temp_dir: Any) -> None:
    """Test that get_pairs filters out incomplete pairs."""
    storage = SyncSqliteStorage()

    # Create a complete pair
    complete_id = uuid.UUID(int=5)
    storage.create_pair(
        id=complete_id,
        request=Request(method="GET", url="https://example.com/complete"),
    )
    storage.add_response(
        pair_id=complete_id,
        response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
        key="test_key",
    )

    # Create an incomplete pair with the same key (shouldn't be returned)
    incomplete_id = uuid.UUID(int=6)
    storage.create_pair(
        id=incomplete_id,
        request=Request(method="GET", url="https://example.com/incomplete"),
    )
    # Update cache_key manually without adding response
    conn = storage._ensure_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE entries SET cache_key = ? WHERE id = ?", (b"test_key", incomplete_id.bytes))
    conn.commit()

    # Should only return the complete pair
    pairs = storage.get_pairs("test_key")
    assert len(pairs) == 1
    assert pairs[0].id == complete_id



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_update_pair(use_temp_dir: Any) -> None:
    """Test updating an existing pair."""
    storage = SyncSqliteStorage()

    pair_id = uuid.UUID(int=7)
    storage.create_pair(
        id=pair_id,
        request=Request(method="GET", url="https://example.com"),
    )
    storage.add_response(
        pair_id=pair_id,
        response=Response(status_code=200, stream=make_sync_iterator([b"original"])),
        key="original_key",
    )

    # Update with a callable
    def updater(pair):
        return replace(pair, cache_key=b"updated_key")

    result = storage.update_pair(pair_id, updater)
    assert result is not None
    assert result.cache_key == b"updated_key"

    # Verify the update persisted
    pairs = storage.get_pairs("updated_key")
    assert len(pairs) == 1
    assert pairs[0].cache_key == b"updated_key"



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_update_pair_with_new_pair(use_temp_dir: Any) -> None:
    """Test updating a pair by providing a new pair directly."""
    storage = SyncSqliteStorage()

    pair_id = uuid.UUID(int=8)
    storage.create_pair(
        id=pair_id,
        request=Request(method="GET", url="https://example.com"),
    )
    complete_pair = storage.add_response(
        pair_id=pair_id,
        response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
        key="key1",
    )

    # Update with a new pair object
    new_pair = replace(complete_pair, cache_key=b"key2")
    result = storage.update_pair(pair_id, new_pair)

    assert result is not None
    assert result.cache_key == b"key2"



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_remove_pair(use_temp_dir: Any) -> None:
    """Test soft-deleting a pair."""
    storage = SyncSqliteStorage()

    pair_id = uuid.UUID(int=9)
    storage.create_pair(
        id=pair_id,
        request=Request(method="GET", url="https://example.com"),
    )
    storage.add_response(
        pair_id=pair_id,
        response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
        key="test_key",
    )

    # Remove the pair
    storage.remove(pair_id)

    # Verify deleted_at is set
    conn = storage._ensure_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT deleted_at FROM entries WHERE id = ?", (pair_id.bytes,))
    result = cursor.fetchone()
    assert result is not None
    assert result[0] is not None  # deleted_at should be set



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_stream_persistence(use_temp_dir: Any) -> None:
    """Test that streams are properly saved and retrieved."""
    storage = SyncSqliteStorage()

    pair_id = uuid.UUID(int=10)
    request_chunks = [b"req1", b"req2", b"req3"]
    response_chunks = [b"resp1", b"resp2"]

    inc_pair = storage.create_pair(
        id=pair_id,
        request=Request(
            method="POST",
            url="https://example.com",
            stream=make_sync_iterator(request_chunks),
        ),
    )

    for _ in inc_pair.request.iter_stream():
        ...

    cmp_pair = storage.add_response(
        pair_id=pair_id,
        response=Response(status_code=200, stream=make_sync_iterator(response_chunks)),
        key="stream_test",
    )

    for _ in cmp_pair.response.iter_stream():
        ...

    # Retrieve and verify streams
    pairs = storage.get_pairs("stream_test")
    assert len(pairs) == 1

    retrieved_request_chunks = []
    for chunk in pairs[0].request.iter_stream():
        retrieved_request_chunks.append(chunk)

    retrieved_response_chunks = []
    for chunk in pairs[0].response.iter_stream():
        retrieved_response_chunks.append(chunk)

    assert retrieved_request_chunks == request_chunks
    assert retrieved_response_chunks == response_chunks



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_multiple_pairs_different_keys(use_temp_dir: Any) -> None:
    """Test that pairs with different keys are properly isolated."""
    storage = SyncSqliteStorage()

    # Create pairs with different keys
    for i in range(3):
        pair_id = uuid.UUID(int=100 + i)
        storage.create_pair(
            id=pair_id,
            request=Request(method="GET", url=f"https://example.com/{i}"),
        )
        storage.add_response(
            pair_id=pair_id,
            response=Response(status_code=200, stream=make_sync_iterator([f"data{i}".encode()])),
            key=f"key_{i}",
        )

    # Verify each key returns only its own pair
    for i in range(3):
        pairs = storage.get_pairs(f"key_{i}")
        assert len(pairs) == 1
        assert pairs[0].request.url == f"https://example.com/{i}"



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_remove_nonexistent_pair(use_temp_dir: Any) -> None:
    """Test that removing a non-existent pair doesn't raise an error."""
    storage = SyncSqliteStorage()

    # Should not raise
    storage.remove(uuid.UUID(int=999))



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_update_nonexistent_pair(use_temp_dir: Any) -> None:
    """Test that updating a non-existent pair returns None."""
    storage = SyncSqliteStorage()

    result = storage.update_pair(uuid.UUID(int=999), lambda p: replace(p, cache_key=b"new_key"))
    assert result is None



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_add_response_to_nonexistent_pair(use_temp_dir: Any) -> None:
    """Test that adding a response to non-existent pair raises an error."""
    storage = SyncSqliteStorage()

    try:
        storage.add_response(
            pair_id=uuid.UUID(int=999),
            response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
            key="test_key",
        )
        assert False, "Expected ValueError"
    except ValueError as e:
        assert "not found" in str(e)
