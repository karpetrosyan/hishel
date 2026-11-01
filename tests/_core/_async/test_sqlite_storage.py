import logging
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone

import anysqlite
import pytest
from time_machine import travel

from hishel import Headers
from hishel._core._storages._async_sqlite import STORAGE_CHUNK_SIZE, AsyncSqliteStorage
from hishel._core.models import Request, Response
from hishel._utils import make_async_iterator

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def at(seconds):
    return travel(START + timedelta(seconds=seconds), tick=False)


async def new_storage(**kwargs):
    return AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"), **kwargs)


def req():
    return Request(method="GET", url="https://example.com")


async def store(storage, key="k", body=b"data", request=None, **limits):
    entry = await storage.create_entry(
        request or req(), Response(status_code=200, stream=make_async_iterator([body])), key, **limits
    )
    await read(entry)
    return entry


async def read(entry):
    return b"".join([chunk async for chunk in entry.response.stream])


async def rows(storage):
    conn = await storage._ensure_connection()
    cur = await conn.cursor()
    await cur.execute("SELECT COUNT(*) FROM entries")
    return (await cur.fetchone())[0]


async def chunk_rows(storage):
    conn = await storage._ensure_connection()
    cur = await conn.cursor()
    await cur.execute("SELECT COUNT(*) FROM streams")
    return (await cur.fetchone())[0]


@pytest.mark.anyio
async def test_round_trip_rechunks_and_returns_exact_body():
    storage = await new_storage()
    body = b"x" * (STORAGE_CHUNK_SIZE * 2 + 5)
    await store(storage, body=body)
    [entry] = await storage.get_entries("k")
    assert await read(entry) == body
    assert await chunk_rows(storage) == 3


@pytest.mark.anyio
async def test_empty_body():
    storage = await new_storage()
    await store(storage, body=b"")
    [entry] = await storage.get_entries("k")
    assert await read(entry) == b""


@pytest.mark.anyio
async def test_incomplete_entry_is_invisible_until_stream_finishes():
    storage = await new_storage()
    entry = await storage.create_entry(req(), Response(status_code=200, stream=make_async_iterator([b"a", b"b"])), "k")
    assert await storage.get_entries("k") == []
    await read(entry)
    assert len(await storage.get_entries("k")) == 1


@pytest.mark.anyio
async def test_ttl_hides_then_next_write_deletes():
    storage = await new_storage(default_ttl=100)
    with at(0):
        await store(storage)
    with at(99):
        assert len(await storage.get_entries("k")) == 1
    with at(101):
        assert await storage.get_entries("k") == []
        await store(storage, key="other")
        assert await rows(storage) == 2  # expired, but returned at 99 so still within grace
    with at(400):
        await store(storage, key="other2")
        assert await storage.get_entries("k") == []
        conn = await storage._ensure_connection()
        cur = await conn.cursor()
        await cur.execute("SELECT COUNT(*) FROM entries WHERE cache_key = ?", (b"k",))
        assert (await cur.fetchone())[0] == 0
    assert await chunk_rows(storage) == 1  # "other" expired and went cold too; only other2 is left


@pytest.mark.anyio
async def test_tti_extends_on_read_and_expires_when_idle():
    storage = await new_storage(default_tti=100)
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
async def test_ttl_caps_tti():
    storage = await new_storage(default_ttl=200, default_tti=100)
    with at(0):
        await store(storage)
    for t in (80, 160):
        with at(t):
            assert len(await storage.get_entries("k")) == 1
    with at(201):
        assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_values_passed_to_create_entry_override_defaults_and_are_stored():
    storage = await new_storage(default_ttl=1000, default_tti=1000)
    with at(0):
        await store(storage, ttl=500, tti=100)
    with at(99):
        [entry] = await storage.get_entries("k")
        assert len(await storage.get_entries("k")) == 1
    with at(250):
        assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_defaults_apply_only_to_entries_created_under_them(tmp_path):
    path = tmp_path / "cache.db"
    first = AsyncSqliteStorage(database_path=path, default_tti=100)
    with at(0):
        await store(first)
    await first.close()

    second = AsyncSqliteStorage(database_path=path, default_tti=1000)
    with at(90):
        assert len(await second.get_entries("k")) == 1
    with at(250):
        assert await second.get_entries("k") == []
    await second.close()


@pytest.mark.anyio
async def test_update_headers_keeps_limits():
    storage = await new_storage()
    with at(0):
        entry = await store(storage, ttl=100, tti=50)
        await storage.update_headers(entry.id, Headers({"etag": "new"}))
    with at(40):
        assert len(await storage.get_entries("k")) == 1
    with at(80):
        assert len(await storage.get_entries("k")) == 1
    with at(101):
        assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_frequent_reads_do_not_write():
    storage = await new_storage()
    with at(0):
        await store(storage)
    with at(10):
        calls = []
        original = storage._try_write

        async def spy(sql, params):
            calls.append(sql)
            return await original(sql, params)

        storage._try_write = spy
        await storage.get_entries("k")
        assert calls == []
    with at(61):
        await storage.get_entries("k")
        assert len(calls) == 1


@pytest.mark.anyio
async def test_remove_hides_immediately_and_is_deleted_after_grace():
    storage = await new_storage()
    with at(0):
        entry = await store(storage)
        await storage.remove_entry(entry.id)
        assert await storage.get_entries("k") == []
    with at(100):
        await store(storage, key="x")
        assert await rows(storage) == 2
    with at(181):
        await store(storage, key="y")
        assert await rows(storage) == 2  # removed row gone, x and y left


@pytest.mark.anyio
async def test_remove_racing_with_lookup_touch_stays_removed():
    storage = await new_storage(default_tti=100)
    with at(0):
        entry = await store(storage)
    with at(90):
        original = storage._try_write

        async def remove_first(sql, params):
            await storage.remove_entry(entry.id)
            return await original(sql, params)

        storage._try_write = remove_first
        await storage.get_entries("k")
        storage._try_write = original
        assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_remove_during_write_stays_removed_and_consumer_is_served(caplog):
    storage = await new_storage()
    chunks = [b"x" * STORAGE_CHUNK_SIZE] * 3
    entry = await storage.create_entry(req(), Response(status_code=200, stream=make_async_iterator(chunks)), "k")
    stream = entry.response.stream
    received = [await stream.__anext__()]
    await storage.remove_entry(entry.id)
    with caplog.at_level(logging.CRITICAL):
        async for chunk in stream:
            received.append(chunk)
    assert b"".join(received) == b"".join(chunks)
    assert await storage.get_entries("k") == []
    assert await rows(storage) == 0


@pytest.mark.anyio
async def test_reader_heartbeat_does_not_stop_tti_extension():
    storage = await new_storage(default_tti=100)
    with at(0):
        await store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 2))
        [entry] = await storage.get_entries("k")
    stream = entry.response.stream
    with at(70):
        await stream.__anext__()  # updates last_accessed_at only
    with at(80):
        assert len(await storage.get_entries("k")) == 1  # must still extend to 180
    with at(150):
        assert len(await storage.get_entries("k")) == 1


@pytest.mark.anyio
async def test_remove_and_update_missing_entry_are_noops():
    storage = await new_storage()
    await storage.remove_entry(uuid.uuid4())
    await storage.update_headers(uuid.uuid4(), Headers({"a": "b"}))


@pytest.mark.anyio
async def test_update_headers():
    storage = await new_storage()
    entry = await store(storage)
    await storage.update_headers(entry.id, Headers({"etag": "new"}))
    [got] = await storage.get_entries("k")
    assert got.response.headers["etag"] == "new"
    assert await read(got) == b"data"


@pytest.mark.anyio
async def test_lookup_of_read_entry_protects_from_cleanup_for_grace():
    storage = await new_storage(default_ttl=300)
    with at(0):
        await store(storage)
    with at(299):
        [entry] = await storage.get_entries("k")
    with at(320):  # expired, but read 21s ago
        await store(storage, key="x")
        assert await read(entry) == b"data"


@pytest.mark.anyio
async def test_lru_evicts_least_recently_used_and_stops_when_it_fits():
    body = b"x" * STORAGE_CHUNK_SIZE
    storage = await new_storage(max_size=2_000_000)
    for i in range(10):
        with at(i * 1000):
            await store(storage, key=f"k{i}", body=body)
    size = await storage._database_size(await (await storage._ensure_connection()).cursor())
    count = await rows(storage)
    assert size <= 2_000_000 + 2 * STORAGE_CHUNK_SIZE
    assert count >= 5, f"over-evicted: {count}"

    # Protect k9-ish: read the oldest survivor, then force evictions
    with at(100_000):
        survivors = []
        for i in range(10):
            if await storage.get_entries(f"k{i}"):
                survivors.append(i)
        oldest = survivors[0]
    with at(100_500):
        await storage.get_entries(f"k{oldest}")
    with at(100_700):
        for i in range(10, 13):
            await store(storage, key=f"k{i}", body=body)
        assert await storage.get_entries(f"k{oldest}") != []


@pytest.mark.anyio
async def test_database_stays_near_limit_over_many_writes():
    body = b"x" * 50_000
    storage = await new_storage(max_size=1_000_000)
    for i in range(300):
        with at(i * 500):
            await store(storage, key=f"k{i}", body=body)
        size = await storage._database_size(await (await storage._ensure_connection()).cursor())
        assert size <= 1_000_000 + 200_000, f"at write {i}: {size}"


@pytest.mark.anyio
async def test_cache_full_of_recently_used_entries_stops_storing_but_serves():
    body = b"x" * 400_000
    storage = await new_storage(max_size=1_000_000)
    with at(0):
        await store(storage, key="a", body=body)
        await store(storage, key="b", body=body)
        await store(storage, key="c", body=body)
    with at(1):
        before = await rows(storage)
        entry = await storage.create_entry(req(), Response(status_code=200, stream=make_async_iterator([body])), "d")
        assert await read(entry) == body
        assert await rows(storage) == before
        assert await storage.get_entries("d") == []
    # Becomes evictable once the grace period passes
    with at(500):
        await store(storage, key="d", body=body)
        assert len(await storage.get_entries("d")) == 1


@pytest.mark.anyio
async def test_reader_raises_when_entry_deleted_mid_read():
    storage = await new_storage()
    await store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 3))
    [entry] = await storage.get_entries("k")
    stream = entry.response.stream
    await stream.__anext__()
    conn = await storage._ensure_connection()
    await conn.execute("DELETE FROM entries")
    await conn.commit()
    with pytest.raises(RuntimeError, match="deleted while"):
        async for _ in stream:
            pass


@pytest.mark.anyio
async def test_active_slow_reader_survives_cleanup_and_eviction():
    storage = await new_storage(default_ttl=100)
    with at(0):
        await store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 8))
        [entry] = await storage.get_entries("k")
    stream = entry.response.stream
    total = 0
    for i in range(8):
        with at(i * 100):  # spans 700s, well past TTL and grace
            total += len(await stream.__anext__())
            await store(storage, key=f"other{i}")
    assert total == STORAGE_CHUNK_SIZE * 8


@pytest.mark.anyio
async def test_reader_starting_late_within_grace_refreshes_protection():
    storage = await new_storage(default_ttl=100)
    with at(0):
        await store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 2))
        [entry] = await storage.get_entries("k")
    stream = entry.response.stream
    with at(170):
        await stream.__anext__()
    with at(300):  # expired and 300s after lookup, but only 130s after reading
        await store(storage, key="o")
        await stream.__anext__()


@pytest.mark.anyio
async def test_stalled_reader_past_grace_raises_instead_of_truncating():
    storage = await new_storage(default_ttl=100)
    with at(0):
        await store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 2))
        [entry] = await storage.get_entries("k")
    stream = entry.response.stream
    with at(1):
        await stream.__anext__()
    with at(1000):
        await store(storage, key="o")
        with pytest.raises(RuntimeError, match="deleted while"):
            await stream.__anext__()


@pytest.mark.anyio
async def test_slow_writer_is_not_treated_as_abandoned():
    storage = await new_storage()
    with at(0):
        entry = await storage.create_entry(
            req(),
            Response(status_code=200, stream=make_async_iterator([b"x" * STORAGE_CHUNK_SIZE] * 6)),
            "k",
        )
    stream = entry.response.stream
    for i in range(6):
        with at(i * 150):
            await stream.__anext__()
            await store(storage, key=f"o{i}")
    with at(900), pytest.raises(StopAsyncIteration):
        await stream.__anext__()
    with at(900):
        [got] = await storage.get_entries("k")
        assert len(await read(got)) == STORAGE_CHUNK_SIZE * 6


@pytest.mark.anyio
async def test_abandoned_stream_discards_partial_data_immediately():
    storage = await new_storage()
    entry = await storage.create_entry(
        req(),
        Response(status_code=200, stream=make_async_iterator([b"x" * STORAGE_CHUNK_SIZE] * 3)),
        "k",
    )
    stream = entry.response.stream
    await stream.__anext__()
    await stream.__anext__()
    assert await rows(storage) == 1
    await stream.aclose()
    assert await rows(storage) == 0
    assert await chunk_rows(storage) == 0


@pytest.mark.anyio
async def test_crashed_writer_is_removed_after_grace():
    storage = await new_storage()
    with at(0):
        entry = await storage.create_entry(
            req(),
            Response(status_code=200, stream=make_async_iterator([b"x" * STORAGE_CHUNK_SIZE] * 2)),
            "k",
        )
        await entry.response.stream.__anext__()
    with at(100):
        await store(storage, key="o")
        assert await rows(storage) == 2
    with at(181):
        await store(storage, key="p")
        assert await rows(storage) == 2  # crashed row gone, o and p left
        assert await chunk_rows(storage) == 2


@pytest.mark.anyio
async def test_upstream_failure_discards_and_propagates():
    async def boom():
        yield b"x" * STORAGE_CHUNK_SIZE
        raise ValueError("upstream")

    storage = await new_storage()
    entry = await storage.create_entry(req(), Response(status_code=200, stream=boom()), "k")
    with pytest.raises(ValueError):
        await read(entry)
    assert await rows(storage) == 0


@pytest.mark.anyio
@pytest.mark.parametrize("kwargs", [{"max_stream_size": 1000}, {"max_size": 1000}])
async def test_too_big_response_is_not_cached_but_fully_delivered(kwargs):
    storage = await new_storage(**kwargs)
    chunks = [b"x" * 700] * 5
    entry = await storage.create_entry(req(), Response(status_code=200, stream=make_async_iterator(chunks)), "k")
    assert await read(entry) == b"".join(chunks)
    assert await storage.get_entries("k") == []
    assert await rows(storage) == 0


@pytest.mark.anyio
async def test_storage_failure_mid_stream_does_not_fail_consumer(caplog):
    storage = await new_storage()
    chunks = [b"x" * STORAGE_CHUNK_SIZE] * 4
    entry = await storage.create_entry(req(), Response(status_code=200, stream=make_async_iterator(chunks)), "k")
    stream = entry.response.stream
    received = [await stream.__anext__()]
    # Row vanishes under the writer: the next insert violates the foreign key
    conn = await storage._ensure_connection()
    await conn.execute("DELETE FROM entries")
    await conn.commit()
    with caplog.at_level(logging.CRITICAL):
        async for chunk in stream:
            received.append(chunk)
    assert b"".join(received) == b"".join(chunks)
    assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_create_entry_failure_serves_uncached():
    storage = await new_storage()
    await storage._ensure_connection()

    async def broken(*args):
        raise sqlite3.OperationalError("disk full")

    storage._reclaim_space = broken
    entry = await storage.create_entry(req(), Response(status_code=200, stream=make_async_iterator([b"data"])), "k")
    assert await read(entry) == b"data"
    assert await rows(storage) == 0


@pytest.mark.anyio
async def test_corrupt_row_does_not_break_lookup_or_cleanup():
    storage = await new_storage()
    with at(0):
        await store(storage)
        await store(storage)
        conn = await storage._ensure_connection()
        cur = await conn.cursor()
        await cur.execute("SELECT id FROM entries LIMIT 1")
        bad = (await cur.fetchone())[0]
        await cur.execute("UPDATE entries SET data = ? WHERE id = ?", (b"\xc1garbage", bad))
        await conn.commit()
        assert len(await storage.get_entries("k")) == 1
    with at(200):
        await store(storage, key="o")
        assert await rows(storage) == 2
        assert len(await storage.get_entries("k")) == 1


@pytest.mark.anyio
async def test_closed_storage_raises_and_does_not_reopen():
    storage = await new_storage()
    await store(storage)
    await storage.close()
    with pytest.raises(RuntimeError, match="closed"):
        await storage.get_entries("k")
    assert storage.connection is None


def create_v1_database(path):
    """The schema hishel 1.x created, which has no `user_version`."""
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE entries (id BLOB PRIMARY KEY, cache_key BLOB, data BLOB NOT NULL,"
        " created_at REAL NOT NULL, deleted_at REAL)"
    )
    conn.execute(
        "CREATE TABLE streams (entry_id BLOB NOT NULL, chunk_number INTEGER NOT NULL, chunk_data BLOB NOT NULL,"
        " PRIMARY KEY (entry_id, chunk_number), FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE)"
    )
    for i in range(20):
        entry_id = uuid.uuid4().bytes
        conn.execute("INSERT INTO entries VALUES (?, ?, ?, ?, NULL)", (entry_id, f"k{i}".encode(), b"", 0.0))
        conn.execute("INSERT INTO streams VALUES (?, 0, ?)", (entry_id, b"x" * 500_000))
    conn.commit()
    conn.close()


@pytest.mark.anyio
async def test_old_database_is_refused_and_left_untouched(tmp_path):
    path = tmp_path / "cache.db"
    create_v1_database(path)
    before = path.read_bytes()

    storage = AsyncSqliteStorage(database_path=path)
    with pytest.raises(RuntimeError, match="Hishel 1.x"):
        await storage.get_entries("k0")
    with pytest.raises(RuntimeError, match="Hishel 1.x"):
        await store(storage)
    await storage.close()

    assert path.read_bytes() == before


@pytest.mark.anyio
async def test_default_path_leaves_a_1x_cache_alone(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    old = tmp_path / ".cache" / "hishel" / "hishel_cache.db"
    old.parent.mkdir(parents=True)
    create_v1_database(old)
    before = old.read_bytes()

    storage = AsyncSqliteStorage()
    await store(storage)
    assert len(await storage.get_entries("k")) == 1
    await storage.close()

    assert old.read_bytes() == before


@pytest.mark.anyio
async def test_connection_with_tables_of_its_own_is_left_untouched():
    connection = await anysqlite.connect(":memory:")
    await connection.execute("CREATE TABLE entries (name TEXT)")
    await connection.execute("INSERT INTO entries VALUES ('mine')")
    await connection.execute("PRAGMA user_version=7")
    await connection.commit()

    storage = AsyncSqliteStorage(connection=connection)
    with pytest.raises(RuntimeError, match="connection"):
        await storage.get_entries("k")

    cursor = await connection.execute("SELECT name FROM entries")
    assert await cursor.fetchall() == [("mine",)]
    cursor = await connection.execute("PRAGMA user_version")
    assert await cursor.fetchall() == [(7,)]
    cursor = await connection.execute("PRAGMA table_info(streams)")
    assert await cursor.fetchall() == []


@pytest.mark.anyio
async def test_connection_keeps_its_user_version():
    connection = await anysqlite.connect(":memory:")
    await connection.execute("PRAGMA user_version=7")
    storage = AsyncSqliteStorage(connection=connection)
    await store(storage)
    cursor = await connection.execute("PRAGMA user_version")
    assert await cursor.fetchall() == [(7,)]


@pytest.mark.anyio
async def test_reopening_a_database_keeps_its_entries(tmp_path):
    path = tmp_path / "cache.db"
    first = AsyncSqliteStorage(database_path=path)
    await store(first)
    await first.close()

    again = AsyncSqliteStorage(database_path=path)
    assert len(await again.get_entries("k")) == 1
    await again.close()


class FlakyCursor:
    def __init__(self, cursor, connection):
        self._cursor = cursor
        self._connection = connection

    async def execute(self, sql, *args):
        if "journal_mode" in sql:
            self._connection.wal_attempts += 1
            if self._connection.wal_attempts <= self._connection.failures:
                raise sqlite3.OperationalError(self._connection.message)
        return await self._cursor.execute(sql, *args)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class FlakyConnection:
    """Fails the switch to WAL a given number of times, which is hard to trigger for real in one process."""

    def __init__(self, connection, failures, message="database is locked"):
        self._connection = connection
        self.failures = failures
        self.message = message
        self.wal_attempts = 0

    async def cursor(self):
        return FlakyCursor(await self._connection.cursor(), self)

    def __getattr__(self, name):
        return getattr(self._connection, name)


@pytest.mark.anyio
async def test_switch_to_wal_retries_while_locked():
    connection = FlakyConnection(await anysqlite.connect(":memory:"), failures=3)
    storage = AsyncSqliteStorage(connection=connection)  # type: ignore[arg-type]
    await store(storage)
    assert connection.wal_attempts == 4
    assert len(await storage.get_entries("k")) == 1


@pytest.mark.anyio
async def test_switch_to_wal_gives_up_and_tries_again_on_the_next_use(monkeypatch, caplog):
    monkeypatch.setattr("hishel._core._storages._async_sqlite.WAL_RETRY_SECONDS", 0.05)
    connection = FlakyConnection(await anysqlite.connect(":memory:"), failures=10**9)
    storage = AsyncSqliteStorage(connection=connection)  # type: ignore[arg-type]
    with caplog.at_level(logging.CRITICAL):
        assert await storage.get_entries("k") == []

    connection.failures = 0
    await store(storage)
    assert len(await storage.get_entries("k")) == 1


@pytest.mark.anyio
async def test_switch_to_wal_only_retries_locks(caplog):
    connection = FlakyConnection(await anysqlite.connect(":memory:"), failures=1, message="disk I/O error")
    storage = AsyncSqliteStorage(connection=connection)  # type: ignore[arg-type]
    with caplog.at_level(logging.CRITICAL):
        assert await storage.get_entries("k") == []
    assert connection.wal_attempts == 1


@pytest.mark.anyio
async def test_database_failures_do_not_fail_the_caller(caplog):
    storage = await new_storage()
    entry = await store(storage)

    async def broken():
        raise sqlite3.OperationalError("database is locked")

    storage._ensure_connection = broken
    with caplog.at_level(logging.CRITICAL):
        assert await storage.get_entries("k") == []
        await storage.update_headers(entry.id, Headers({"x": "1"}))
        await storage.remove_entry(entry.id)
        created = await storage.create_entry(req(), Response(status_code=200, stream=make_async_iterator([b"d"])), "k")
        without_body = await storage.create_entry(req(), Response(status_code=204), "k")
    assert await read(created) == b"d"
    assert await read(without_body) == b""


@pytest.mark.anyio
async def test_queries_use_indexes():
    storage = await new_storage()
    conn = await storage._ensure_connection()
    cur = await conn.cursor()

    async def plan(sql, params):
        await cur.execute("EXPLAIN QUERY PLAN " + sql, params)
        return " | ".join(r[3] for r in await cur.fetchall())

    cleanup = await plan("SELECT id FROM entries WHERE expires_at < ? AND last_accessed_at < ? LIMIT ?", (1.0, 1.0, 1))
    assert "USING INDEX idx_entries_expires_at" in cleanup or "USING INDEX idx_entries_last_accessed_at" in cleanup
    print("cleanup:", cleanup)
    evict = await plan("SELECT id FROM entries WHERE last_accessed_at < ? ORDER BY last_accessed_at LIMIT ?", (1.0, 1))
    assert "idx_entries_last_accessed_at" in evict and "TEMP B-TREE" not in evict
    print("evict:", evict)
    lookup = await plan(
        "SELECT id, data, chunk_count, last_accessed_at FROM entries"
        " WHERE cache_key = ? AND (expires_at IS NULL OR expires_at > ?)",
        (b"k", 1.0),
    )
    assert "idx_entries_cache_key" in lookup
    print("lookup:", lookup)
    await conn.execute("SELECT 1")


@pytest.mark.anyio
async def test_cost_with_100k_entries(tmp_path, capsys):
    from hishel._core._storages._packing import pack
    from hishel._core.models import Entry

    storage = AsyncSqliteStorage(database_path=tmp_path / "bench.db", max_size=None)
    conn = await storage._ensure_connection()
    now = time.time()
    template = Entry(
        id=uuid.uuid4(),
        request=req(),
        response=Response(status_code=200, headers=Headers({f"x-{i}": "v" * 40 for i in range(15)})),
    )

    entries, streams = [], []
    for i in range(100_000):
        id_ = uuid.uuid4()
        key = f"key-{i}".encode()
        entries.append((id_.bytes, key, pack(template.request, template.response), None, now, 1, None, None))
        streams.append((id_.bytes, 0, b"x" * 10_000))
    await conn.executemany("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?)", entries)
    await conn.executemany("INSERT INTO streams VALUES (?,?,?)", streams)
    await conn.commit()

    t = time.perf_counter()
    for _ in range(200):
        await storage._reclaim_space(conn, now)
    no_work = (time.perf_counter() - t) / 200 * 1000

    storage.max_size = 2 * 1024**3
    t = time.perf_counter()
    for _ in range(200):
        await storage._reclaim_space(conn, now)
    with_size_check = (time.perf_counter() - t) / 200 * 1000

    t = time.perf_counter()
    for i in range(200):
        await store(storage, key=f"new-{i}", body=b"x" * 10_000)
    create = (time.perf_counter() - t) / 200 * 1000
    assert len(await storage.get_entries("new-0")) == 1

    t = time.perf_counter()
    for i in range(1000):
        await storage.get_entries(f"key-{i}")
    lookup = (time.perf_counter() - t) / 1000 * 1000

    # Everything expires and goes cold at once: one batch's cost.
    await conn.execute("UPDATE entries SET expires_at = 1, last_accessed_at = 1")
    await conn.commit()
    t = time.perf_counter()
    await storage._reclaim_space(conn, now)
    batch = (time.perf_counter() - t) * 1000
    with capsys.disabled():
        print(
            f"\n100k entries: cleanup no-op {no_work:.3f} ms, +size check {with_size_check:.3f} ms, "
            f"create+store {create:.3f} ms, get_entries {lookup:.3f} ms, delete batch of 200 {batch:.1f} ms"
        )
    await storage.close()


@pytest.mark.anyio
async def test_ttl_counts_from_when_entry_was_stored_not_when_body_finished():
    storage = await new_storage()
    with at(0):
        entry = await storage.create_entry(
            req(), Response(status_code=200, stream=make_async_iterator([b"a"])), "k", ttl=100
        )
    with at(60):
        await read(entry)
    with at(99):
        assert len(await storage.get_entries("k")) == 1
    with at(101):
        assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_entries_get_their_id_and_key_from_the_row_not_the_blob():
    from hishel._core._storages._packing import unpack

    storage = await new_storage()
    entry = await store(storage, key="some-key")
    [got] = await storage.get_entries("some-key")
    assert got.id == entry.id
    conn = await storage._ensure_connection()
    cur = await conn.cursor()
    await cur.execute("SELECT data FROM entries")
    blob = (await cur.fetchone())[0]
    assert entry.id.bytes not in blob and b"some-key" not in blob
    assert unpack(bytes(blob))[1].status_code == 200


@pytest.mark.anyio
async def test_response_without_a_stream_is_stored_with_an_empty_body():
    storage = await new_storage()
    entry = await storage.create_entry(req(), Response(status_code=204), "k")
    assert await read(entry) == b""
    [got] = await storage.get_entries("k")
    assert got.response.status_code == 204
    assert await read(got) == b""


@pytest.mark.anyio
async def test_eviction_between_select_and_touch_is_a_miss_not_an_error():
    storage = await new_storage()
    with at(0):
        await store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 2))
    with at(1000):
        original = storage._try_write

        async def evict_first(sql, params):
            conn = await storage._ensure_connection()
            await conn.execute("DELETE FROM entries")
            await conn.commit()
            return await original(sql, params)

        storage._try_write = evict_first
        assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_only_the_evicted_entry_is_skipped():
    storage = await new_storage()
    with at(0):
        evicted = await store(storage, body=b"gone")
        await store(storage, body=b"kept")
    with at(1000):
        original = storage._try_write
        calls: list[str] = []

        async def evict_on_first_touch(sql, params):
            if not calls:
                calls.append(sql)
                conn = await storage._ensure_connection()
                await conn.execute("DELETE FROM entries WHERE id = ?", (params[2],))
                await conn.commit()
            return await original(sql, params)

        storage._try_write = evict_on_first_touch
        entries = await storage.get_entries("k")
    storage._try_write = original
    assert len(entries) == 1
    assert evicted.id.bytes != b""
    assert await read(entries[0]) in (b"gone", b"kept")


@pytest.mark.anyio
async def test_removal_between_select_and_touch_is_a_miss():
    storage = await new_storage(default_tti=100)
    with at(0):
        entry = await store(storage)
    with at(90):
        original = storage._try_write

        async def remove_first(sql, params):
            await storage.remove_entry(entry.id)
            return await original(sql, params)

        storage._try_write = remove_first
        assert await storage.get_entries("k") == []


@pytest.mark.anyio
async def test_failed_touch_still_serves_the_entry(caplog):
    storage = await new_storage()
    with at(0):
        await store(storage, body=b"data")
    with at(1000):
        conn = await storage._ensure_connection()
        original = storage._try_write

        async def failing(sql, params):
            return await original("UPDATE no_such_table SET x = 1", ())

        storage._try_write = failing
        with caplog.at_level(logging.CRITICAL):
            [entry] = await storage.get_entries("k")
        storage._try_write = original
        assert await read(entry) == b"data"
        assert conn is not None


@pytest.mark.anyio
async def test_try_write_reports_rows_changed_or_failure(caplog):
    storage = await new_storage()
    with at(0):
        await store(storage)
    assert await storage._try_write("UPDATE entries SET last_accessed_at = 1 WHERE cache_key = ?", (b"k",)) == 1
    assert await storage._try_write("UPDATE entries SET last_accessed_at = 1 WHERE cache_key = ?", (b"nope",)) == 0
    with caplog.at_level(logging.CRITICAL):
        assert await storage._try_write("UPDATE no_such_table SET x = 1", ()) is None


@pytest.mark.anyio
async def test_write_removed_just_before_completion_is_not_cached():
    storage = await new_storage()
    entry = await storage.create_entry(req(), Response(status_code=200, stream=make_async_iterator([b"a"])), "k")
    stream = entry.response.stream
    assert await stream.__anext__() == b"a"
    await storage.remove_entry(entry.id)
    with pytest.raises(StopAsyncIteration):
        await stream.__anext__()
    assert await storage.get_entries("k") == []
    assert await rows(storage) == 0
