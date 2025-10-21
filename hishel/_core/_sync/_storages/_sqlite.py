from __future__ import annotations

import time
import uuid
from dataclasses import replace
from typing import (
    Iterable,
    Iterator,
    Callable,
    List,
    Literal,
    Optional,
    Union,
)

from hishel._core._base._storages._base import SyncBaseStorage, ensure_cache_dict
from hishel._core._base._storages._packing import pack, unpack
from hishel._core.models import (
    CompletePair,
    IncompletePair,
    Pair,
    PairMeta,
    Request,
    Response,
)

# Batch cleanup configuration
# How often to run cleanup (seconds). Default: 1 hour.
BATCH_CLEANUP_INTERVAL = 3600
# How long to wait after storage creation before allowing the first cleanup (seconds)
BATCH_CLEANUP_START_DELAY = 5 * 60
# Number of rows to process per chunk when cleaning
BATCH_CLEANUP_CHUNK_SIZE = 200


try:
    import sqlite3

    class SyncSqliteStorage(SyncBaseStorage):
        _STREAM_KIND = {"request": 0, "response": 1}
        _COMPLETE_CHUNK_NUMBER = -1

        def __init__(
            self,
            *,
            connection: Optional[sqlite3.Connection] = None,
            database_path: str = "hishel_cache.db",
            default_ttl: Optional[float] = None,
            refresh_ttl_on_access: bool = True,
        ) -> None:
            base_path = ensure_cache_dict()

            self.connection = connection
            self.database_path = base_path / database_path
            self.default_ttl = default_ttl
            self.refresh_ttl_on_access = refresh_ttl_on_access
            self.last_cleanup = time.time() - BATCH_CLEANUP_INTERVAL + BATCH_CLEANUP_START_DELAY
            # When this storage instance was created. Used to delay the first cleanup.
            self._start_time = time.time()
            self._initialized = False

        def _ensure_connection(self) -> sqlite3.Connection:
            """Ensure connection is established and database is initialized."""
            if self.connection is None:
                self.connection = sqlite3.connect(str(self.database_path))
            if not self._initialized:
                self._initialize_database()
                self._initialized = True
            return self.connection

        def _initialize_database(self) -> None:
            """Initialize the database schema."""
            assert self.connection is not None
            cursor = self.connection.cursor()

            # Table for storing request/response pairs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS entries (
                    id BLOB PRIMARY KEY,
                    cache_key BLOB,
                    data BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    deleted_at REAL
                )
            """)

            # Table for storing stream chunks
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS streams (
                    entry_id BLOB NOT NULL,
                    kind INTEGER NOT NULL,
                    chunk_number INTEGER NOT NULL,
                    chunk_data BLOB NOT NULL,
                    PRIMARY KEY (entry_id, kind, chunk_number),
                    FOREIGN KEY (entry_id) REFERENCES entries(id) ON DELETE CASCADE
                )
            """)

            # Indexes for performance
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_deleted_at ON entries(deleted_at)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_entries_cache_key ON entries(cache_key)")
            # Note: PRIMARY KEY (entry_id, kind, chunk_number) already provides an index
            # for queries like: entry_id = ? AND kind = ? AND chunk_number = ?

            self.connection.commit()

        def create_pair(
            self,
            request: Request,
            id: uuid.UUID | None = None,
        ) -> IncompletePair:
            pair_id = id if id is not None else uuid.uuid4()
            pair_meta = PairMeta(
                created_at=time.time(),
            )

            pair = IncompletePair(id=pair_id, request=request, meta=pair_meta)

            packed_pair = pack(pair, kind="pair")

            connection = self._ensure_connection()
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO entries (id, cache_key, data, created_at, deleted_at) VALUES (?, ?, ?, ?, ?)",
                (pair_id.bytes, None, packed_pair, pair_meta.created_at, None),
            )
            connection.commit()

            assert isinstance(request.stream, Iterable), "Request stream must be an Iterable, not Iterable"

            request = Request(
                method=request.method,
                url=request.url,
                headers=request.headers,
                metadata=request.metadata,
                stream=self._save_stream(request.stream, pair_id.bytes, "request"),
            )

            return replace(pair, request=request)

        def add_response(
            self,
            pair_id: uuid.UUID,
            response: Response,
            key: str | bytes,
        ) -> CompletePair:
            if isinstance(key, str):
                key = key.encode("utf-8")

            connection = self._ensure_connection()
            cursor = connection.cursor()

            # Get the existing pair
            cursor.execute("SELECT data FROM entries WHERE id = ?", (pair_id.bytes,))
            result = cursor.fetchone()

            if result is None:
                raise ValueError(f"Entry with ID {pair_id} not found.")

            pair = unpack(result[0], kind="pair")

            assert isinstance(response.stream, (Iterator, Iterable))
            response = replace(response, stream=self._save_stream(response.stream, pair_id.bytes, "response"))

            self._delete_stream(pair.id.bytes, cursor, type="response")
            complete_pair = CompletePair(
                id=pair.id, request=pair.request, response=response, meta=pair.meta, cache_key=key
            )

            # Update the entry with the complete pair and set cache_key
            cursor.execute(
                "UPDATE entries SET data = ?, cache_key = ? WHERE id = ?",
                (pack(complete_pair, kind="pair"), key, pair_id.bytes),
            )
            connection.commit()

            return complete_pair

        def get_pairs(self, key: str) -> List[CompletePair]:
            final_pairs: List[CompletePair] = []

            now = time.time()
            if now - self.last_cleanup >= BATCH_CLEANUP_INTERVAL:
                try:
                    self._batch_cleanup()
                except Exception:
                    # don't let cleanup prevent reads; failures are non-fatal
                    pass

            connection = self._ensure_connection()
            cursor = connection.cursor()
            # Query entries directly by cache_key
            cursor.execute("SELECT id, data FROM entries WHERE cache_key = ?", (key.encode("utf-8"),))

            for row in cursor.fetchall():
                pair_data = unpack(row[1], kind="pair")

                if isinstance(pair_data, IncompletePair):
                    continue

                final_pairs.append(pair_data)

            pairs_with_streams: List[CompletePair] = []

            for pair in final_pairs:
                pairs_with_streams.append(
                    replace(
                        pair,
                        response=replace(
                            pair.response,
                            stream=self._stream_data_from_cache(pair.id.bytes, "response"),
                        ),
                        request=replace(
                            pair.request,
                            stream=self._stream_data_from_cache(pair.id.bytes, "request"),
                        ),
                    )
                )
            return pairs_with_streams

        def update_pair(
            self,
            id: uuid.UUID,
            new_pair: Union[CompletePair, Callable[[CompletePair], CompletePair]],
        ) -> Optional[CompletePair]:
            connection = self._ensure_connection()
            cursor = connection.cursor()
            cursor.execute("SELECT data FROM entries WHERE id = ?", (id.bytes,))
            result = cursor.fetchone()

            if result is None:
                return None

            pair = unpack(result[0], kind="pair")

            if isinstance(pair, IncompletePair):
                return None

            if isinstance(new_pair, CompletePair):
                complete_pair = new_pair
            else:
                complete_pair = new_pair(pair)

            if pair.id != complete_pair.id:
                raise ValueError("Pair ID mismatch")

            cursor.execute(
                "UPDATE entries SET data = ? WHERE id = ?", (pack(complete_pair, kind="pair"), id.bytes)
            )

            if pair.cache_key != complete_pair.cache_key:
                cursor.execute(
                    "UPDATE entries SET cache_key = ? WHERE id = ?",
                    (complete_pair.cache_key, complete_pair.id.bytes),
                )

            connection.commit()

            return complete_pair

        def remove(self, id: uuid.UUID) -> None:
            connection = self._ensure_connection()
            cursor = connection.cursor()
            cursor.execute("SELECT data FROM entries WHERE id = ?", (id.bytes,))
            result = cursor.fetchone()

            if result is None:
                return None

            pair = unpack(result[0], kind="pair")
            self._soft_delete_pair(pair, cursor)
            connection.commit()

        def _is_stream_complete(
            self, kind: Literal["request", "response"], pair_id: uuid.UUID, cursor: sqlite3.Cursor
        ) -> bool:
            kind_id = self._STREAM_KIND[kind]
            # Check if there's a completion marker (chunk_number = -1)
            cursor.execute(
                "SELECT 1 FROM streams WHERE entry_id = ? AND kind = ? AND chunk_number = ? LIMIT 1",
                (pair_id.bytes, kind_id, self._COMPLETE_CHUNK_NUMBER),
            )
            return cursor.fetchone() is not None

        def _soft_delete_pair(self, pair: Union[CompletePair, IncompletePair], cursor: sqlite3.Cursor) -> None:
            """
            Mark the pair as deleted by setting the deleted_at timestamp.
            """
            marked_pair = self.mark_pair_as_deleted(pair)
            cursor.execute(
                "UPDATE entries SET data = ?, deleted_at = ? WHERE id = ?",
                (pack(marked_pair, kind="pair"), marked_pair.meta.deleted_at, pair.id.bytes),
            )

        def _is_pair_expired(self, pair: Pair, cursor: sqlite3.Cursor) -> bool:
            """
            Check if the pair is expired.
            """
            ttl = pair.request.metadata["hishel_ttl"] if "hishel_ttl" in pair.request.metadata else self.default_ttl
            created_at = pair.meta.created_at
            if ttl is None:
                return False
            return created_at + ttl < time.time()

        def _batch_cleanup(
            self,
        ) -> None:
            """
            Cleanup expired pairs in the database.
            """
            should_mark_as_deleted: List[Union[CompletePair, IncompletePair]] = []
            should_hard_delete: List[Union[CompletePair, IncompletePair]] = []

            connection = self._ensure_connection()
            cursor = connection.cursor()

            # Process entries in chunks to avoid loading the entire table into memory.
            chunk_size = BATCH_CLEANUP_CHUNK_SIZE
            offset = 0
            while True:
                cursor.execute("SELECT id, data FROM entries LIMIT ? OFFSET ?", (chunk_size, offset))
                rows = cursor.fetchall()
                if not rows:
                    break

                for row in rows:
                    pair = unpack(row[1], kind="pair")
                    if pair is None:
                        continue

                    # expired but not yet soft-deleted
                    if self._is_pair_expired(pair, cursor) and not self.is_soft_deleted(pair):
                        should_mark_as_deleted.append(pair)

                    # soft-deleted and safe to hard delete, or corrupted pair
                    if (self.is_soft_deleted(pair) and self.is_safe_to_hard_delete(pair)) or self._is_corrupted(
                        pair, cursor
                    ):
                        should_hard_delete.append(pair)

                # advance pagination
                offset += len(rows)

            for pair in should_mark_as_deleted:
                self._soft_delete_pair(pair, cursor)

            for pair in should_hard_delete:
                self._hard_delete_pair(pair, cursor)

            connection.commit()

        def _is_corrupted(self, pair: IncompletePair | CompletePair, cursor: sqlite3.Cursor) -> bool:
            # if pair was created more than 1 hour ago and still not completed
            if pair.meta.created_at + 3600 < time.time() and isinstance(pair, IncompletePair):
                return True

            if isinstance(pair, CompletePair) and not self._is_stream_complete("request", pair.id, cursor):
                return True
            return False

        def _hard_delete_pair(self, pair: CompletePair | IncompletePair, cursor: sqlite3.Cursor) -> None:
            """
            Permanently delete the pair from the database.
            """
            cursor.execute("DELETE FROM entries WHERE id = ?", (pair.id.bytes,))

            # Delete all streams (both request and response) for this entry
            self._delete_stream(pair.id.bytes, cursor)

        def _delete_stream(
            self,
            entry_id: bytes,
            cursor: sqlite3.Cursor,
            type: Literal["request", "response", "all"] = "all",
        ) -> None:
            """
            Delete all streams (both request and response) associated with the given entry ID.
            """
            if type == "request":
                cursor.execute(
                    "DELETE FROM streams WHERE entry_id = ? AND kind = ?", (entry_id, self._STREAM_KIND["request"])
                )
            elif type == "response":
                cursor.execute(
                    "DELETE FROM streams WHERE entry_id = ? AND kind = ?", (entry_id, self._STREAM_KIND["response"])
                )
            elif type == "all":
                cursor.execute("DELETE FROM streams WHERE entry_id = ?", (entry_id,))

        def _save_stream(
            self,
            stream: Iterator[bytes],
            entry_id: bytes,
            kind: Literal["response", "request"],
        ) -> Iterator[bytes]:
            """
            Wrapper around an async iterator that also saves the data to the cache in chunks.
            """
            kind_id = self._STREAM_KIND[kind]
            chunk_number = 0
            for chunk in stream:
                connection = self._ensure_connection()
                cursor = connection.cursor()
                cursor.execute(
                    "INSERT INTO streams (entry_id, kind, chunk_number, chunk_data) VALUES (?, ?, ?, ?)",
                    (entry_id, kind_id, chunk_number, chunk),
                )
                connection.commit()
                chunk_number += 1
                yield chunk

            # Mark end of stream with chunk_number = -1
            connection = self._ensure_connection()
            cursor = connection.cursor()
            cursor.execute(
                "INSERT INTO streams (entry_id, kind, chunk_number, chunk_data) VALUES (?, ?, ?, ?)",
                (entry_id, kind_id, self._COMPLETE_CHUNK_NUMBER, b""),
            )
            connection.commit()

        def _stream_data_from_cache(
            self,
            entry_id: bytes,
            kind: Literal["response", "request"],
        ) -> Iterator[bytes]:
            """
            Get an async iterator that yields the stream data from the cache.
            """
            kind_id = self._STREAM_KIND[kind]
            chunk_number = 0

            connection = self._ensure_connection()
            while True:
                cursor = connection.cursor()
                cursor.execute(
                    "SELECT chunk_data FROM streams WHERE entry_id = ? AND kind = ? AND chunk_number = ?",
                    (entry_id, kind_id, chunk_number),
                )
                result = cursor.fetchone()

                if result is None:
                    break
                chunk = result[0]
                # chunk_number = -1 is the completion marker with empty data
                if chunk == b"":
                    break
                yield chunk
                chunk_number += 1
except ImportError:

    class SyncSqliteStorage(SyncBaseStorage):
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "The 'sqlite3' library is required to use the `SyncSqliteStorage` integration. "
                "Install hishel with 'pip install hishel[async]'."
            )
