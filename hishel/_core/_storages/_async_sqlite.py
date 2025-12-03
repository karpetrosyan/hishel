from __future__ import annotations

import time
import uuid
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

# Batch cleanup configuration
# How often to run cleanup (seconds). Default: 1 hour.
BATCH_CLEANUP_INTERVAL = 3600
# How long to wait after storage creation before allowing the first cleanup (seconds)
BATCH_CLEANUP_START_DELAY = 5 * 60
# Number of rows to process per chunk when cleaning
BATCH_CLEANUP_CHUNK_SIZE = 200


try:
    import anysqlite

    class AsyncSqliteStorage(AsyncBaseStorage):
        _COMPLETE_CHUNK_NUMBER = -1

        def __init__(
            self,
            *,
            connection: Optional[anysqlite.Connection] = None,
            database_path: Union[str, Path] = "hishel_cache.db",
            default_ttl: Optional[float] = None,
            refresh_ttl_on_access: bool = True,
        ) -> None:
            self.connection = connection
            self.database_path: Path = database_path if isinstance(database_path, Path) else Path(database_path)
            self.default_ttl = default_ttl
            self.refresh_ttl_on_access = refresh_ttl_on_access
            self.last_cleanup = time.time() - BATCH_CLEANUP_INTERVAL + BATCH_CLEANUP_START_DELAY
            # When this storage instance was created. Used to delay the first cleanup.
            self._start_time = time.time()
            self._initialized = False

        async def _ensure_connection(self) -> anysqlite.Connection:
            """Ensure connection is established and database is initialized."""
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
            """Initialize the database schema."""
            assert self.connection is not None
            cursor = await self.connection.cursor()

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
                try:
                    await self._batch_cleanup()
                except Exception:
                    # don't let cleanup prevent reads; failures are non-fatal
                    pass

            connection = await self._ensure_connection()
            cursor = await connection.cursor()
            # Query entries directly by cache_key
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

            await cursor.execute(
                "UPDATE entries SET data = ? WHERE id = ?",
                (pack(complete_pair, kind="pair"), id.bytes),
            )

            if pair.cache_key != complete_pair.cache_key:
                await cursor.execute(
                    "UPDATE entries SET cache_key = ? WHERE id = ?",
                    (complete_pair.cache_key, complete_pair.id.bytes),
                )

            await connection.commit()

            return complete_pair

        async def remove_entry(self, id: uuid.UUID) -> None:
            connection = await self._ensure_connection()
            cursor = await connection.cursor()
            await cursor.execute("SELECT data FROM entries WHERE id = ?", (id.bytes,))
            result = await cursor.fetchone()

            if result is None:
                return None

            pair = unpack(result[0], kind="pair")
            await self._soft_delete_pair(pair, cursor)
            await connection.commit()

        async def close(self) -> None:
            if self.connection is not None:
                await self.connection.close()
                self.connection = None

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
            ttl = pair.request.metadata["hishel_ttl"] if "hishel_ttl" in pair.request.metadata else self.default_ttl
            created_at = pair.meta.created_at
            if ttl is None:
                return False
            return created_at + ttl < time.time()

        async def _batch_cleanup(
            self,
        ) -> None:
            """
            Cleanup expired entries in the database.
            """
            should_mark_as_deleted: List[Entry] = []
            should_hard_delete: List[Entry] = []

            connection = await self._ensure_connection()
            cursor = await connection.cursor()

            # Process entries in chunks to avoid loading the entire table into memory.
            chunk_size = BATCH_CLEANUP_CHUNK_SIZE
            offset = 0
            while True:
                await cursor.execute(
                    "SELECT id, data FROM entries LIMIT ? OFFSET ?",
                    (chunk_size, offset),
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

                # advance pagination
                offset += len(rows)

            for pair in should_mark_as_deleted:
                await self._soft_delete_pair(pair, cursor)

            for pair in should_hard_delete:
                await self._hard_delete_pair(pair, cursor)

            await connection.commit()

        async def _is_corrupted(self, pair: Entry, cursor: anysqlite.Cursor) -> bool:
            # if entry was created more than 1 hour ago and still has no full response data
            if pair.meta.created_at + 3600 < time.time() and not (await self._is_stream_complete(pair.id, cursor)):
                return True
            return False

        async def _hard_delete_pair(self, pair: Entry, cursor: anysqlite.Cursor) -> None:
            """
            Permanently delete the pair from the database.
            """
            await cursor.execute("DELETE FROM entries WHERE id = ?", (pair.id.bytes,))

            # Delete response stream for this entry
            await self._delete_stream(pair.id.bytes, cursor)

        async def _delete_stream(
            self,
            entry_id: bytes,
            cursor: anysqlite.Cursor,
        ) -> None:
            """
            Delete response stream associated with the given entry ID.
            """
            await cursor.execute("DELETE FROM streams WHERE entry_id = ?", (entry_id,))

        async def _save_stream(
            self,
            stream: AsyncIterator[bytes],
            entry_id: bytes,
        ) -> AsyncIterator[bytes]:
            """
            Wrapper around an async iterator that also saves the response data to the cache in chunks.
            """
            chunk_number = 0
            content_length = 0
            async for chunk in stream:
                content_length += len(chunk)
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
            """
            chunk_number = 0

            connection = await self._ensure_connection()
            while True:
                cursor = await connection.cursor()
                await cursor.execute(
                    "SELECT chunk_data FROM streams WHERE entry_id = ? AND chunk_number = ?",
                    (entry_id, chunk_number),
                )
                result = await cursor.fetchone()

                if result is None:
                    break
                chunk = result[0]
                # chunk_number = -1 is the completion marker with empty data
                if chunk == b"":
                    break
                yield chunk
                chunk_number += 1

except ImportError:

    class AsyncSqliteStorage:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "The 'anysqlite' library is required to use the `AsyncSqliteStorage` integration. "
                "Install hishel with 'pip install hishel[async]'."
            )
