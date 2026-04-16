import uuid
from dataclasses import replace
from datetime import datetime
from zoneinfo import ZoneInfo

from time_machine import travel

from hishel._core._storages._sync_dict import SyncDictStorage
from hishel._core.models import Request, Response
from hishel._utils import make_sync_iterator


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_add_entry() -> None:
    """Test adding a complete entry with request and response."""
    storage = SyncDictStorage()

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"response data"])),
        key="test_key",
        id_=uuid.UUID(int=0),
    )

    assert entry.id == uuid.UUID(int=0)
    assert entry.cache_key == b"test_key"
    assert entry.request.method == "GET"
    assert entry.request.url == "https://example.com"
    assert entry.response.status_code == 200


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_add_entry_with_stream() -> None:
    """Test adding an entry with a multi-chunk streaming response."""
    storage = SyncDictStorage()

    entry = storage.create_entry(
        request=Request(method="POST", url="https://example.com/upload"),
        response=Response(status_code=200, stream=make_sync_iterator([b"chunk1", b"chunk2"])),
        key="stream_key",
        id_=uuid.UUID(int=0),
    )

    assert entry.cache_key == b"stream_key"

    chunks = list(entry.response._iter_stream())
    assert chunks == [b"chunk1", b"chunk2"]


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_get_entries() -> None:
    """Test retrieving entries by cache key."""
    storage = SyncDictStorage()

    e1 = storage.create_entry(
        request=Request(method="GET", url="https://example.com/1"),
        response=Response(status_code=200, stream=make_sync_iterator([b"response1"])),
        key="shared_key",
        id_=uuid.UUID(int=1),
    )
    e2 = storage.create_entry(
        request=Request(method="GET", url="https://example.com/2"),
        response=Response(status_code=200, stream=make_sync_iterator([b"response2"])),
        key="shared_key",
        id_=uuid.UUID(int=2),
    )

    entries = storage.get_entries("shared_key")
    assert len(entries) == 2
    assert all(entry.cache_key == b"shared_key" for entry in entries)
    assert {e.id for e in entries} == {e1.id, e2.id}


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_get_entries_empty_key() -> None:
    """Test retrieving entries for an unknown key returns an empty list."""
    storage = SyncDictStorage()

    entries = storage.get_entries("nonexistent_key")
    assert entries == []


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_update_entry() -> None:
    """Test updating an existing entry with a callable."""
    storage = SyncDictStorage()

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"original"])),
        key="original_key",
        id_=uuid.UUID(int=5),
    )

    result = storage.update_entry(entry.id, lambda e: replace(e, cache_key=b"updated_key"))

    assert result is not None
    assert result.cache_key == b"updated_key"

    entries = storage.get_entries("updated_key")
    assert len(entries) == 1
    assert entries[0].cache_key == b"updated_key"

    # Old key should no longer return this entry
    assert storage.get_entries("original_key") == []


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_update_entry_with_new_entry() -> None:
    """Test updating an entry by providing a new entry object directly."""
    storage = SyncDictStorage()

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
        key="key1",
        id_=uuid.UUID(int=6),
    )

    new_entry = replace(entry, cache_key=b"key2")
    result = storage.update_entry(entry.id, new_entry)

    assert result is not None
    assert result.cache_key == b"key2"

    assert len(storage.get_entries("key2")) == 1
    assert storage.get_entries("key1") == []


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_update_nonexistent_entry() -> None:
    """Test that updating a non-existent entry returns None."""
    storage = SyncDictStorage()

    result = storage.update_entry(uuid.UUID(int=999), lambda e: replace(e, cache_key=b"new_key"))
    assert result is None


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_remove_entry() -> None:
    """Test hard-deleting an entry."""
    storage = SyncDictStorage()

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
        key="test_key",
        id_=uuid.UUID(int=7),
    )

    storage.remove_entry(entry.id)

    assert storage.get_entries("test_key") == []


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_remove_nonexistent_entry() -> None:
    """Test that removing a non-existent entry does not raise."""
    storage = SyncDictStorage()

    # Should not raise
    storage.remove_entry(uuid.UUID(int=999))


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_multiple_entries_same_key() -> None:
    """Test creating multiple entries under the same cache key."""
    storage = SyncDictStorage()

    for i in range(3):
        storage.create_entry(
            request=Request(method="GET", url=f"https://example.com/{i}"),
            response=Response(status_code=200, stream=make_sync_iterator([f"data{i}".encode()])),
            key="shared_key",
            id_=uuid.UUID(int=i),
        )

    entries = storage.get_entries("shared_key")
    assert len(entries) == 3
    assert all(e.cache_key == b"shared_key" for e in entries)


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_multiple_entries_different_keys() -> None:
    """Test that entries with different keys are properly isolated."""
    storage = SyncDictStorage()

    for i in range(3):
        storage.create_entry(
            request=Request(method="GET", url=f"https://example.com/{i}"),
            response=Response(status_code=200, stream=make_sync_iterator([f"data{i}".encode()])),
            key=f"key_{i}",
            id_=uuid.UUID(int=9 + i),
        )

    for i in range(3):
        entries = storage.get_entries(f"key_{i}")
        assert len(entries) == 1
        assert entries[0].request.url == f"https://example.com/{i}"


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_autogenerated_id() -> None:
    """Test that a UUID is auto-generated when no id_ is provided."""
    storage = SyncDictStorage()

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
        key="test_key",
    )

    assert isinstance(entry.id, uuid.UUID)


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")))
def test_not_threadsafe() -> None:
    """Test that threadsafe=False initializes correctly and still works."""
    storage = SyncDictStorage(threadsafe=False)

    entry = storage.create_entry(
        request=Request(method="GET", url="https://example.com"),
        response=Response(status_code=200, stream=make_sync_iterator([b"data"])),
        key="test_key",
        id_=uuid.UUID(int=0),
    )

    entries = storage.get_entries("test_key")
    assert len(entries) == 1
    assert entries[0].id == entry.id
