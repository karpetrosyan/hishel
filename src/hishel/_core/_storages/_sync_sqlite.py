from __future__ import annotations

import logging
import random
import threading
import time
import uuid
import warnings
from collections.abc import Iterable, Iterator
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional, Union

from hishel._core._headers import Headers
from hishel._core._storages._packing import pack, unpack
from hishel._core._storages._sync_base import SyncBaseStorage
from hishel._core.models import Entry, Request, Response
from hishel._utils import ensure_cache_dict, make_sync_iterator

logger = logging.getLogger(__name__)

# The tables this storage uses. Tables with these names and other columns, such
# as a 1.x cache or the caller's own, are refused and never changed. So a new
# schema needs a new default database_path.
TABLE_COLUMNS = {
    "entries": {"id", "cache_key", "data", "expires_at", "last_accessed_at", "chunk_count", "ttl_deadline", "tti"},
    "streams": {"entry_id", "chunk_number", "chunk_data"},
}
# The `entries` columns of a Hishel 1.x cache, which gets an error of its own.
V1_ENTRIES_COLUMNS = {"id", "cache_key", "data", "created_at", "deleted_at"}
# How long to keep retrying the switch to WAL, which needs a lock that several
# processes opening a new file at once fight over. SQLite fails right away there
# instead of waiting for busy_timeout (seconds).
WAL_RETRY_SECONDS = 5
# Rows deleted per create_entry when removing expired entries.
CLEANUP_BATCH_SIZE = 200
# Eviction stops as soon as the database fits, so it deletes a few rows at a
# time: one extra entry must not cost 200 others.
EVICTION_BATCH_SIZE = 10
EVICTION_MAX_BATCHES = 20
# last_accessed_at is written at most this often per entry (seconds).
MAX_TOUCH_INTERVAL = 60
# Target size (bytes) of a stored stream chunk row. Incoming chunks are
# re-chunked to this size before being written.
STORAGE_CHUNK_SIZE = 131072
# The WAL file is truncated back to this size (bytes) after a checkpoint.
MAX_WAL_SIZE = 64 * 1024 * 1024
# expires_at of entries that lookups must not return: removed entries and
# entries still being written. Always in the past, whatever the clock says.
HIDDEN = 0.0


def _connection_is_cross_thread_safe(connection: "sqlite3.Connection") -> bool:
    """
    Probe a sqlite3.Connection to determine whether it was created with
    check_same_thread=False (and therefore can safely be shared across
    threads under our own application lock).

    sqlite3 doesn't expose check_same_thread as a public attribute, so we
    detect it by trying a trivial SELECT from a fresh thread and catching
    sqlite3.ProgrammingError. Costs ~1ms; only called once at storage
    construction when a user supplied their own connection.
    """
    result: list[bool] = [False]

    def probe() -> None:
        try:
            connection.execute("SELECT 1").fetchone()
            result[0] = True
        except sqlite3.ProgrammingError:
            result[0] = False

    t = threading.Thread(target=probe)
    t.start()
    t.join()
    return result[0]


if TYPE_CHECKING:
    import sqlite3
    from threading import RLock
else:
    try:
        import sqlite3
        from threading import RLock
    except ImportError:
        sqlite3 = None
        RLock = None


class SyncSqliteStorage(SyncBaseStorage):
    """
    An entry is removed in two steps. Lookups stop returning it as soon as
    expires_at passes, and its row is deleted once it has also gone unused for
    soft_delete_ttl seconds, so that readers already streaming it can finish.
    Active readers and writers keep that window open by updating last_accessed_at.

    The connection is shared between threads, so every use of it holds _lock.
    Unlike the async storage, this file is written by hand rather than generated,
    because anysqlite provides that serialisation for the async one.
    """

    def __init__(
        self,
        *,
        connection: Optional[sqlite3.Connection] = None,
        database_path: Union[str, Path] = "hishel_cache_v2.db",
        default_ttl: float | None = None,
        default_tti: float | None = None,
        max_stream_size: int | None = None,
        max_size: int | None = 1024**3,
        soft_delete_ttl: float = 180,
    ) -> None:
        if sqlite3 is None:
            raise ImportError(
                "The 'sqlite3' module is required to use the `SyncSqliteStorage` integration, "
                "but it is not available in this Python installation."
            )

        # If the user supplied their own connection, check up front
        # whether it can be used from threads other than the one that
        # created it. SyncSqliteStorage is meant to work from any
        # thread; a connection created with the default
        # check_same_thread=True will raise sqlite3.ProgrammingError
        # the moment a non-creator thread touches it, regardless of
        # any locking we do at the application level.
        #
        # We only warn rather than raise so single-threaded callers
        # who deliberately use the default still work fine. The user
        # is responsible for ensuring their code matches the
        # connection's threading mode.
        if connection is not None and not _connection_is_cross_thread_safe(connection):
            warnings.warn(
                "SyncSqliteStorage was given a sqlite3.Connection created with "
                "check_same_thread=True (the default). This storage will only "
                "work from the thread that created the connection; any call "
                "from another thread will raise sqlite3.ProgrammingError. If "
                "you intend to use the storage from multiple threads, re-create "
                "your connection with check_same_thread=False, or omit the "
                "`connection=` argument and let SyncSqliteStorage create one.",
                stacklevel=2,
            )

        super().__init__(default_ttl=default_ttl, default_tti=default_tti, max_stream_size=max_stream_size)
        self.connection = connection
        self.database_path: Path = database_path if isinstance(database_path, Path) else Path(database_path)
        self.max_size = max_size
        self.soft_delete_ttl = soft_delete_ttl
        # An entry's last_accessed_at can lag by this much, so it has to stay
        # well below soft_delete_ttl for the grace period to mean anything.
        self._touch_interval = min(MAX_TOUCH_INTERVAL, soft_delete_ttl / 2)
        self._initialized = False
        # Set by close() and never unset: prevents lingering stream generators
        # from silently reopening the connection.
        self._closed = False
        self._lock = RLock()

    def _ensure_connection(self) -> sqlite3.Connection:
        with self._lock:
            if self._closed:
                raise RuntimeError("SyncSqliteStorage is closed and can no longer be used.")
            if self.connection is None:
                parent = self.database_path.parent if self.database_path.parent != Path(".") else None
                full_path = ensure_cache_dict(parent) / self.database_path.name
                self.connection = sqlite3.connect(str(full_path), check_same_thread=False)
            if not self._initialized:
                self._initialize_database()
                self._initialized = True
            return self.connection

    def _initialize_database(self) -> None:
        assert self.connection is not None
        cursor = self.connection.cursor()

        for table, columns in TABLE_COLUMNS.items():
            cursor.execute(f"PRAGMA table_info({table})")
            found = {row[1] for row in cursor.fetchall()}
            if found and found != columns:
                if table == "entries" and found == V1_ENTRIES_COLUMNS:
                    raise RuntimeError(
                        "This database is a Hishel 1.x cache, which this version can't use. It was left as it is. "
                        "Delete it or use another `database_path`."
                    )
                raise RuntimeError(
                    f"The database already has a `{table}` table that Hishel can't use. It was left as it is. "
                    "Use another `database_path` or `connection`."
                )

        self._switch_to_wal(cursor)
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute(f"PRAGMA journal_size_limit={MAX_WAL_SIZE}")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS entries (
                id BLOB PRIMARY KEY,
                cache_key BLOB NOT NULL,
                data BLOB NOT NULL,
                expires_at REAL,
                last_accessed_at REAL NOT NULL,
                chunk_count INTEGER,
                ttl_deadline REAL,
                tti REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS streams (
                entry_id BLOB NOT NULL,
                chunk_number INTEGER NOT NULL,
                chunk_data BLOB NOT NULL,
                PRIMARY KEY (entry_id, chunk_number),
                FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_cache_key ON entries(cache_key)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_expires_at ON entries(expires_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_last_accessed_at ON entries(last_accessed_at)")
        self.connection.commit()

    def _switch_to_wal(self, cursor: sqlite3.Cursor) -> None:
        deadline = time.monotonic() + WAL_RETRY_SECONDS
        while True:
            try:
                cursor.execute("PRAGMA journal_mode=WAL")
                return
            except sqlite3.OperationalError as error:
                if "locked" not in str(error) or time.monotonic() > deadline:
                    raise
                time.sleep(random.uniform(0.01, 0.1))

    def create_entry(
        self,
        request: Request,
        response: Response,
        key: str,
        *,
        ttl: float | None = None,
        tti: float | None = None,
    ) -> Entry:
        body = response.stream if response.stream is not None else make_sync_iterator([])
        assert isinstance(body, (Iterator, Iterable))

        now = time.time()
        ttl_deadline, tti = self._limits(ttl, tti, now)
        entry = Entry(
            id=uuid.uuid4(),
            request=request,
            response=replace(response, stream=body),
        )

        with self._lock:
            try:
                connection = self._ensure_connection()
                if not self._reclaim_space(connection, now):
                    return entry
                cursor = connection.cursor()
                cursor.execute(
                    "INSERT INTO entries (id, cache_key, data, expires_at, last_accessed_at, ttl_deadline, tti)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (entry.id.bytes, key.encode("utf-8"), pack(request, response), HIDDEN, now, ttl_deadline, tti),
                )
                connection.commit()
            except RuntimeError:
                # Closed, or a database it can't use, which aren't failures of the cache.
                raise
            except Exception:
                logger.exception("hishel: could not store entry, serving the response uncached")
                return entry

        stream = self._save_stream(body, entry.id.bytes, ttl_deadline, tti, now)
        return replace(entry, response=replace(response, stream=stream))

    def get_entries(self, key: str) -> List[Entry]:
        now = time.time()
        with self._lock:
            try:
                cursor = self._ensure_connection().cursor()
                cursor.execute(
                    "SELECT id, data, chunk_count, expires_at, last_accessed_at, ttl_deadline, tti FROM entries"
                    " WHERE cache_key = ? AND (expires_at IS NULL OR expires_at > ?)",
                    (key.encode("utf-8"), now),
                )
                rows = cursor.fetchall()
            except (sqlite3.Error, OSError):
                logger.exception("hishel: could not read entries, treating this as a cache miss")
                return []

        entries: List[Entry] = []
        for id_, data, chunk_count, expires_at, last_accessed_at, ttl_deadline, tti in rows:
            try:
                request, response = unpack(bytes(data))
            except Exception:
                logger.exception("hishel: dropping an entry that could not be decoded")
                self._try_write("UPDATE entries SET expires_at = ? WHERE id = ?", (HIDDEN, id_))
                continue

            # Most hits write nothing. Otherwise every read would be a write.
            new_expires_at = self._expires_at(ttl_deadline, tti, now)
            tti_lags = (
                tti is not None
                and expires_at is not None
                and new_expires_at is not None
                and new_expires_at - expires_at >= tti / 2
            )
            if now - last_accessed_at >= self._touch_interval or tti_lags:
                # The expiry check stops this from bringing back an entry that
                # remove_entry hid after the SELECT above.
                touched = self._try_write(
                    "UPDATE entries SET last_accessed_at = ?, expires_at = ?"
                    " WHERE id = ? AND (expires_at IS NULL OR expires_at > ?)",
                    (now, new_expires_at, id_, now),
                )
                # No row matched, so it was evicted or removed after the SELECT.
                if touched == 0:
                    continue
                if touched is not None:
                    last_accessed_at = now

            entries.append(
                Entry(
                    id=uuid.UUID(bytes=id_),
                    request=request,
                    response=replace(
                        response,
                        stream=self._stream_from_cache(id_, chunk_count, last_accessed_at),
                    ),
                )
            )

        return entries

    def update_headers(self, id: uuid.UUID, headers: Headers) -> None:
        # The blob is only ever rewritten here, so the last writer winning is
        # the correct result if two revalidations race.
        with self._lock:
            try:
                connection = self._ensure_connection()
                cursor = connection.cursor()
                cursor.execute("SELECT data FROM entries WHERE id = ?", (id.bytes,))
                row = cursor.fetchone()
                if row is None:
                    return

                request, response = unpack(bytes(row[0]))
                updated = pack(request, replace(response, headers=headers))
                cursor.execute("UPDATE entries SET data = ? WHERE id = ?", (updated, id.bytes))
                connection.commit()
            except (sqlite3.Error, OSError):
                logger.exception("hishel: could not update entry")

    def remove_entry(self, id: uuid.UUID) -> None:
        with self._lock:
            try:
                connection = self._ensure_connection()
                cursor = connection.cursor()
                # An entry still being written has no readers to protect, and hiding it
                # would not last: completing the stream sets expires_at.
                cursor.execute("DELETE FROM entries WHERE id = ? AND chunk_count IS NULL", (id.bytes,))
                cursor.execute("UPDATE entries SET expires_at = ? WHERE id = ?", (HIDDEN, id.bytes))
                connection.commit()
            except (sqlite3.Error, OSError):
                logger.exception("hishel: could not remove entry, so it can still be served")

    def close(self) -> None:
        with self._lock:
            self._closed = True
            if self.connection is not None:
                self.connection.close()
                self.connection = None
            self._initialized = False

    def _try_write(self, sql: str, parameters: tuple[Any, ...]) -> int | None:
        """
        Run a write that must not fail the request being served.

        Returns how many rows it changed, or None if it failed.
        """
        try:
            with self._lock:
                connection = self._ensure_connection()
                cursor = connection.cursor()
                cursor.execute(sql, parameters)
                changed = cursor.rowcount
                connection.commit()
            return changed
        except Exception:
            logger.exception("hishel: cache write failed")
            return None

    def _reclaim_space(self, connection: sqlite3.Connection, now: float) -> bool:
        """
        Delete a bounded number of rows and return whether there is room for a new entry.

        Abandoned writes are covered too: they stay HIDDEN and stop updating
        last_accessed_at once their writer is gone.
        """
        cursor = connection.cursor()
        unused_since = now - self.soft_delete_ttl

        cursor.execute(
            "DELETE FROM entries WHERE id IN ("
            " SELECT id FROM entries WHERE expires_at < ? AND last_accessed_at < ? LIMIT ?)",
            (now, unused_since, CLEANUP_BATCH_SIZE),
        )
        connection.commit()

        if self.max_size is None:
            return True

        for _ in range(EVICTION_MAX_BATCHES):
            if self._database_size(cursor) <= self.max_size:
                return True
            cursor.execute(
                "DELETE FROM entries WHERE id IN ("
                " SELECT id FROM entries WHERE last_accessed_at < ? ORDER BY last_accessed_at LIMIT ?)",
                (unused_since, EVICTION_BATCH_SIZE),
            )
            deleted = cursor.rowcount
            connection.commit()
            if deleted == 0:
                break

        return self._database_size(cursor) <= self.max_size

    def _database_size(self, cursor: sqlite3.Cursor) -> int:
        cursor.execute(
            "SELECT (page_count - freelist_count) * page_size"
            " FROM pragma_page_count(), pragma_freelist_count(), pragma_page_size()"
        )
        row = cursor.fetchone()
        return int(row[0])

    def _save_stream(
        self,
        stream: Iterator[bytes],
        id_: bytes,
        ttl_deadline: float | None,
        tti: float | None,
        last_touch: float,
    ) -> Iterator[bytes]:
        """
        Yield the stream unchanged while saving it, re-chunked to STORAGE_CHUNK_SIZE.

        Saving stops on the first failure, or when the response gets too big to
        cache, but the consumer keeps receiving the stream either way.
        """
        limits = [limit for limit in (self.max_stream_size, self.max_size) if limit is not None]
        limit = min(limits, default=None)
        chunk_number = 0
        total_size = 0
        buffer = bytearray()
        saving = True
        completed = False

        def write_chunk(data: bytes) -> bool:
            nonlocal chunk_number, last_touch
            inserted = self._try_write(
                "INSERT INTO streams (entry_id, chunk_number, chunk_data) VALUES (?, ?, ?)",
                (id_, chunk_number, data),
            )
            if inserted is None:
                return False
            chunk_number += 1
            now = time.time()
            if now - last_touch >= self._touch_interval:
                last_touch = now
                self._try_write("UPDATE entries SET last_accessed_at = ? WHERE id = ?", (now, id_))
            return True

        try:
            for chunk in stream:
                if saving:
                    total_size += len(chunk)
                    if limit is not None and total_size > limit:
                        saving = False
                    else:
                        buffer += chunk
                        while saving and len(buffer) >= STORAGE_CHUNK_SIZE:
                            saving = write_chunk(bytes(buffer[:STORAGE_CHUNK_SIZE]))
                            del buffer[:STORAGE_CHUNK_SIZE]
                    if not saving:
                        buffer.clear()
                        self._try_write("DELETE FROM entries WHERE id = ?", (id_,))
                yield chunk

            if saving and buffer:
                saving = write_chunk(bytes(buffer))
            if saving:
                now = time.time()
                updated = self._try_write(
                    "UPDATE entries SET chunk_count = ?, expires_at = ?, last_accessed_at = ? WHERE id = ?",
                    (chunk_number, self._expires_at(ttl_deadline, tti, now), now, id_),
                )
                completed = bool(updated)
        finally:
            # Upstream failed or the consumer stopped reading. If this gets
            # cancelled too, _reclaim_space removes the row later.
            if not completed:
                self._try_write("DELETE FROM entries WHERE id = ?", (id_,))

    def _stream_from_cache(
        self,
        id_: bytes,
        chunk_count: int,
        last_touch: float,
    ) -> Iterator[bytes]:
        for chunk_number in range(chunk_count):
            with self._lock:
                cursor = self._ensure_connection().cursor()
                cursor.execute(
                    "SELECT chunk_data FROM streams WHERE entry_id = ? AND chunk_number = ?",
                    (id_, chunk_number),
                )
                row = cursor.fetchone()
            if row is None:
                raise RuntimeError(
                    "Cached response was deleted while it was being read. "
                    "Increase soft_delete_ttl if consumers stall for longer than that."
                )

            now = time.time()
            if now - last_touch >= self._touch_interval:
                last_touch = now
                self._try_write("UPDATE entries SET last_accessed_at = ? WHERE id = ?", (now, id_))

            yield row[0]
