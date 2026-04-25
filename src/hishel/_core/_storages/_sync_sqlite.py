from __future__ import annotations

import logging
import threading
import time
import uuid
import warnings
from dataclasses import replace
from pathlib import Path
from typing import (
    Any,
    Iterable,
    Iterator,
    Callable,
    List,
    Optional,
    Union,
)

from hishel._core._storages._sync_base import SyncBaseStorage
from hishel._core._storages._packing import pack, unpack
from hishel._core.models import (
    Entry,
    EntryMeta,
    Request,
    Response,
)
from hishel._utils import ensure_cache_dict

logger = logging.getLogger(__name__)

# Batch cleanup configuration
# How often to run cleanup (seconds). Default: 1 hour.
BATCH_CLEANUP_INTERVAL = 3600
# How long to wait after storage creation before allowing the first cleanup (seconds)
BATCH_CLEANUP_START_DELAY = 5 * 60
# Number of rows to process per chunk when cleaning
BATCH_CLEANUP_CHUNK_SIZE = 200


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
    import sqlite3 as _sqlite3
    result: list[bool] = [False]

    def probe() -> None:
        try:
            connection.execute("SELECT 1").fetchone()
            result[0] = True
        except _sqlite3.ProgrammingError:
            result[0] = False

    t = threading.Thread(target=probe)
    t.start()
    t.join()
    return result[0]


try:
    import sqlite3
    from threading import RLock

    class SyncSqliteStorage(SyncBaseStorage):
        _COMPLETE_CHUNK_NUMBER = -1

        def __init__(
            self,
            *,
            connection: Optional[sqlite3.Connection] = None,
            database_path: Union[str, Path] = "hishel_cache.db",
            default_ttl: Optional[float] = None,
            refresh_ttl_on_access: bool | None = None,
        ) -> None:
            if isinstance(refresh_ttl_on_access, bool):
                warnings.warn(
                    "The 'refresh_ttl_on_access' parameter is deprecated and has no effect. "
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

            self.connection = connection
            self.database_path: Path = (
                database_path if isinstance(database_path, Path) else Path(database_path)
            )
            self.default_ttl = default_ttl
            self.last_cleanup = (
                time.time() - BATCH_CLEANUP_INTERVAL + BATCH_CLEANUP_START_DELAY
            )
            self._start_time = time.time()
            self._initialized = False
            # A single RLock guards all access to the shared sqlite3
            # connection. Why a single lock and not the two-lock split used
            # in the async version:
            #
            # The async (anysqlite) storage can let pure reads and
            # single-statement writes run lock-free because anysqlite
            # enforces per-Connection serialisation via a CapacityLimiter(1)
            # at the Python level. Python's standard sqlite3 module does
            # NOT do that. The docs say "write operations may need to be
            # serialized by the user to avoid data corruption", and in
            # practice even concurrent reads on the same connection from
            # different threads can raise sqlite3.InterfaceError under
            # load. So every DB operation goes through this lock.
            #
            # RLock so accidental re-entry on the same thread doesn't
            # deadlock; the common single-thread case costs the same as a
            # plain Lock.
            self._lock = RLock()

        def _ensure_connection(self) -> sqlite3.Connection:
            """
            Ensure connection is established and database is initialized.

            Caller must hold self._lock.
            """
            if self.connection is None:
                # Create cache directory and resolve full path on first connection.
                parent = (
                    self.database_path.parent
                    if self.database_path.parent != Path(".")
                    else None
                )
                full_path = ensure_cache_dict(parent) / self.database_path.name
                # check_same_thread=False is required because the cache is
                # used from any thread; our self._lock serialises access so
                # the no-thread-check mode is safe.
                self.connection = sqlite3.connect(
                    str(full_path), check_same_thread=False
                )
            if not self._initialized:
                self._initialize_database()
                self._initialized = True
            return self.connection

        def _initialize_database(self) -> None:
            """
            Initialize the database schema and configure the connection.

            Caller must hold self._lock.
            """
            assert self.connection is not None
            cursor = self.connection.cursor()

            # Configure connection for cache workload:
            # - WAL allows concurrent readers during writes (between processes)
            # - busy_timeout avoids SQLITE_BUSY errors under file-level contention
            # - synchronous=NORMAL is the right durability/perf tradeoff for a cache
            # - foreign_keys enables ON DELETE CASCADE enforcement
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")

            # Table for storing request/response pairs
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id BLOB PRIMARY KEY,
                    cache_key BLOB,
                    data BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    deleted_at REAL
                )
                """
            )

            # Table for storing response stream chunks only
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS streams (
                    entry_id BLOB NOT NULL,
                    chunk_number INTEGER NOT NULL,
                    chunk_data BLOB NOT NULL,
                    PRIMARY KEY (entry_id, chunk_number),
                    FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
                )
                """
            )

            # Indexes for performance
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_entries_deleted_at ON entries(deleted_at)"
            )
            cursor.execute(
                "CREATE INDEX IF NOT EXISTS idx_entries_cache_key ON entries(cache_key)"
            )

            self.connection.commit()

        def create_entry(
            self,
            request: Request,
            response: Response,
            key: str,
            id_: uuid.UUID | None = None,
        ) -> Entry:
            key_bytes = key.encode("utf-8")

            # Build the entry outside the lock; only the actual DB write
            # needs to be serialised against other DB users.
            pair_id = id_ if id_ is not None else uuid.uuid4()
            pair_meta = EntryMeta(created_at=time.time())

            assert isinstance(response.stream, (Iterator, Iterable))
            response_with_stream = replace(
                response,
                stream=self._save_stream(response.stream, pair_id.bytes),
            )

            complete_entry = Entry(
                id=pair_id,
                request=request,
                response=response_with_stream,
                meta=pair_meta,
                cache_key=key_bytes,
            )

            with self._lock:
                connection = self._ensure_connection()
                cursor = connection.cursor()
                cursor.execute(
                    "INSERT INTO entries (id, cache_key, data, created_at, deleted_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (
                        pair_id.bytes,
                        key_bytes,
                        pack(complete_entry, kind="pair"),
                        pair_meta.created_at,
                        None,
                    ),
                )
                connection.commit()

            return complete_entry

        def get_entries(self, key: str) -> List[Entry]:
            final_pairs: List[Entry] = []

            with self._lock:
                if time.time() - self.last_cleanup >= BATCH_CLEANUP_INTERVAL:
                    try:
                        self._batch_cleanup()
                    except Exception:
                        # Don't let cleanup prevent reads; failures are non-fatal
                        # but we log so problems are visible instead of silent.
                        logger.exception("hishel: batch cleanup failed")

                connection = self._ensure_connection()
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT id, data FROM entries WHERE cache_key = ?",
                    (key.encode("utf-8"),),
                )

                for row in cursor.fetchall():
                    pair_data = unpack(row[1], kind="pair")

                    if pair_data is None:
                        continue

                    # Skip entries without a complete response stream
                    if not self._is_stream_complete(pair_data.id, cursor=cursor):
                        continue

                    # Skip expired entries
                    if self._is_pair_expired(pair_data, cursor=cursor):
                        continue

                    # Skip soft-deleted entries
                    if self.is_soft_deleted(pair_data):
                        continue

                    final_pairs.append(pair_data)

            pairs_with_streams: List[Entry] = []

            # Wrap response streams as lazy generators that take the lock
            # per chunk inside _stream_data_from_cache. We deliberately do
            # NOT hold the lock across user iteration of the stream.
            for pair in final_pairs:
                pairs_with_streams.append(
                    replace(
                        pair,
                        response=replace(
                            pair.response,
                            stream=self._stream_data_from_cache(pair.id.bytes),
                        ),
                    )
                )

            return pairs_with_streams

        def update_entry(
            self,
            id: uuid.UUID,
            new_pair: Union[Entry, Callable[[Entry], Entry]],
        ) -> Optional[Entry]:
            # MUST hold the lock: this is a SELECT-modify-UPDATE sequence
            # and concurrent updaters would otherwise lose each other's
            # writes. Removing this lock would silently corrupt entries.
            with self._lock:
                connection = self._ensure_connection()
                cursor = connection.cursor()
                cursor.execute("SELECT data FROM entries WHERE id = ?", (id.bytes,))
                result = cursor.fetchone()

                if result is None:
                    return None

                pair = unpack(result[0], kind="pair")

                # Skip entries without a response (incomplete)
                if not isinstance(pair, Entry) or pair.response is None:
                    return None

                if isinstance(new_pair, Entry):
                    complete_pair = new_pair
                else:
                    complete_pair = new_pair(pair)

                if pair.id != complete_pair.id:
                    raise ValueError("Pair ID mismatch")

                # Single UPDATE setting both columns avoids an extra round trip.
                cursor.execute(
                    "UPDATE entries SET data = ?, cache_key = ? WHERE id = ?",
                    (
                        pack(complete_pair, kind="pair"),
                        complete_pair.cache_key,
                        id.bytes,
                    ),
                )

                connection.commit()

                return complete_pair

        def refresh_entry_ttl(self, id: uuid.UUID) -> None:
            self.update_entry(
                id,
                lambda pair: replace(
                    pair, meta=replace(pair.meta, created_at=time.time())
                ),
            )

        def remove_entry(self, id: uuid.UUID) -> None:
            with self._lock:
                connection = self._ensure_connection()
                cursor = connection.cursor()
                cursor.execute("SELECT data FROM entries WHERE id = ?", (id.bytes,))
                result = cursor.fetchone()

                if result is None:
                    return

                pair = unpack(result[0], kind="pair")
                self._soft_delete_pair(pair, cursor)
                connection.commit()

        def close(self) -> None:
            with self._lock:
                if self.connection is not None:
                    self.connection.close()
                    self.connection = None
                # Reset initialization state so a future reconnection will
                # re-run schema/PRAGMA setup against the new connection.
                self._initialized = False

        def _is_stream_complete(
            self, pair_id: uuid.UUID, cursor: sqlite3.Cursor
        ) -> bool:
            """Caller must hold self._lock."""
            cursor.execute(
                "SELECT 1 FROM streams WHERE entry_id = ? AND chunk_number = ? LIMIT 1",
                (pair_id.bytes, self._COMPLETE_CHUNK_NUMBER),
            )
            return cursor.fetchone() is not None

        def _soft_delete_pair(
            self,
            pair: Entry,
            cursor: sqlite3.Cursor,
        ) -> None:
            """
            Mark the pair as deleted by setting the deleted_at timestamp.

            Caller must hold self._lock.
            """
            marked_pair = self.mark_pair_as_deleted(pair)
            cursor.execute(
                "UPDATE entries SET data = ?, deleted_at = ? WHERE id = ?",
                (
                    pack(marked_pair, kind="pair"),
                    marked_pair.meta.deleted_at,
                    pair.id.bytes,
                ),
            )

        def _is_pair_expired(self, pair: Entry, cursor: sqlite3.Cursor) -> bool:
            """
            Check if the pair is expired.
            """
            ttl = pair.request.metadata.get("hishel_ttl") or self.default_ttl
            created_at = pair.meta.created_at
            if ttl is None:
                return False
            return created_at + ttl < time.time()

        def _batch_cleanup(self) -> None:
            """
            Cleanup expired entries in the database.

            Uses keyset pagination on `id` rather than LIMIT/OFFSET so that
            scans are stable even if rows are mutated between chunks, and so
            that performance does not degrade on large tables.

            Caller must hold self._lock.
            """
            should_mark_as_deleted: List[Entry] = []
            should_hard_delete: List[Entry] = []

            connection = self._ensure_connection()
            cursor = connection.cursor()

            chunk_size = BATCH_CLEANUP_CHUNK_SIZE
            last_id: Optional[bytes] = None
            while True:
                if last_id is None:
                    cursor.execute(
                        "SELECT id, data FROM entries ORDER BY id LIMIT ?",
                        (chunk_size,),
                    )
                else:
                    cursor.execute(
                        "SELECT id, data FROM entries WHERE id > ? ORDER BY id LIMIT ?",
                        (last_id, chunk_size),
                    )
                rows = cursor.fetchall()
                if not rows:
                    break

                for row in rows:
                    pair = unpack(row[1], kind="pair")
                    if pair is None:
                        continue

                    # expired but not yet soft-deleted
                    if self._is_pair_expired(pair, cursor) and not self.is_soft_deleted(
                        pair
                    ):
                        should_mark_as_deleted.append(pair)

                    # soft-deleted and safe to hard delete, or corrupted pair
                    if (
                        self.is_soft_deleted(pair) and self.is_safe_to_hard_delete(pair)
                    ) or self._is_corrupted(pair, cursor):
                        should_hard_delete.append(pair)

                # advance keyset cursor to the last id we saw
                last_id = rows[-1][0]

            for pair in should_mark_as_deleted:
                self._soft_delete_pair(pair, cursor)

            for pair in should_hard_delete:
                self._hard_delete_pair(pair, cursor)

            connection.commit()

            # Record completion time so we don't immediately re-run on the
            # next get_entries call.
            self.last_cleanup = time.time()

        def _is_corrupted(self, pair: Entry, cursor: sqlite3.Cursor) -> bool:
            # If entry was created more than 1 hour ago and still has no
            # complete response stream, treat it as corrupt.
            if pair.meta.created_at + 3600 < time.time() and not (
                self._is_stream_complete(pair.id, cursor)
            ):
                return True
            return False

        def _hard_delete_pair(self, pair: Entry, cursor: sqlite3.Cursor) -> None:
            """
            Permanently delete the pair from the database.

            Stream chunks are removed automatically via ON DELETE CASCADE
            (foreign_keys pragma is enabled in _initialize_database).

            Caller must hold self._lock.
            """
            cursor.execute("DELETE FROM entries WHERE id = ?", (pair.id.bytes,))

        def _save_stream(
            self,
            stream: Iterator[bytes],
            entry_id: bytes,
        ) -> Iterator[bytes]:
            """
            Wrapper around an iterator that also saves the response data
            to the cache in chunks.

            Each chunk insert takes self._lock; the lock is released between
            chunks so user iteration of the stream does not block other DB
            operations.
            """
            chunk_number = 0
            for chunk in stream:
                with self._lock:
                    connection = self._ensure_connection()
                    cursor = connection.cursor()
                    cursor.execute(
                        "INSERT INTO streams (entry_id, chunk_number, chunk_data) VALUES (?, ?, ?)",
                        (entry_id, chunk_number, chunk),
                    )
                    connection.commit()
                chunk_number += 1
                yield chunk

            # Mark end of stream with chunk_number = -1
            with self._lock:
                connection = self._ensure_connection()
                cursor = connection.cursor()
                cursor.execute(
                    "INSERT INTO streams (entry_id, chunk_number, chunk_data) VALUES (?, ?, ?)",
                    (entry_id, self._COMPLETE_CHUNK_NUMBER, b""),
                )
                connection.commit()

        def _stream_data_from_cache(
            self,
            entry_id: bytes,
        ) -> Iterator[bytes]:
            """
            Get an iterator that yields the response stream data from the cache.

            Iteration terminates when no row exists for the next sequential
            chunk_number (the completion marker lives at chunk_number = -1
            and is queried separately by _is_stream_complete, not here).

            Each chunk read takes self._lock; the lock is released between
            chunks so user iteration does not block other DB operations.
            """
            chunk_number = 0

            while True:
                with self._lock:
                    connection = self._ensure_connection()
                    cursor = connection.cursor()
                    cursor.execute(
                        "SELECT chunk_data FROM streams WHERE entry_id = ? AND chunk_number = ?",
                        (entry_id, chunk_number),
                    )
                    result = cursor.fetchone()

                if result is None:
                    break
                yield result[0]
                chunk_number += 1

except ImportError as _import_error:
    _original_error = _import_error

    class SyncSqliteStorage:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "The 'sqlite3' library is required to use the `SyncSqliteStorage` integration. "
                "Install hishel with 'pip install hishel[async]'. "
                f"Original import error: {_original_error!r}"
            )