import logging
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone

import sqlite3
import pytest
from time_machine import travel

from hishel import Headers
from hishel._core._storages._sync_sqlite import STORAGE_CHUNK_SIZE, SyncSqliteStorage
from hishel._core.models import Request, Response
from hishel._utils import make_sync_iterator

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


@pytest.fixture
def anyio_backend():
    return "asyncio"


def at(seconds):
    return travel(START + timedelta(seconds=seconds), tick=False)


def new_storage(**kwargs):
    return SyncSqliteStorage(connection=sqlite3.connect(":memory:", check_same_thread=False), **kwargs)


def req():
    return Request(method="GET", url="https://example.com")


def store(storage, key="k", body=b"data", request=None, **limits):
    entry = storage.create_entry(
        request or req(), Response(status_code=200, stream=make_sync_iterator([body])), key, **limits
    )
    read(entry)
    return entry


def read(entry):
    return b"".join([chunk for chunk in entry.response.stream])


def rows(storage):
    conn = storage._ensure_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM entries")
    return (cur.fetchone())[0]


def chunk_rows(storage):
    conn = storage._ensure_connection()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM streams")
    return (cur.fetchone())[0]



def test_round_trip_rechunks_and_returns_exact_body():
    storage = new_storage()
    body = b"x" * (STORAGE_CHUNK_SIZE * 2 + 5)
    store(storage, body=body)
    [entry] = storage.get_entries("k")
    assert read(entry) == body
    assert chunk_rows(storage) == 3



def test_empty_body():
    storage = new_storage()
    store(storage, body=b"")
    [entry] = storage.get_entries("k")
    assert read(entry) == b""



def test_incomplete_entry_is_invisible_until_stream_finishes():
    storage = new_storage()
    entry = storage.create_entry(req(), Response(status_code=200, stream=make_sync_iterator([b"a", b"b"])), "k")
    assert storage.get_entries("k") == []
    read(entry)
    assert len(storage.get_entries("k")) == 1



def test_ttl_hides_then_next_write_deletes():
    storage = new_storage(default_ttl=100)
    with at(0):
        store(storage)
    with at(99):
        assert len(storage.get_entries("k")) == 1
    with at(101):
        assert storage.get_entries("k") == []
        store(storage, key="other")
        assert rows(storage) == 2  # expired, but returned at 99 so still within grace
    with at(400):
        store(storage, key="other2")
        assert storage.get_entries("k") == []
        conn = storage._ensure_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM entries WHERE cache_key = ?", (b"k",))
        assert (cur.fetchone())[0] == 0
    assert chunk_rows(storage) == 1  # "other" expired and went cold too; only other2 is left



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
        [entry] = storage.get_entries("k")
        assert len(storage.get_entries("k")) == 1
    with at(250):
        assert storage.get_entries("k") == []



def test_defaults_apply_only_to_entries_created_under_them(tmp_path):
    path = tmp_path / "cache.db"
    first = SyncSqliteStorage(database_path=path, default_tti=100)
    with at(0):
        store(first)
    first.close()

    second = SyncSqliteStorage(database_path=path, default_tti=1000)
    with at(90):
        assert len(second.get_entries("k")) == 1
    with at(250):
        assert second.get_entries("k") == []
    second.close()



def test_update_headers_keeps_limits():
    storage = new_storage()
    with at(0):
        entry = store(storage, ttl=100, tti=50)
        storage.update_headers(entry.id, Headers({"etag": "new"}))
    with at(40):
        assert len(storage.get_entries("k")) == 1
    with at(80):
        assert len(storage.get_entries("k")) == 1
    with at(101):
        assert storage.get_entries("k") == []



def test_frequent_reads_do_not_write():
    storage = new_storage()
    with at(0):
        store(storage)
    with at(10):
        calls = []
        original = storage._try_write

        def spy(sql, params):
            calls.append(sql)
            return original(sql, params)

        storage._try_write = spy
        storage.get_entries("k")
        assert calls == []
    with at(61):
        storage.get_entries("k")
        assert len(calls) == 1



def test_remove_hides_immediately_and_is_deleted_after_grace():
    storage = new_storage()
    with at(0):
        entry = store(storage)
        storage.remove_entry(entry.id)
        assert storage.get_entries("k") == []
    with at(100):
        store(storage, key="x")
        assert rows(storage) == 2
    with at(181):
        store(storage, key="y")
        assert rows(storage) == 2  # removed row gone, x and y left



def test_remove_racing_with_lookup_touch_stays_removed():
    storage = new_storage(default_tti=100)
    with at(0):
        entry = store(storage)
    with at(90):
        original = storage._try_write

        def remove_first(sql, params):
            storage.remove_entry(entry.id)
            return original(sql, params)

        storage._try_write = remove_first
        storage.get_entries("k")
        storage._try_write = original
        assert storage.get_entries("k") == []



def test_remove_during_write_stays_removed_and_consumer_is_served(caplog):
    storage = new_storage()
    chunks = [b"x" * STORAGE_CHUNK_SIZE] * 3
    entry = storage.create_entry(req(), Response(status_code=200, stream=make_sync_iterator(chunks)), "k")
    stream = entry.response.stream
    received = [stream.__next__()]
    storage.remove_entry(entry.id)
    with caplog.at_level(logging.CRITICAL):
        for chunk in stream:
            received.append(chunk)
    assert b"".join(received) == b"".join(chunks)
    assert storage.get_entries("k") == []
    assert rows(storage) == 0



def test_reader_heartbeat_does_not_stop_tti_extension():
    storage = new_storage(default_tti=100)
    with at(0):
        store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 2))
        [entry] = storage.get_entries("k")
    stream = entry.response.stream
    with at(70):
        stream.__next__()  # updates last_accessed_at only
    with at(80):
        assert len(storage.get_entries("k")) == 1  # must still extend to 180
    with at(150):
        assert len(storage.get_entries("k")) == 1



def test_remove_and_update_missing_entry_are_noops():
    storage = new_storage()
    storage.remove_entry(uuid.uuid4())
    storage.update_headers(uuid.uuid4(), Headers({"a": "b"}))



def test_update_headers():
    storage = new_storage()
    entry = store(storage)
    storage.update_headers(entry.id, Headers({"etag": "new"}))
    [got] = storage.get_entries("k")
    assert got.response.headers["etag"] == "new"
    assert read(got) == b"data"



def test_lookup_of_read_entry_protects_from_cleanup_for_grace():
    storage = new_storage(default_ttl=300)
    with at(0):
        store(storage)
    with at(299):
        [entry] = storage.get_entries("k")
    with at(320):  # expired, but read 21s ago
        store(storage, key="x")
        assert read(entry) == b"data"



def test_lru_evicts_least_recently_used_and_stops_when_it_fits():
    body = b"x" * STORAGE_CHUNK_SIZE
    storage = new_storage(max_size=2_000_000)
    for i in range(10):
        with at(i * 1000):
            store(storage, key=f"k{i}", body=body)
    size = storage._database_size((storage._ensure_connection()).cursor())
    count = rows(storage)
    assert size <= 2_000_000 + 2 * STORAGE_CHUNK_SIZE
    assert count >= 5, f"over-evicted: {count}"

    # Protect k9-ish: read the oldest survivor, then force evictions
    with at(100_000):
        survivors = []
        for i in range(10):
            if storage.get_entries(f"k{i}"):
                survivors.append(i)
        oldest = survivors[0]
    with at(100_500):
        storage.get_entries(f"k{oldest}")
    with at(100_700):
        for i in range(10, 13):
            store(storage, key=f"k{i}", body=body)
        assert storage.get_entries(f"k{oldest}") != []



def test_database_stays_near_limit_over_many_writes():
    body = b"x" * 50_000
    storage = new_storage(max_size=1_000_000)
    for i in range(300):
        with at(i * 500):
            store(storage, key=f"k{i}", body=body)
        size = storage._database_size((storage._ensure_connection()).cursor())
        assert size <= 1_000_000 + 200_000, f"at write {i}: {size}"



def test_cache_full_of_recently_used_entries_stops_storing_but_serves():
    body = b"x" * 400_000
    storage = new_storage(max_size=1_000_000)
    with at(0):
        store(storage, key="a", body=body)
        store(storage, key="b", body=body)
        store(storage, key="c", body=body)
    with at(1):
        before = rows(storage)
        entry = storage.create_entry(req(), Response(status_code=200, stream=make_sync_iterator([body])), "d")
        assert read(entry) == body
        assert rows(storage) == before
        assert storage.get_entries("d") == []
    # Becomes evictable once the grace period passes
    with at(500):
        store(storage, key="d", body=body)
        assert len(storage.get_entries("d")) == 1



def test_reader_raises_when_entry_deleted_mid_read():
    storage = new_storage()
    store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 3))
    [entry] = storage.get_entries("k")
    stream = entry.response.stream
    stream.__next__()
    conn = storage._ensure_connection()
    conn.execute("DELETE FROM entries")
    conn.commit()
    with pytest.raises(RuntimeError, match="deleted while"):
        for _ in stream:
            pass



def test_active_slow_reader_survives_cleanup_and_eviction():
    storage = new_storage(default_ttl=100)
    with at(0):
        store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 8))
        [entry] = storage.get_entries("k")
    stream = entry.response.stream
    total = 0
    for i in range(8):
        with at(i * 100):  # spans 700s, well past TTL and grace
            total += len(stream.__next__())
            store(storage, key=f"other{i}")
    assert total == STORAGE_CHUNK_SIZE * 8



def test_reader_starting_late_within_grace_refreshes_protection():
    storage = new_storage(default_ttl=100)
    with at(0):
        store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 2))
        [entry] = storage.get_entries("k")
    stream = entry.response.stream
    with at(170):
        stream.__next__()
    with at(300):  # expired and 300s after lookup, but only 130s after reading
        store(storage, key="o")
        stream.__next__()



def test_stalled_reader_past_grace_raises_instead_of_truncating():
    storage = new_storage(default_ttl=100)
    with at(0):
        store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 2))
        [entry] = storage.get_entries("k")
    stream = entry.response.stream
    with at(1):
        stream.__next__()
    with at(1000):
        store(storage, key="o")
        with pytest.raises(RuntimeError, match="deleted while"):
            stream.__next__()



def test_slow_writer_is_not_treated_as_abandoned():
    storage = new_storage()
    with at(0):
        entry = storage.create_entry(
            req(),
            Response(status_code=200, stream=make_sync_iterator([b"x" * STORAGE_CHUNK_SIZE] * 6)),
            "k",
        )
    stream = entry.response.stream
    for i in range(6):
        with at(i * 150):
            stream.__next__()
            store(storage, key=f"o{i}")
    with at(900), pytest.raises(StopIteration):
        stream.__next__()
    with at(900):
        [got] = storage.get_entries("k")
        assert len(read(got)) == STORAGE_CHUNK_SIZE * 6



def test_abandoned_stream_discards_partial_data_immediately():
    storage = new_storage()
    entry = storage.create_entry(
        req(),
        Response(status_code=200, stream=make_sync_iterator([b"x" * STORAGE_CHUNK_SIZE] * 3)),
        "k",
    )
    stream = entry.response.stream
    stream.__next__()
    stream.__next__()
    assert rows(storage) == 1
    stream.close()
    assert rows(storage) == 0
    assert chunk_rows(storage) == 0



def test_crashed_writer_is_removed_after_grace():
    storage = new_storage()
    with at(0):
        entry = storage.create_entry(
            req(),
            Response(status_code=200, stream=make_sync_iterator([b"x" * STORAGE_CHUNK_SIZE] * 2)),
            "k",
        )
        entry.response.stream.__next__()
    with at(100):
        store(storage, key="o")
        assert rows(storage) == 2
    with at(181):
        store(storage, key="p")
        assert rows(storage) == 2  # crashed row gone, o and p left
        assert chunk_rows(storage) == 2



def test_upstream_failure_discards_and_propagates():
    def boom():
        yield b"x" * STORAGE_CHUNK_SIZE
        raise ValueError("upstream")

    storage = new_storage()
    entry = storage.create_entry(req(), Response(status_code=200, stream=boom()), "k")
    with pytest.raises(ValueError):
        read(entry)
    assert rows(storage) == 0



@pytest.mark.parametrize("kwargs", [{"max_stream_size": 1000}, {"max_size": 1000}])
def test_too_big_response_is_not_cached_but_fully_delivered(kwargs):
    storage = new_storage(**kwargs)
    chunks = [b"x" * 700] * 5
    entry = storage.create_entry(req(), Response(status_code=200, stream=make_sync_iterator(chunks)), "k")
    assert read(entry) == b"".join(chunks)
    assert storage.get_entries("k") == []
    assert rows(storage) == 0



def test_storage_failure_mid_stream_does_not_fail_consumer(caplog):
    storage = new_storage()
    chunks = [b"x" * STORAGE_CHUNK_SIZE] * 4
    entry = storage.create_entry(req(), Response(status_code=200, stream=make_sync_iterator(chunks)), "k")
    stream = entry.response.stream
    received = [stream.__next__()]
    # Row vanishes under the writer: the next insert violates the foreign key
    conn = storage._ensure_connection()
    conn.execute("DELETE FROM entries")
    conn.commit()
    with caplog.at_level(logging.CRITICAL):
        for chunk in stream:
            received.append(chunk)
    assert b"".join(received) == b"".join(chunks)
    assert storage.get_entries("k") == []



def test_create_entry_failure_serves_uncached():
    storage = new_storage()
    storage._ensure_connection()

    def broken(*args):
        raise sqlite3.OperationalError("disk full")

    storage._reclaim_space = broken
    entry = storage.create_entry(req(), Response(status_code=200, stream=make_sync_iterator([b"data"])), "k")
    assert read(entry) == b"data"
    assert rows(storage) == 0



def test_corrupt_row_does_not_break_lookup_or_cleanup():
    storage = new_storage()
    with at(0):
        store(storage)
        store(storage)
        conn = storage._ensure_connection()
        cur = conn.cursor()
        cur.execute("SELECT id FROM entries LIMIT 1")
        bad = (cur.fetchone())[0]
        cur.execute("UPDATE entries SET data = ? WHERE id = ?", (b"\xc1garbage", bad))
        conn.commit()
        assert len(storage.get_entries("k")) == 1
    with at(200):
        store(storage, key="o")
        assert rows(storage) == 2
        assert len(storage.get_entries("k")) == 1



def test_closed_storage_raises_and_does_not_reopen():
    storage = new_storage()
    store(storage)
    storage.close()
    with pytest.raises(RuntimeError, match="closed"):
        storage.get_entries("k")
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



def test_old_database_is_reset_and_file_shrinks(tmp_path):
    path = tmp_path / "cache.db"
    create_v1_database(path)
    old_size = path.stat().st_size
    assert old_size > 9_000_000

    new = SyncSqliteStorage(database_path=path)
    assert new.get_entries("k0") == []
    store(new)
    assert len(new.get_entries("k")) == 1
    conn = new._ensure_connection()
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    new.close()
    assert path.stat().st_size < 200_000

    # Reopening a current database keeps its data
    again = SyncSqliteStorage(database_path=path)
    assert len(again.get_entries("k")) == 1
    again.close()



def test_queries_use_indexes():
    storage = new_storage()
    conn = storage._ensure_connection()
    cur = conn.cursor()

    def plan(sql, params):
        cur.execute("EXPLAIN QUERY PLAN " + sql, params)
        return " | ".join(r[3] for r in cur.fetchall())

    cleanup = plan("SELECT id FROM entries WHERE expires_at < ? AND last_accessed_at < ? LIMIT ?", (1.0, 1.0, 1))
    assert "USING INDEX idx_entries_expires_at" in cleanup or "USING INDEX idx_entries_last_accessed_at" in cleanup
    print("cleanup:", cleanup)
    evict = plan("SELECT id FROM entries WHERE last_accessed_at < ? ORDER BY last_accessed_at LIMIT ?", (1.0, 1))
    assert "idx_entries_last_accessed_at" in evict and "TEMP B-TREE" not in evict
    print("evict:", evict)
    lookup = plan(
        "SELECT id, data, chunk_count, last_accessed_at FROM entries"
        " WHERE cache_key = ? AND (expires_at IS NULL OR expires_at > ?)",
        (b"k", 1.0),
    )
    assert "idx_entries_cache_key" in lookup
    print("lookup:", lookup)
    conn.execute("SELECT 1")



def test_cost_with_100k_entries(tmp_path, capsys):
    from hishel._core._storages._packing import pack
    from hishel._core.models import Entry

    storage = SyncSqliteStorage(database_path=tmp_path / "bench.db", max_size=None)
    conn = storage._ensure_connection()
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
    conn.executemany("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?)", entries)
    conn.executemany("INSERT INTO streams VALUES (?,?,?)", streams)
    conn.commit()

    t = time.perf_counter()
    for _ in range(200):
        storage._reclaim_space(conn, now)
    no_work = (time.perf_counter() - t) / 200 * 1000

    storage.max_size = 2 * 1024**3
    t = time.perf_counter()
    for _ in range(200):
        storage._reclaim_space(conn, now)
    with_size_check = (time.perf_counter() - t) / 200 * 1000

    t = time.perf_counter()
    for i in range(200):
        store(storage, key=f"new-{i}", body=b"x" * 10_000)
    create = (time.perf_counter() - t) / 200 * 1000
    assert len(storage.get_entries("new-0")) == 1

    t = time.perf_counter()
    for i in range(1000):
        storage.get_entries(f"key-{i}")
    lookup = (time.perf_counter() - t) / 1000 * 1000

    # Everything expires and goes cold at once: one batch's cost.
    conn.execute("UPDATE entries SET expires_at = 1, last_accessed_at = 1")
    conn.commit()
    t = time.perf_counter()
    storage._reclaim_space(conn, now)
    batch = (time.perf_counter() - t) * 1000
    with capsys.disabled():
        print(
            f"\n100k entries: cleanup no-op {no_work:.3f} ms, +size check {with_size_check:.3f} ms, "
            f"create+store {create:.3f} ms, get_entries {lookup:.3f} ms, delete batch of 200 {batch:.1f} ms"
        )
    storage.close()



def test_ttl_counts_from_when_entry_was_stored_not_when_body_finished():
    storage = new_storage()
    with at(0):
        entry = storage.create_entry(
            req(), Response(status_code=200, stream=make_sync_iterator([b"a"])), "k", ttl=100
        )
    with at(60):
        read(entry)
    with at(99):
        assert len(storage.get_entries("k")) == 1
    with at(101):
        assert storage.get_entries("k") == []



def test_entries_get_their_id_and_key_from_the_row_not_the_blob():
    from hishel._core._storages._packing import unpack

    storage = new_storage()
    entry = store(storage, key="some-key")
    [got] = storage.get_entries("some-key")
    assert got.id == entry.id
    conn = storage._ensure_connection()
    cur = conn.cursor()
    cur.execute("SELECT data FROM entries")
    blob = (cur.fetchone())[0]
    assert entry.id.bytes not in blob and b"some-key" not in blob
    assert unpack(bytes(blob))[1].status_code == 200



def test_response_without_a_stream_is_stored_with_an_empty_body():
    storage = new_storage()
    entry = storage.create_entry(req(), Response(status_code=204), "k")
    assert read(entry) == b""
    [got] = storage.get_entries("k")
    assert got.response.status_code == 204
    assert read(got) == b""



def test_eviction_between_select_and_touch_is_a_miss_not_an_error():
    storage = new_storage()
    with at(0):
        store(storage, body=b"x" * (STORAGE_CHUNK_SIZE * 2))
    with at(1000):
        original = storage._try_write

        def evict_first(sql, params):
            conn = storage._ensure_connection()
            conn.execute("DELETE FROM entries")
            conn.commit()
            return original(sql, params)

        storage._try_write = evict_first
        assert storage.get_entries("k") == []



def test_only_the_evicted_entry_is_skipped():
    storage = new_storage()
    with at(0):
        evicted = store(storage, body=b"gone")
        store(storage, body=b"kept")
    with at(1000):
        original = storage._try_write
        calls: list[str] = []

        def evict_on_first_touch(sql, params):
            if not calls:
                calls.append(sql)
                conn = storage._ensure_connection()
                conn.execute("DELETE FROM entries WHERE id = ?", (params[2],))
                conn.commit()
            return original(sql, params)

        storage._try_write = evict_on_first_touch
        entries = storage.get_entries("k")
    storage._try_write = original
    assert len(entries) == 1
    assert evicted.id.bytes != b""
    assert read(entries[0]) in (b"gone", b"kept")



def test_removal_between_select_and_touch_is_a_miss():
    storage = new_storage(default_tti=100)
    with at(0):
        entry = store(storage)
    with at(90):
        original = storage._try_write

        def remove_first(sql, params):
            storage.remove_entry(entry.id)
            return original(sql, params)

        storage._try_write = remove_first
        assert storage.get_entries("k") == []



def test_failed_touch_still_serves_the_entry(caplog):
    storage = new_storage()
    with at(0):
        store(storage, body=b"data")
    with at(1000):
        conn = storage._ensure_connection()
        original = storage._try_write

        def failing(sql, params):
            return original("UPDATE no_such_table SET x = 1", ())

        storage._try_write = failing
        with caplog.at_level(logging.CRITICAL):
            [entry] = storage.get_entries("k")
        storage._try_write = original
        assert read(entry) == b"data"
        assert conn is not None



def test_try_write_reports_rows_changed_or_failure(caplog):
    storage = new_storage()
    with at(0):
        store(storage)
    assert storage._try_write("UPDATE entries SET last_accessed_at = 1 WHERE cache_key = ?", (b"k",)) == 1
    assert storage._try_write("UPDATE entries SET last_accessed_at = 1 WHERE cache_key = ?", (b"nope",)) == 0
    with caplog.at_level(logging.CRITICAL):
        assert storage._try_write("UPDATE no_such_table SET x = 1", ()) is None



def test_write_removed_just_before_completion_is_not_cached():
    storage = new_storage()
    entry = storage.create_entry(req(), Response(status_code=200, stream=make_sync_iterator([b"a"])), "k")
    stream = entry.response.stream
    assert stream.__next__() == b"a"
    storage.remove_entry(entry.id)
    with pytest.raises(StopIteration):
        stream.__next__()
    assert storage.get_entries("k") == []
    assert rows(storage) == 0
