from __future__ import annotations

import logging
import time
import uuid
import warnings
from dataclasses import replace
from pathlib import Path
from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Callable,
    List,
    Optional,
    Union,
)

from hishel._core._storages._async_base import AsyncBaseStorage
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


try:
    import anysqlite
    from anyio import Lock

    class AsyncSqliteStorage(AsyncBaseStorage):
        _COMPLETE_CHUNK_NUMBER = -1

        def __init__(
            self,
            *,
            connection: Optional[anysqlite.Connection] = None,
            database_path: Union[str, Path] = "hishel_cache.db",
            default_ttl: Optional[float] = None,
            refresh_ttl_on_access: bool | None = None,
        ) -> None:
            if isinstance(refresh_ttl_on_access, bool):
                warnings.warn("The 'refresh_ttl_on_access' parameter is deprecated and has no effect. ")

            self.connection = connection
            self.database_path: Path = database_path if isinstance(database_path, Path) else Path(database_path)
            self.default_ttl = default_ttl
            self.last_cleanup = time.time() - BATCH_CLEANUP_INTERVAL + BATCH_CLEANUP_START_DELAY
            # When this storage instance was created. Used to delay the first cleanup.
            self._start_time = time.time()
            self._initialized = False
            # _init_lock serialises the lazy connection-and-schema setup in
            # _ensure_connection so concurrent first-time callers cannot both
            # open a connection or both run CREATE TABLE / PRAGMA setup.
            #
            # _write_lock serialises read-modify-write sequences (update_entry,
            # remove_entry, _batch_cleanup). Pure single-statement reads and
            # writes do NOT need this lock: anysqlite already serialises
            # cursor calls on a single Connection via its internal
            self._init_lock = Lock()
            self._write_lock = Lock()

        async def _ensure_connection(self) -> anysqlite.Connection:
            """
            Ensure connection is established and database is initialized.

            Safe to call concurrently: uses _init_lock with double-checked
            locking so the fast path (already initialised) does not take the
            lock at all, and the slow path opens the connection and runs
            schema setup exactly once.
            """
            # Fast path: already initialised. No lock needed because both
            # fields, once set, are only mutated under _init_lock and the
            # only writer that resets them (close()) takes _init_lock too.
            if self.connection is not None and self._initialized:
                return self.connection

            async with self._init_lock:
                # Re-check inside the lock; another task may have raced us.
                if self.connection is None:
                    # Create cache directory and resolve full path on first connection
                    parent = self.database_path.parent if self.database_path.parent != Path(".") else None
                    full_path = ensure_cache_dict(parent) / self.database_path.name
                    self.connection = await anysqlite.connect(str(full_path))
                if not self._initialized:
                    await self._initialize_database()
                    self._initialized = True
                return self.connection

        async def _initialize_database(self) -> None:
            """Initialize the database schema and configure the connection."""
            assert self.connection is not None
            cursor = await self.connection.cursor()

            # Configure connection for cache workload:
            # - WAL allows concurrent readers during writes
            # - busy_timeout avoids SQLITE_BUSY errors under contention
            # - synchronous=NORMAL is the right durability/perf tradeoff for a cache
            # - foreign_keys enables ON DELETE CASCADE enforcement
            await cursor.execute("PRAGMA journal_mode=WAL")
            await cursor.execute("PRAGMA busy_timeout=5000")
            await cursor.execute("PRAGMA synchronous=NORMAL")
            await cursor.execute("PRAGMA foreign_keys=ON")

            # Table for storing request/response pairs
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    id BLOB PRIMARY KEY,
                    cache_key BLOB,
                    data BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    deleted_at REAL
                )
            """)

            # Table for storing response stream chunks only
            await cursor.execute("""
                CREATE TABLE IF NOT EXISTS streams (
                    entry_id BLOB NOT NULL,
                    chunk_number INTEGER NOT NULL,
                    chunk_data BLOB NOT NULL,
                    PRIMARY KEY (entry_id, chunk_number),
                    FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
                )
            """)

            # Indexes for performance
            await cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_deleted_at ON entries(deleted_at)")
            await cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_cache_key ON entries(cache_key)")

            await self.connection.commit()

        async def create_entry(
            self, request: Request, response: Response, key: str, id_: uuid.UUID | None = None
        ) -> Entry:
            key_bytes = key.encode("utf-8")

            # No write_lock needed: this is a single INSERT (atomic at the
            # SQLite level) and anysqlite serialises cursor access on the
            # connection internally. The streaming response is consumed by
            # the caller after this returns; _save_stream handles its own
            # writes per chunk.
            connection = await self._ensure_connection()
            cursor = await connection.cursor()

            # Create a new entry directly with both request and response
            pair_id = id_ if id_ is not None else uuid.uuid4()
            pair_meta = EntryMeta(
                created_at=time.time(),
            )

            assert isinstance(response.stream, (AsyncIterator, AsyncIterable))
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

            # Insert the complete entry into the database
            await cursor.execute(
                "INSERT INTO entries (id, cache_key, data, created_at, deleted_at) VALUES (?, ?, ?, ?, ?)",
                (pair_id.bytes, key_bytes, pack(complete_entry, kind="pair"), pair_meta.created_at, None),
            )
            await connection.commit()

            return complete_entry

        async def get_entries(self, key: str) -> List[Entry]:
            final_pairs: List[Entry] = []

            now = time.time()
            if now - self.last_cleanup >= BATCH_CLEANUP_INTERVAL:
                # _batch_cleanup performs writes (soft/hard deletes) that can
                # race with update_entry / remove_entry, so it must run under
                # the write lock. Pure reads below do not need it.
                async with self._write_lock:
                    # Re-check inside the lock so we don't run cleanup twice
                    # if multiple readers raced past the outer check.
                    if now - self.last_cleanup >= BATCH_CLEANUP_INTERVAL:
                        try:
                            await self._batch_cleanup()
                        except Exception:
                            # don't let cleanup prevent reads; failures are non-fatal
                            # but we log so problems are visible instead of silent
                            logger.exception("hishel: batch cleanup failed")

            connection = await self._ensure_connection()
            cursor = await connection.cursor()
            # Query entries directly by cache_key. anysqlite serialises this
            # cursor's calls against any other concurrent operation on the
            # connection, so we don't need an application-level lock.
            await cursor.execute(
                "SELECT id, data FROM entries WHERE cache_key = ?",
                (key.encode("utf-8"),),
            )

            for row in await cursor.fetchall():
                pair_data = unpack(row[1], kind="pair")

                if pair_data is None:
                    continue

                # Skip entries without a response (incomplete)
                if not await self._is_stream_complete(pair_data.id, cursor=cursor):
                    continue

                # Skip expired entries
                if await self._is_pair_expired(pair_data, cursor=cursor):
                    continue

                # Skip soft-deleted entries
                if self.is_soft_deleted(pair_data):
                    continue

                final_pairs.append(pair_data)

            pairs_with_streams: List[Entry] = []

            # Only restore response streams from cache
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

        async def update_entry(
            self,
            id: uuid.UUID,
            new_pair: Union[Entry, Callable[[Entry], Entry]],
        ) -> Optional[Entry]:
            # MUST hold _write_lock: this is a SELECT-modify-UPDATE sequence
            # and concurrent updaters would otherwise lose each other's
            # writes. Removing this lock would silently corrupt entries.
            async with self._write_lock:
                connection = await self._ensure_connection()
                cursor = await connection.cursor()
                await cursor.execute("SELECT data FROM entries WHERE id = ?", (id.bytes,))
                result = await cursor.fetchone()

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
                await cursor.execute(
                    "UPDATE entries SET data = ?, cache_key = ? WHERE id = ?",
                    (pack(complete_pair, kind="pair"), complete_pair.cache_key, id.bytes),
                )

                await connection.commit()

                return complete_pair

        async def refresh_entry_ttl(self, id: uuid.UUID) -> None:
            await self.update_entry(
                id,
                lambda pair: replace(
                    pair,
                    meta=replace(pair.meta, created_at=time.time()),
                ),
            )

        async def remove_entry(self, id: uuid.UUID) -> None:
            # MUST hold _write_lock: SELECT then soft-delete UPDATE. Without
            # the lock, a concurrent update_entry could clobber the soft
            # delete or vice versa.
            async with self._write_lock:
                connection = await self._ensure_connection()
                cursor = await connection.cursor()
                await cursor.execute("SELECT data FROM entries WHERE id = ?", (id.bytes,))
                result = await cursor.fetchone()

                if result is None:
                    return

                pair = unpack(result[0], kind="pair")
                await self._soft_delete_pair(pair, cursor)
                await connection.commit()

        async def close(self) -> None:
            # Drain both write and init paths before tearing down the
            # connection. Acquisition order: _write_lock first, _init_lock
            # second. This is the only place that holds both, so no other
            # site can deadlock against us.
            async with self._write_lock, self._init_lock:
                if self.connection is not None:
                    await self.connection.close()
                    self.connection = None
                # Reset initialization state so a future reconnection will
                # re-run schema/PRAGMA setup against the new connection.
                self._initialized = False

        async def _is_stream_complete(self, pair_id: uuid.UUID, cursor: anysqlite.Cursor) -> bool:
            # Check if there's a completion marker (chunk_number = -1) for response stream
            await cursor.execute(
                "SELECT 1 FROM streams WHERE entry_id = ? AND chunk_number = ? LIMIT 1",
                (pair_id.bytes, self._COMPLETE_CHUNK_NUMBER),
            )
            return await cursor.fetchone() is not None

        async def _soft_delete_pair(
            self,
            pair: Entry,
            cursor: anysqlite.Cursor,
        ) -> None:
            """
            Mark the pair as deleted by setting the deleted_at timestamp.
            """
            marked_pair = self.mark_pair_as_deleted(pair)
            await cursor.execute(
                "UPDATE entries SET data = ?, deleted_at = ? WHERE id = ?",
                (
                    pack(marked_pair, kind="pair"),
                    marked_pair.meta.deleted_at,
                    pair.id.bytes,
                ),
            )

        async def _is_pair_expired(self, pair: Entry, cursor: anysqlite.Cursor) -> bool:
            """
            Check if the pair is expired.
            """
            ttl = pair.request.metadata.get("hishel_ttl") or self.default_ttl
            created_at = pair.meta.created_at
            if ttl is None:
                return False
            return created_at + ttl < time.time()

        async def _batch_cleanup(
            self,
        ) -> None:
            """
            Cleanup expired entries in the database.

            Uses keyset pagination on `id` rather than LIMIT/OFFSET so that
            scans are stable even if rows are mutated between chunks, and so
            that performance does not degrade on large tables.
            """
            should_mark_as_deleted: List[Entry] = []
            should_hard_delete: List[Entry] = []

            connection = await self._ensure_connection()
            cursor = await connection.cursor()

            chunk_size = BATCH_CLEANUP_CHUNK_SIZE
            last_id: Optional[bytes] = None
            while True:
                if last_id is None:
                    await cursor.execute(
                        "SELECT id, data FROM entries ORDER BY id LIMIT ?",
                        (chunk_size,),
                    )
                else:
                    await cursor.execute(
                        "SELECT id, data FROM entries WHERE id > ? ORDER BY id LIMIT ?",
                        (last_id, chunk_size),
                    )
                rows = await cursor.fetchall()
                if not rows:
                    break

                for row in rows:
                    pair = unpack(row[1], kind="pair")
                    if pair is None:
                        continue

                    # expired but not yet soft-deleted
                    if await self._is_pair_expired(pair, cursor) and not self.is_soft_deleted(pair):
                        should_mark_as_deleted.append(pair)

                    # soft-deleted and safe to hard delete, or corrupted pair
                    if (self.is_soft_deleted(pair) and self.is_safe_to_hard_delete(pair)) or await self._is_corrupted(
                        pair, cursor
                    ):
                        should_hard_delete.append(pair)

                # advance keyset cursor to the last id we saw
                last_id = rows[-1][0]

            for pair in should_mark_as_deleted:
                await self._soft_delete_pair(pair, cursor)

            for pair in should_hard_delete:
                await self._hard_delete_pair(pair, cursor)

            await connection.commit()

            # Record completion time so we don't immediately re-run on the
            # next get_entries call.
            self.last_cleanup = time.time()

        async def _is_corrupted(self, pair: Entry, cursor: anysqlite.Cursor) -> bool:
            # if entry was created more than 1 hour ago and still has no full response data
            if pair.meta.created_at + 3600 < time.time() and not (await self._is_stream_complete(pair.id, cursor)):
                return True
            return False

        async def _hard_delete_pair(self, pair: Entry, cursor: anysqlite.Cursor) -> None:
            """
            Permanently delete the pair from the database.

            Stream chunks are removed automatically via ON DELETE CASCADE
            (foreign_keys pragma is enabled in _initialize_database).
            """
            await cursor.execute("DELETE FROM entries WHERE id = ?", (pair.id.bytes,))

        async def _save_stream(
            self,
            stream: AsyncIterator[bytes],
            entry_id: bytes,
        ) -> AsyncIterator[bytes]:
            """
            Wrapper around an async iterator that also saves the response data
            to the cache in chunks.

            No locking needed: each INSERT is a single statement and atomic at
            the SQLite level, anysqlite serialises cursor calls on the
            connection internally, and only this entry's own writer can be
            inserting into its (entry_id, chunk_number) key space (a duplicate
            would be a caller bug, not a race).
            """
            chunk_number = 0
            async for chunk in stream:
                connection = await self._ensure_connection()
                cursor = await connection.cursor()
                await cursor.execute(
                    "INSERT INTO streams (entry_id, chunk_number, chunk_data) VALUES (?, ?, ?)",
                    (entry_id, chunk_number, chunk),
                )
                await connection.commit()
                chunk_number += 1
                yield chunk

            # Mark end of stream with chunk_number = -1
            connection = await self._ensure_connection()
            cursor = await connection.cursor()
            await cursor.execute(
                "INSERT INTO streams (entry_id, chunk_number, chunk_data) VALUES (?, ?, ?)",
                (entry_id, self._COMPLETE_CHUNK_NUMBER, b""),
            )
            await connection.commit()

        async def _stream_data_from_cache(
            self,
            entry_id: bytes,
        ) -> AsyncIterator[bytes]:
            """
            Get an async iterator that yields the response stream data from the cache.

            Iteration terminates when no row exists for the next sequential
            chunk_number (the completion marker lives at chunk_number = -1 and
            is queried separately by _is_stream_complete, not here).

            No locking needed: each iteration is a single SELECT, and
            anysqlite serialises cursor calls on the connection internally.
            """
            chunk_number = 0

            while True:
                connection = await self._ensure_connection()
                cursor = await connection.cursor()
                await cursor.execute(
                    "SELECT chunk_data FROM streams WHERE entry_id = ? AND chunk_number = ?",
                    (entry_id, chunk_number),
                )
                result = await cursor.fetchone()

                if result is None:
                    break
                yield result[0]
                chunk_number += 1

except ImportError as _import_error:
    _original_error = _import_error

    class AsyncSqliteStorage:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "The 'anysqlite' library is required to use the `AsyncSqliteStorage` integration. "
                "Install hishel with 'pip install hishel[async]'. "
                f"Original import error: {_original_error!r}"
            )
