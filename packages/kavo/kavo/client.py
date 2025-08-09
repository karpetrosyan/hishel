from __future__ import annotations

import uuid
from contextlib import asynccontextmanager, contextmanager
from time import sleep
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterable,
    AsyncIterator,
    Iterable,
    Iterator,
    Mapping,
    Optional,
    Tuple,
    cast,
)

import anyio
import lmdb

from kavo._db import (
    delete_chunk,
    delete_request,
    delete_response,
    delete_staleness_tracker,
    delete_stampede,
    encode_staleness_tracker_key,
    get_chunk,
    get_entry,
    get_response,
    get_response_batch,
    get_stampede,
    put_chunk,
    put_entry,
    put_request,
    put_response,
    put_staleness_tracker,
    put_stampede,
)
from kavo.config import Config, get_default_config

from .labels import get_label
from .models import (
    CacheEntry,
    GetCacheEntryOptions,
    PutResponseOptions,
    StampedeInfo,
    compare_stampede_info,
)
from .pack import unpack
from .utils import (
    assert_present,
    async_iterable_to_iterable,
    get_unix_timestamp_seconds,
)

try:
    from anyio import to_thread
except ImportError:
    to_thread = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from .types_ import Database, Environment, Transaction


class KavoClient:
    env: "Environment"
    response_db: "Database"
    entries_db: "Database"
    requests_db: "Database"
    requests_chunk_db: "Database"
    responses_chunk_db: "Database"
    stampede_db: "Database"
    staleness_tracker_db: "Database"

    def __init__(self, config: Config | None = None, env: "Environment" | None = None) -> None:
        default_config = get_default_config()
        self.config = default_config | (config or {})
        self.env = env or lmdb.open(self.config["lmdb_path"], max_dbs=10)
        self.response_db = self.env.open_db(self.config["responses_db"].encode())
        self.entries_db = self.env.open_db(self.config["entries_db"].encode())
        self.requests_db = self.env.open_db(self.config["requests_db"].encode())
        self.requests_chunk_db = self.env.open_db(self.config["requests_chunk_db"].encode())
        self.responses_chunk_db = self.env.open_db(self.config["responses_chunk_db"].encode())
        self.stampede_db = self.env.open_db(self.config["stampede_db"].encode())
        self.staleness_tracker_db = self.env.open_db(self.config["staleness_tracker_db"].encode())

    def get_cache_entry(self, key: str, options: GetCacheEntryOptions) -> CacheEntry | None:
        """
        Retrieves a cache entry with its associated responses from the database.

        This method fetches a cache entry by key and its linked responses, optionally filtering
        incomplete responses based on the provided options.

        Args:
            key (str): The key to lookup the cache entry.
            options (GetCacheEntryOptions): Options for retrieving the cache entry, including
                whether to allow incomplete responses.

        Returns:
            CacheEntry | None: The cache entry with its responses if found, None otherwise.
                The cache entry contains the original entry data with filtered responses based
                on the options provided.

        Example:
            ```python
            options = GetCacheEntryOptions(allow_incomplete=False)
            cache_entry = client.get_cache_entry("my_key", options)
            ```
        """
        with self.env.begin() as txn:
            cache_entry = get_entry(txn, key, self.entries_db)
            if cache_entry is None:
                return None

            responses = list(get_response_batch(txn, cache_entry["responses"], self.response_db).items())

            if not options.get("allow_incomplete"):
                responses = [
                    (response_id, response)
                    for response_id, response in responses
                    if self._is_stream_complete(self.responses_chunk_db, txn, response_id.bytes)
                ]

            cache_entry["responses"] = [response_id for response_id, _ in responses]

            return cache_entry

    def update_response_time_to_stale(self, response_id: uuid.UUID) -> None:
        """
        Updates the expiration time of a response to stale state.
        This method updates the deletion time for a response in the database. If the response
        has 'no_refresh_on_access' set to True and already has a deletion time, it won't be updated.
        The new deletion time is calculated as current timestamp plus the 'stale_after' value.
        Args:
            response_id (uuid.UUID): The unique identifier of the response to update.
        Returns:
            None: This method doesn't return anything.
        Note:
            The method performs several database operations:
            - Updates the expiration time in the response record
            - Removes the old expiration entry if it exists
            - Creates a new expiration entry
            All these operations are performed in a single transaction.
        """

        with self.env.begin(write=True) as txn:
            response = get_response(txn, response_id, self.response_db)

            if response is None:
                return None

            old_staleness_tracker: Optional[bytes] = response.get(get_label("staleness_tracker"), None)

            if old_staleness_tracker is not None and response.get(get_label("no_refresh_on_access")):
                # If the 'no_refresh_on_access' option was set to True, we don't refresh the staleness tracker
                return None

            new_staleness_tracker = encode_staleness_tracker_key(
                get_unix_timestamp_seconds() + response[get_label("stale_after")],
                response_id,
            )

            modified_response = cast(
                Mapping[str, Any],
                {
                    **response,
                    get_label("staleness_tracker"): new_staleness_tracker,
                },
            )

            if old_staleness_tracker is not None:
                delete_staleness_tracker(txn, key=old_staleness_tracker, db=self.staleness_tracker_db)

            put_staleness_tracker(
                txn,
                key=new_staleness_tracker,
                response_id=response_id,
                db=self.staleness_tracker_db,
            )

            put_response(txn, response_id, modified_response, self.response_db)

    def delete_response(self, id: uuid.UUID) -> None:
        """
        Soft deletes a response by marking it as deleted with a timestamp.
        This method performs a soft delete operation on a response entry in the database by
        adding a 'soft_deleted' timestamp while preserving the original record.
        Args:
            id (uuid.UUID): The unique identifier of the response to be soft deleted.
        Returns:
            None: Returns None if the operation is successful or if the response is not found.
        Examples:
            >>> client.delete_response(uuid.UUID('123e4567-e89b-12d3-a456-426614174000'))
        """

        with self.env.begin(write=True) as txn:
            response = get_response(txn, id, self.response_db)

            if response is None:
                return None

            modified_response = {
                **response,
                get_label("soft_deleted"): get_unix_timestamp_seconds(),
            }

            put_response(txn, id, modified_response, self.response_db)

    def put_response(
        self,
        key: str,
        response: Mapping[str, Any],
        request_id: uuid.UUID,
        response_options: PutResponseOptions | None = None,
    ) -> None:
        """
        Stores a response in the cache with associated metadata and request ID.
        This method stores the response in the cache and manages the relationship between
        cache keys and their responses. It handles both creating new cache entries and
        updating existing ones.
        Args:
            key (str): The cache key to associate the response with.
            response (Mapping[str, Any]): The response data to store.
            request_id (uuid.UUID): Unique identifier for this response.
            response_options (PutResponseOptions | None, optional): Options for storing the response.
                Can include 'stale_after' and 'no_refresh_on_access' settings. Defaults to None.
        The method performs several operations:
            1. Stores the response with metadata (stale_after, created_at)
            2. Creates or updates a cache entry linking the key to the response
            3. Performs cleanup of soft-deleted and stale responses
        Note:
            The response is stored with timestamps and configured staleness settings.
            Cache entries maintain a list of associated response IDs.
        """
        response_options = response_options or {}
        with self.env.begin(write=True) as txn:
            response_to_put = {
                **response,
                get_label(
                    "stale_after",
                ): (response_options.get("stale_after", self.config["stale_after"])),
                get_label("created_at"): get_unix_timestamp_seconds(),
            }

            put_response(
                txn,
                request_id,
                response_to_put | {get_label("no_refresh_on_access"): True}
                if response_options.get("no_refresh_on_access")
                else response_to_put,
                self.response_db,
            )

            cache_entry = get_entry(txn, key, self.entries_db)
            if cache_entry is None:
                # Create a new cache entry if it doesn't exist
                cache_entry = CacheEntry(key=key, responses=[])

            # Add the response to the cache entry
            cache_entry["responses"].append(request_id)

            # Store the updated cache entry
            put_entry(txn, key, cache_entry, self.entries_db)

            self._hard_remove_soft_deleted_responses(txn, cache_entry=cache_entry)
            self._soft_remove_stale_responses(txn)

    def put_response_stream(self, request_id: uuid.UUID, stream: Iterable[bytes]) -> None:
        """
        Store a response stream in the cache.
        """

        with self.env.begin(write=True, db=self.responses_chunk_db) as txn:
            return self._stream_data_to_cache(stream, request_id.bytes, txn, self.responses_chunk_db)

    def get_response_stream(self, request_id: uuid.UUID) -> Iterable[bytes]:
        with self.env.begin() as txn:
            for chunk in self._stream_data_from_cache(request_id.bytes, txn, self.responses_chunk_db):
                yield chunk

    def store_request(
        self,
        request: Mapping[str, Any],
        stream: Iterable[bytes],
        request_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        request_id = request_id or uuid.uuid4()
        env = self.env
        with env.begin(write=True) as txn:
            put_request(request_id, txn, request, self.requests_db)

            self._stream_data_to_cache(stream, request_id.bytes, txn, self.requests_chunk_db)

        return request_id

    @contextmanager
    def stampede_lock(self, key: str) -> Iterator[Tuple[bool, StampedeInfo]]:
        """
        Context manager for acquiring and releasing a stampede lock.
        """
        acquired, stampede_info = self._acquire_stamapede_lock(key)

        if not acquired:
            # If we are waiter, then we should wait for the lock to be released
            while self._should_wait(key, stampede_info):
                sleep(0.01)  # Sleep to avoid busy waiting
                pass

        try:
            yield acquired, stampede_info
        finally:
            if acquired:
                self._release_stampede_lock(key, stampede_info)

    def _soft_remove_stale_responses(self, txn: "Transaction") -> None:
        cursor = txn.cursor(db=self.staleness_tracker_db)

        for key, value in cursor:
            raw_timestamp, response_id = key[:8], key[8:]

            timestamp = int.from_bytes(raw_timestamp, "big")

            unpacked_value = unpack(value, "staleness_tracker")

            response = get_response(txn, unpacked_value["response_id"], response_db=self.response_db)

            if response is None:
                delete_staleness_tracker(txn, key=key, db=self.staleness_tracker_db)
                continue

            if timestamp < get_unix_timestamp_seconds():
                # If the response is stale, we delete it
                modified_reponse = {
                    **response,
                    get_label("soft_deleted"): get_unix_timestamp_seconds(),
                }
                put_response(
                    txn,
                    uuid.UUID(bytes=response_id),
                    modified_reponse,
                    self.response_db,
                )
            else:
                break

    def _should_wait(
        self,
        key: str,
        stampede_info: StampedeInfo,
    ) -> bool:
        """
        Check if we should still wait for the lock with the current StampedeInfo.
        """
        with self.env.begin(db=self.stampede_db) as txn:
            current_stampede_info = get_stampede(txn, key, self.stampede_db)
            if current_stampede_info is None:
                return False

            if self._is_lock_stale(current_stampede_info):
                return False

            if not compare_stampede_info(current_stampede_info, stampede_info):
                return False

        return True

    def _release_stampede_lock(self, key: str, stampede_info: StampedeInfo) -> None:
        """
        Release the stampede lock by deleting the entry from the database.
        """

        with self.env.begin(write=True, db=self.stampede_db) as txn:
            unpacked_stampede_info = get_stampede(txn, key, self.stampede_db)

            if unpacked_stampede_info is None:
                return None

            if unpacked_stampede_info["lock_id"] != stampede_info["lock_id"]:
                return

            deleted = delete_stampede(txn, key, self.stampede_db)
            if not deleted:
                raise RuntimeError(
                    f"Failed to release stampede lock for key: {key}. Lock may not exist or was already released."
                )

    def _acquire_stamapede_lock(
        self,
        key: str,
    ) -> Tuple[bool, StampedeInfo]:
        """
        Non-blocking acquire of a stampede lock.

        If the lock is acquired, it returns True and a StampedeInfo object.
        If the lock is not acquired, it returns False and the current StampedeInfo.
        """

        with self.env.begin(write=True, db=self.stampede_db) as txn:
            stampede_info = get_stampede(txn, key, self.stampede_db)

            if stampede_info is not None and self._is_lock_stale(stampede_info):
                # In case of stale lock, we delete the entry and return True
                # giving a chance for current request to acquire the lock
                delete_stampede(txn, key, self.stampede_db)
                stampede_info = None

            if stampede_info is None:
                # If you got a lock, you are responsible for getting the
                # response from remote server and setting it to the response attribute

                stampede_info = StampedeInfo(acquiredAt=get_unix_timestamp_seconds(), lock_id=uuid.uuid4())
                put_stampede(
                    txn,
                    key,
                    {**stampede_info, "lock_id": stampede_info["lock_id"]},
                    self.stampede_db,
                )
                return True, stampede_info
            return False, stampede_info

    def _is_lock_stale(
        self,
        stampede_info: StampedeInfo,
    ) -> bool:
        """
        Check if the lock is stale based on the acquiredAt timestamp.
        """

        return (
            stampede_info is not None
            and stampede_info["acquiredAt"]
            < get_unix_timestamp_seconds("float") - self.config["max_stampede_wait_time"]
        )

    def _hard_remove_soft_deleted_responses(self, txn: "Transaction", cache_entry: CacheEntry) -> None:
        deleted_response_ids = set()

        for response_id in cache_entry["responses"]:
            response = assert_present(get_response(txn, response_id, self.response_db))

            deleted_timestamp = response.get(get_label("soft_deleted"))

            if deleted_timestamp is not None and (
                deleted_timestamp + self.config["hard_delete_after"] < get_unix_timestamp_seconds()
            ):
                deleted_response_ids.add(response_id)

                # we need to remove request/responses and also it's chunkds

                # delete from response db
                delete_response(txn, response_id, self.response_db)

                # delete from request db
                delete_request(txn, response_id, self.response_db)

                # delete from request chunks db
                self._hard_remove_stream(txn, response_id.bytes, self.requests_chunk_db)

                # delete from response chunks db
                self._hard_remove_stream(txn, response_id.bytes, self.responses_chunk_db)

        new_responses = [
            response_id for response_id in cache_entry["responses"] if response_id not in deleted_response_ids
        ]
        modified_cache_entry: CacheEntry = {
            **cache_entry,
            "responses": [response_id for response_id in new_responses],
        }

        put_entry(txn, cache_entry["key"], modified_cache_entry, self.entries_db)

    def _stream_data_to_cache(
        self,
        stream: Iterable[bytes],
        request_id: bytes,
        txn: "Transaction",
        db: Database,
    ) -> None:
        """
        Stream data to the cache in chunks.
        """

        i = 0
        for chunk in stream:
            put_chunk(txn, b":".join([request_id, f"chunk_{i}".encode("utf-8")]), chunk, db)
            i += 1

        # add empty chunk to indicate end of stream
        put_chunk(txn, b":".join([request_id, f"chunk_{i}".encode("utf-8")]), b"", db)

        # add flag to indicate that the request is complete
        put_chunk(txn, b":".join([request_id, b"complete"]), b"", db)

    def _stream_data_from_cache(self, request_id: bytes, txn: "Transaction", db: "Database") -> Iterable[bytes]:
        """
        Stream data from the cache in chunks.
        """
        i = 0
        while True:
            chunk = get_chunk(txn, b":".join([request_id, f"chunk_{i}".encode("utf-8")]), db=db)
            if chunk is None:
                break
            if chunk == b"":
                break
            yield chunk
            i += 1

    def _hard_remove_stream(self, txn: Transaction, request_id: bytes, db: "Database") -> None:
        """
        Hard remove a stream from the cache.
        Note that we should remove it also when it's not complete
        """
        i = 0
        while True:
            chunk_key = b":".join([request_id, f"chunk_{i}".encode("utf-8")])
            deleted = delete_chunk(txn, chunk_key, db)
            if not deleted:
                break
            i += 1

        # remove the complete flag
        delete_chunk(txn, b":".join([request_id, b"complete"]), db=db)

    def _is_stream_complete(self, chunks_db: "Database", txn: Transaction, request_id: bytes) -> bool:
        """
        Check if the stream is complete.
        """
        return get_chunk(txn, b":".join([request_id, b"complete"]), db=chunks_db) is not None


class AsyncKavoClient:
    def __init__(self, config: Config | None = None, env: "Environment" | None = None) -> None:
        default_config = get_default_config()
        self.config = default_config | (config or {})
        self.env = env or lmdb.open(self.config["lmdb_path"], max_dbs=10)
        self.response_db = self.env.open_db(self.config["responses_db"].encode())
        self.entries_db = self.env.open_db(self.config["entries_db"].encode())
        self.requests_db = self.env.open_db(self.config["requests_db"].encode())
        self.requests_chunk_db = self.env.open_db(self.config["requests_chunk_db"].encode())
        self.responses_chunk_db = self.env.open_db(self.config["responses_chunk_db"].encode())
        self.stampede_db = self.env.open_db(self.config["stampede_db"].encode())
        self.staleness_tracker_db = self.env.open_db(self.config["staleness_tracker_db"].encode())
        self._sync_client = KavoClient(config=self.config, env=self.env)
        if to_thread is None:
            raise ImportError("AsyncKavoClient requires 'anyio' to be installed.")

    async def get_cache_entry(self, key: str, options: GetCacheEntryOptions) -> CacheEntry | None:
        return await to_thread.run_sync(self._sync_client.get_cache_entry, key, options)

    async def delete_response(self, id: uuid.UUID) -> None:
        return await to_thread.run_sync(self._sync_client.delete_response, id)

    async def put_response(
        self,
        key: str,
        response: Mapping[str, Any],
        request_id: uuid.UUID,
        response_options: PutResponseOptions | None = None,
    ) -> None:
        return await to_thread.run_sync(self._sync_client.put_response, key, response, request_id, response_options)

    async def put_response_stream(self, request_id: uuid.UUID, stream: AsyncIterable[bytes]) -> None:
        """
        Store a response stream in the cache.
        """
        return await to_thread.run_sync(
            self._sync_client.put_response_stream,
            request_id,
            async_iterable_to_iterable(stream),
        )

    async def get_response_stream(self, request_id: uuid.UUID) -> AsyncIterable[bytes]:
        txn = await to_thread.run_sync(
            self._sync_client.env.begin,
        )
        try:
            async for chunk in self._stream_data_from_cache(
                request_id.bytes,
                txn,  # type: ignore
                self._sync_client.responses_chunk_db,
            ):
                yield chunk
        finally:
            txn.__exit__(None, None, None)

    async def update_response_time_to_stale(self, response_id: uuid.UUID) -> None:
        return await to_thread.run_sync(self._sync_client.update_response_time_to_stale, response_id)

    async def _stream_data_from_cache(
        self, request_id: bytes, txn: "Transaction", db: "Database"
    ) -> AsyncIterable[bytes]:
        """
        Stream data from the cache in chunks.
        """
        i = 0
        while True:
            chunk = await to_thread.run_sync(
                get_chunk,
                txn,
                b":".join([request_id, f"chunk_{i}".encode("utf-8")]),
                db,
            )
            if chunk is None:
                break
            if chunk == b"":
                break
            yield chunk
            i += 1

    async def store_request(
        self,
        request: Mapping[str, Any],
        stream: AsyncIterable[bytes],
        request_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        return await to_thread.run_sync(
            self._sync_client.store_request,
            request,
            async_iterable_to_iterable(stream),
            request_id,
        )

    @asynccontextmanager
    async def async_stampede_lock(
        self,
        key: str,
    ) -> AsyncIterator[Tuple[bool, StampedeInfo]]:
        """
        Async context manager for acquiring and releasing a stampede lock.
        """
        acquired, stampede_info = await to_thread.run_sync(self._sync_client._acquire_stamapede_lock, key)

        if not acquired:
            # If we are waiter, then we should wait for the lock to be released
            while await to_thread.run_sync(self._sync_client._should_wait, key, stampede_info):
                await anyio.sleep(0.01)

        try:
            yield acquired, stampede_info
        finally:
            if acquired:
                await to_thread.run_sync(self._sync_client._release_stampede_lock, key, stampede_info)
