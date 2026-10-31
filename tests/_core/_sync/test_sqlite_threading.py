import hashlib
import sqlite3
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from time_machine import travel

from hishel import (
    Request,
    Response,
    SyncSqliteStorage,
)
from hishel._core._storages._sync_sqlite import STORAGE_CHUNK_SIZE

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
URL = "https://x/"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def at(seconds):
    return travel(START + timedelta(seconds=seconds), tick=False)


def key_for(url=URL):
    return hashlib.sha256(url.encode()).hexdigest()


# Sync SQLite threading


def read(entry):
    return b"".join(entry.response.stream)


def store(storage, key, body):
    entry = storage.create_entry(
        Request(method="GET", url="https://example.com"),
        Response(status_code=200, stream=iter([body])),
        key,
    )
    return read(entry)


def test_one_storage_used_from_many_threads(tmp_path):
    storage = SyncSqliteStorage(database_path=tmp_path / "c.db")
    body = b"x" * (STORAGE_CHUNK_SIZE + 10)

    def work(i):
        assert store(storage, f"k{i % 5}", body) == body
        for entry in storage.get_entries(f"k{i % 5}"):
            assert read(entry) == body
            storage.update_headers(entry.id, entry.response.headers)

    with ThreadPoolExecutor(16) as pool:
        list(pool.map(work, range(200)))
    assert sum(len(storage.get_entries(f"k{i}")) for i in range(5)) == 200
    storage.close()


def test_stream_read_from_another_thread(tmp_path):
    storage = SyncSqliteStorage(database_path=tmp_path / "c.db")
    store(storage, "k", b"data")
    [entry] = storage.get_entries("k")
    result = []
    thread = threading.Thread(target=lambda: result.append(read(entry)))
    thread.start()
    thread.join()
    assert result == [b"data"]
    storage.close()


def test_two_storages_sharing_a_file_from_threads(tmp_path):
    path = tmp_path / "shared.db"
    first, second = SyncSqliteStorage(database_path=path), SyncSqliteStorage(database_path=path)
    first.get_entries("init")
    second.get_entries("init")
    body = b"x" * (STORAGE_CHUNK_SIZE + 10)

    def work(i):
        store(first if i % 2 else second, f"k{i}", body)

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(work, range(100)))
    for i in range(100):
        [entry] = (second if i % 2 else first).get_entries(f"k{i}")
        assert read(entry) == body
    first.close()
    second.close()


def test_warns_about_connection_bound_to_its_thread():
    with pytest.warns(UserWarning, match="check_same_thread"):
        SyncSqliteStorage(connection=sqlite3.connect(":memory:"))
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        SyncSqliteStorage(connection=sqlite3.connect(":memory:", check_same_thread=False))


def test_close_stops_lingering_stream(tmp_path):
    storage = SyncSqliteStorage(database_path=tmp_path / "c.db")
    store(storage, "k", b"data")
    [entry] = storage.get_entries("k")
    storage.close()
    with pytest.raises(RuntimeError, match="closed"):
        read(entry)

