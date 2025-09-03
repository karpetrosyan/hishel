from __future__ import annotations

import uuid
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING, AsyncIterator, Callable, Iterator, Optional, TypeVar, cast

from anyio import to_thread

from hishel._core._base._storages._base import AsyncBaseStorage
from hishel._core._sync._storages._lmdb import SyncLmdbStorage
from hishel._core.models import CompletePair, IncompletePair, Request, Response
from hishel._utils import async_iterator_to_sync, sync_iterator_to_async

if TYPE_CHECKING:
    from ...._lmdb_types_ import Environment

import lmdb

T = TypeVar("T", CompletePair, IncompletePair)


def ensure_async(pair: T) -> T:
    """
    Convert synchronous iterators in request/response streams to asynchronous iterators.

    This function takes a pair object (request/response pair) and ensures that any
    synchronous iterator streams are converted to asynchronous iterators. It handles
    both request streams and response streams in CompletePair objects.

    Args:
        pair (T): A request/response pair object that may contain synchronous iterator streams.
            T is a generic type that represents either a Pair or CompletePair object.

    Returns:
        T: A new pair object with any synchronous streams converted to asynchronous iterators.
            The original pair is not modified; instead, a new copy is returned.

    Example:
        >>> pair = IncompletePair(request=Request(stream=iter([b"data"])))
        >>> async_pair = ensure_async(pair)
        >>> isinstance(async_pair.request.stream, AsyncIterator)
        True
    """
    if isinstance(pair.request.stream, Iterator):
        async_pair = replace(pair, request=replace(pair.request, stream=sync_iterator_to_async(pair.request.stream)))

    if isinstance(pair, CompletePair) and isinstance(pair.response.stream, Iterator):
        async_pair = replace(pair, response=replace(pair.response, stream=sync_iterator_to_async(pair.response.stream)))  # type: ignore
    return async_pair


class AsyncLmdbStorage(AsyncBaseStorage):
    def __init__(
        self,
        *,
        env: Optional["Environment"] = None,
        entry_db_name: str = "hishel_entries",
        stream_db_name: str = "hishel_streams",
        entry_db_key_index_db_name: str = "hishel_entry_key_index",
        default_ttl: Optional[float] = None,
        refresh_ttl_on_access: bool = True,
    ) -> None:
        self.env = env if env is not None else cast("Environment", lmdb.open("hishel_cache", max_dbs=100))

        self.entry_db = self.env.open_db(entry_db_name.encode("utf-8"))
        self.stream_db = self.env.open_db(stream_db_name.encode("utf-8"))
        self.entry_key_index_db = self.env.open_db(
            entry_db_key_index_db_name.encode("utf-8"),
            dupsort=True,
        )
        self.default_ttl = default_ttl
        self.refresh_ttl_on_access = refresh_ttl_on_access
        self.last_cleanup = float("-inf")
        self._sync_lmdb_storage = SyncLmdbStorage(
            env=self.env,
            entry_db_name=entry_db_name,
            stream_db_name=stream_db_name,
            entry_db_key_index_db_name=entry_db_key_index_db_name,
            default_ttl=default_ttl,
            refresh_ttl_on_access=refresh_ttl_on_access,
        )

    async def create_pair(
        self,
        key: str,
        request: Request,
        /,
        ttl: Optional[float] = None,
        refresh_ttl_on_access: Optional[bool] = None,
    ) -> IncompletePair:
        """
        Store a request in the backend under the given key.

        Args:
            key: Unique identifier for grouping or looking up stored requests.
            request: The request object to store.
            ttl: Optional time-to-live (in seconds). If set, the entry expires after
                the given duration.
            refresh_ttl_on_access: If True, accessing this entry refreshes its TTL.
                If False, the TTL is fixed. If None, uses the backend's default behavior.

        Returns:
            The created IncompletePair object representing the stored request.

        Raises:
            NotImplementedError: Must be implemented in subclasses.
        """
        assert isinstance(request.stream, AsyncIterator), "Response stream must be an AsyncIterator"

        return ensure_async(
            await to_thread.run_sync(
                partial(
                    self._sync_lmdb_storage.create_pair,
                    key,
                    replace(request, stream=async_iterator_to_sync(request.stream)),
                    ttl=ttl,
                    refresh_ttl_on_access=refresh_ttl_on_access,
                )
            )
        )

    async def add_response(self, pair_id: uuid.UUID, response: Response) -> CompletePair:
        """
        Add a response to an existing request pair.

        Args:
            pair_id: The unique identifier of the request pair.
            response: The response object to add.

        Returns:
            The updated response object.

        Raises:
            NotImplementedError: Must be implemented in subclasses.
        """
        assert isinstance(response.stream, AsyncIterator), "Response stream must be an AsyncIterator"

        return ensure_async(
            await to_thread.run_sync(
                self._sync_lmdb_storage.add_response,
                pair_id,
                replace(response, stream=async_iterator_to_sync(response.stream)),
            )
        )

    async def get_pairs(self, key: str) -> list[CompletePair]:
        """
        Retrieve all responses associated with a given key.

        Args:
            key: The unique identifier for the request pairs.
            complete_only: If True, only return pairs with responses. If False,
                only return pairs without responses. If None, return all pairs.
        """
        return [ensure_async(pair) for pair in await to_thread.run_sync(self._sync_lmdb_storage.get_pairs, key)]

    async def update_pair(
        self,
        id: uuid.UUID,
        new_pair: CompletePair | Callable[[CompletePair], CompletePair],
    ) -> CompletePair | None:
        """
        Update an existing request pair.

        Args:
            id: The unique identifier of the request pair to update.
            new_pair: The new pair data or a callable that takes the current pair
                and returns the updated pair.
        """
        updated_pair = await to_thread.run_sync(self._sync_lmdb_storage.update_pair, id, new_pair)
        if updated_pair is not None:
            return ensure_async(updated_pair)
        return None

    async def remove(self, id: uuid.UUID) -> None:
        """
        Remove a request pair from the storage.

        Args:
            id: The unique identifier of the request pair to remove.
        """
        await to_thread.run_sync(self._sync_lmdb_storage.remove, id)
