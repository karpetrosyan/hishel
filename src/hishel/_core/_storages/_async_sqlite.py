from __future__ import annotations

import logging
import time
import uuid
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional, Union

from hishel._core._headers import Headers
from hishel._core._storages._async_base import AsyncBaseStorage
from hishel._core._storages._packing import pack, unpack
from hishel._core.models import Entry, Request, Response
from hishel._utils import ensure_cache_dict, make_async_iterator

logger = logging.getLogger(__name__)

# Stored in `PRAGMA user_version`. A database with any other version is reset,
# since cached data is disposable.
SCHEMA_VERSION = 1
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


if TYPE_CHECKING:
    import anysqlite
    from anyio import Lock
else:
    try:
        import anysqlite
        from anyio import Lock
    except ImportError:
        anysqlite = None
        Lock = None


class AsyncSqliteStorage(AsyncBaseStorage):
    """
    An entry is removed in two steps. Lookups stop returning it as soon as
    expires_at passes, and its row is deleted once it has also gone unused for
    soft_delete_ttl seconds, so that readers already streaming it can finish.
    Active readers and writers keep that window open by updating last_accessed_at.

    Writes are single atomic statements, and anysqlite serialises calls on the
    connection, so no write lock is needed.
    """

    def __init__(
        self,
        *,
        connection: Optional[anysqlite.Connection] = None,
        database_path: Union[str, Path] = "hishel_cache.db",
        default_ttl: float | None = None,
        default_tti: float | None = None,
        max_stream_size: int | None = None,
        max_size: int | None = 1024**3,
        soft_delete_ttl: float = 180,
    ) -> None:
        if anysqlite is None:
            raise ImportError(
                "The 'anysqlite' library is required to use the `AsyncSqliteStorage` integration. "
                "Install hishel with 'pip install hishel[async]'."
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
        self._init_lock = Lock()

    async def _ensure_connection(self) -> anysqlite.Connection:
        if self._closed:
            raise RuntimeError("AsyncSqliteStorage is closed and can no longer be used.")

        if self.connection is not None and self._initialized:
            return self.connection

        async with self._init_lock:
            if self._closed:
                raise RuntimeError("AsyncSqliteStorage is closed and can no longer be used.")
            if self.connection is None:
                parent = self.database_path.parent if self.database_path.parent != Path(".") else None
                full_path = ensure_cache_dict(parent) / self.database_path.name
                self.connection = await anysqlite.connect(str(full_path))
            if not self._initialized:
                await self._initialize_database()
                self._initialized = True
            return self.connection

    async def _initialize_database(self) -> None:
        assert self.connection is not None
        cursor = await self.connection.cursor()

        await cursor.execute("PRAGMA journal_mode=WAL")
        await cursor.execute("PRAGMA busy_timeout=5000")
        await cursor.execute("PRAGMA synchronous=NORMAL")
        await cursor.execute("PRAGMA foreign_keys=ON")
        await cursor.execute(f"PRAGMA journal_size_limit={MAX_WAL_SIZE}")

        await cursor.execute("PRAGMA user_version")
        row = await cursor.fetchone()
        if row[0] == SCHEMA_VERSION:
            return

        await cursor.execute("DROP TABLE IF EXISTS streams")
        await cursor.execute("DROP TABLE IF EXISTS entries")
        await self.connection.commit()
        # Nothing is left to copy, so this is cheap, and it returns the old
        # file's space to the OS.
        await cursor.execute("VACUUM")

        await cursor.execute("""
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
        await cursor.execute("""
            CREATE TABLE IF NOT EXISTS streams (
                entry_id BLOB NOT NULL,
                chunk_number INTEGER NOT NULL,
                chunk_data BLOB NOT NULL,
                PRIMARY KEY (entry_id, chunk_number),
                FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
            )
        """)
        await cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_cache_key ON entries(cache_key)")
        await cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_expires_at ON entries(expires_at)")
        await cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_last_accessed_at ON entries(last_accessed_at)")
        await cursor.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        await self.connection.commit()

    async def create_entry(
        self,
        request: Request,
        response: Response,
        key: str,
        *,
        ttl: float | None = None,
        tti: float | None = None,
    ) -> Entry:
        body = response.stream if response.stream is not None else make_async_iterator([])
        assert isinstance(body, (AsyncIterator, AsyncIterable))
        connection = await self._ensure_connection()

        now = time.time()
        ttl_deadline, tti = self._limits(ttl, tti, now)
        entry = Entry(
            id=uuid.uuid4(),
            request=request,
            response=response,
        )

        try:
            if not await self._reclaim_space(connection, now):
                return entry
            cursor = await connection.cursor()
            await cursor.execute(
                "INSERT INTO entries (id, cache_key, data, expires_at, last_accessed_at, ttl_deadline, tti)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (entry.id.bytes, key.encode("utf-8"), pack(request, response), HIDDEN, now, ttl_deadline, tti),
            )
            await connection.commit()
        except Exception:
            logger.exception("hishel: could not store entry, serving the response uncached")
            return entry

        stream = self._save_stream(body, entry.id.bytes, ttl_deadline, tti, now)
        return replace(entry, response=replace(response, stream=stream))

    async def get_entries(self, key: str) -> List[Entry]:
        connection = await self._ensure_connection()
        cursor = await connection.cursor()
        now = time.time()
        await cursor.execute(
            "SELECT id, data, chunk_count, expires_at, last_accessed_at, ttl_deadline, tti FROM entries"
            " WHERE cache_key = ? AND (expires_at IS NULL OR expires_at > ?)",
            (key.encode("utf-8"), now),
        )

        entries: List[Entry] = []
        for id_, data, chunk_count, expires_at, last_accessed_at, ttl_deadline, tti in await cursor.fetchall():
            try:
                request, response = unpack(bytes(data))
            except Exception:
                logger.exception("hishel: dropping an entry that could not be decoded")
                await self._try_write("UPDATE entries SET expires_at = ? WHERE id = ?", (HIDDEN, id_))
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
                touched = await self._try_write(
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

    async def update_headers(self, id: uuid.UUID, headers: Headers) -> None:
        # The blob is only ever rewritten here, so the last writer winning is
        # the correct result if two revalidations race.
        connection = await self._ensure_connection()
        cursor = await connection.cursor()
        await cursor.execute("SELECT data FROM entries WHERE id = ?", (id.bytes,))
        row = await cursor.fetchone()
        if row is None:
            return

        request, response = unpack(bytes(row[0]))
        updated = pack(request, replace(response, headers=headers))
        await cursor.execute("UPDATE entries SET data = ? WHERE id = ?", (updated, id.bytes))
        await connection.commit()

    async def remove_entry(self, id: uuid.UUID) -> None:
        connection = await self._ensure_connection()
        cursor = await connection.cursor()
        # An entry still being written has no readers to protect, and hiding it
        # would not last: completing the stream sets expires_at.
        await cursor.execute("DELETE FROM entries WHERE id = ? AND chunk_count IS NULL", (id.bytes,))
        await cursor.execute("UPDATE entries SET expires_at = ? WHERE id = ?", (HIDDEN, id.bytes))
        await connection.commit()

    async def close(self) -> None:
        async with self._init_lock:
            self._closed = True
            if self.connection is not None:
                await self.connection.close()
                self.connection = None
            self._initialized = False

    async def _try_write(self, sql: str, parameters: tuple[Any, ...]) -> int | None:
        """
        Run a write that must not fail the request being served.

        Returns how many rows it changed, or None if it failed.
        """
        try:
            connection = await self._ensure_connection()
            cursor = await connection.cursor()
            await cursor.execute(sql, parameters)
            changed = cursor.rowcount
            await connection.commit()
            return changed
        except Exception:
            logger.exception("hishel: cache write failed")
            return None

    async def _reclaim_space(self, connection: anysqlite.Connection, now: float) -> bool:
        """
        Delete a bounded number of rows and return whether there is room for a new entry.

        Abandoned writes are covered too: they stay HIDDEN and stop updating
        last_accessed_at once their writer is gone.
        """
        cursor = await connection.cursor()
        unused_since = now - self.soft_delete_ttl

        await cursor.execute(
            "DELETE FROM entries WHERE id IN ("
            " SELECT id FROM entries WHERE expires_at < ? AND last_accessed_at < ? LIMIT ?)",
            (now, unused_since, CLEANUP_BATCH_SIZE),
        )
        await connection.commit()

        if self.max_size is None:
            return True

        for _ in range(EVICTION_MAX_BATCHES):
            if await self._database_size(cursor) <= self.max_size:
                return True
            await cursor.execute(
                "DELETE FROM entries WHERE id IN ("
                " SELECT id FROM entries WHERE last_accessed_at < ? ORDER BY last_accessed_at LIMIT ?)",
                (unused_since, EVICTION_BATCH_SIZE),
            )
            deleted = cursor.rowcount
            await connection.commit()
            if deleted == 0:
                break

        return await self._database_size(cursor) <= self.max_size

    async def _database_size(self, cursor: anysqlite.Cursor) -> int:
        await cursor.execute(
            "SELECT (page_count - freelist_count) * page_size"
            " FROM pragma_page_count(), pragma_freelist_count(), pragma_page_size()"
        )
        row = await cursor.fetchone()
        return int(row[0])

    async def _save_stream(
        self,
        stream: AsyncIterator[bytes],
        id_: bytes,
        ttl_deadline: float | None,
        tti: float | None,
        last_touch: float,
    ) -> AsyncIterator[bytes]:
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

        async def write_chunk(data: bytes) -> bool:
            nonlocal chunk_number, last_touch
            inserted = await self._try_write(
                "INSERT INTO streams (entry_id, chunk_number, chunk_data) VALUES (?, ?, ?)",
                (id_, chunk_number, data),
            )
            if inserted is None:
                return False
            chunk_number += 1
            now = time.time()
            if now - last_touch >= self._touch_interval:
                last_touch = now
                await self._try_write("UPDATE entries SET last_accessed_at = ? WHERE id = ?", (now, id_))
            return True

        try:
            async for chunk in stream:
                if saving:
                    total_size += len(chunk)
                    if limit is not None and total_size > limit:
                        saving = False
                    else:
                        buffer += chunk
                        while saving and len(buffer) >= STORAGE_CHUNK_SIZE:
                            saving = await write_chunk(bytes(buffer[:STORAGE_CHUNK_SIZE]))
                            del buffer[:STORAGE_CHUNK_SIZE]
                    if not saving:
                        buffer.clear()
                        await self._try_write("DELETE FROM entries WHERE id = ?", (id_,))
                yield chunk

            if saving and buffer:
                saving = await write_chunk(bytes(buffer))
            if saving:
                now = time.time()
                updated = await self._try_write(
                    "UPDATE entries SET chunk_count = ?, expires_at = ?, last_accessed_at = ? WHERE id = ?",
                    (chunk_number, self._expires_at(ttl_deadline, tti, now), now, id_),
                )
                completed = bool(updated)
        finally:
            # Upstream failed or the consumer stopped reading. If this gets
            # cancelled too, _reclaim_space removes the row later.
            if not completed:
                await self._try_write("DELETE FROM entries WHERE id = ?", (id_,))

    async def _stream_from_cache(
        self,
        id_: bytes,
        chunk_count: int,
        last_touch: float,
    ) -> AsyncIterator[bytes]:
        for chunk_number in range(chunk_count):
            connection = await self._ensure_connection()
            cursor = await connection.cursor()
            await cursor.execute(
                "SELECT chunk_data FROM streams WHERE entry_id = ? AND chunk_number = ?",
                (id_, chunk_number),
            )
            row = await cursor.fetchone()
            if row is None:
                raise RuntimeError(
                    "Cached response was deleted while it was being read. "
                    "Increase soft_delete_ttl if consumers stall for longer than that."
                )

            now = time.time()
            if now - last_touch >= self._touch_interval:
                last_touch = now
                await self._try_write("UPDATE entries SET last_accessed_at = ? WHERE id = ?", (now, id_))

            yield row[0]
