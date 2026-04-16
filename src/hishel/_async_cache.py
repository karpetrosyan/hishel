from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import replace
from typing import AsyncIterable, AsyncIterator, Awaitable, Callable

from typing_extensions import assert_never

from hishel import (
    AnyState,
    AsyncBaseStorage,
    AsyncSqliteStorage,
    CacheMiss,
    CouldNotBeStored,
    FromCache,
    IdleClient,
    NeedRevalidation,
    NeedToBeUpdated,
    Request,
    Response,
    StoreAndUse,
)
from hishel._core._spec import InvalidateEntries, vary_headers_match
from hishel._core.models import Entry, ResponseMetadata
from hishel._policies import CachePolicy, FilterPolicy, SpecificationPolicy
from hishel._utils import make_async_iterator

logger = logging.getLogger("hishel.integrations.clients")


class AsyncCacheProxy:
    """
    A proxy for HTTP caching in clients.

    This class is independent of any specific HTTP library and works only with internal models.
    It delegates request execution to a user-provided callable, making it compatible with any
    HTTP client. Caching behavior is determined by the policy object.

    Args:
        request_sender: Callable that sends HTTP requests and returns responses.
        storage: Storage backend for cache entries. Defaults to AsyncSqliteStorage.
        policy: Caching policy to use. Can be SpecificationPolicy (respects RFC 9111) or
            FilterPolicy (user-defined filtering). Defaults to SpecificationPolicy().
    """

    def __init__(
        self,
        request_sender: Callable[[Request], Awaitable[Response]],
        storage: AsyncBaseStorage | None = None,
        policy: CachePolicy | None = None,
    ) -> None:
        self.send_request = request_sender
        self.storage = storage if storage is not None else AsyncSqliteStorage()
        self.policy = policy if policy is not None else SpecificationPolicy()

    async def handle_request(self, request: Request) -> Response:
        if isinstance(self.policy, FilterPolicy):
            return await self._handle_request_with_filters(request)
        return await self._handle_request_respecting_spec(request)

    async def _get_key_for_request(self, request: Request) -> str:
        if self.policy.use_body_key or request.metadata.get("hishel_body_key"):
            assert isinstance(request.stream, (AsyncIterator, AsyncIterable))
            collected = b"".join([chunk async for chunk in request.stream])
            hash_ = hashlib.sha256(collected).hexdigest()
            request.stream = make_async_iterator([collected])
            return hash_
        return hashlib.sha256(str(request.url).encode("utf-8")).hexdigest()

    async def _maybe_refresh_entry_ttl(self, entry: Entry) -> None:
        if entry.request.metadata.get("hishel_refresh_ttl_on_access"):
            await self.storage.update_entry(
                entry.id,
                lambda current_entry: replace(
                    current_entry,
                    meta=replace(current_entry.meta, created_at=time.time()),
                ),
            )

    async def _handle_request_with_filters(self, request: Request) -> Response:
        assert isinstance(self.policy, FilterPolicy)

        for request_filter in self.policy.request_filters:
            if request_filter.needs_body():
                body = await request.aread()
                if not request_filter.apply(request, body):
                    logger.debug("Request filtered out by request filter")
                    return await self.send_request(request)
            else:
                if not request_filter.apply(request, None):
                    logger.debug("Request filtered out by request filter")
                    return await self.send_request(request)

        logger.debug("Trying to get cached response ignoring specification")
        cache_key = await self._get_key_for_request(request)
        entries = await self.storage.get_entries(cache_key)

        logger.debug(f"Found {len(entries)} cached entries for the request")

        for entry in entries:
            if (
                str(entry.request.url) == str(request.url)
                and entry.request.method == request.method
                and vary_headers_match(
                    request,
                    entry,
                )
            ):
                logger.debug(
                    "Found matching cached response for the request",
                )
                response_meta = ResponseMetadata(
                    hishel_from_cache=True,
                    hishel_created_at=entry.meta.created_at,
                    hishel_revalidated=False,
                    hishel_stored=False,
                )
                entry.response.metadata.update(response_meta)  # type: ignore
                await self._maybe_refresh_entry_ttl(entry)
                return entry.response

        response = await self.send_request(request)
        for response_filter in self.policy.response_filters:
            if response_filter.needs_body():
                body = await response.aread()
                if not response_filter.apply(response, body):
                    logger.debug("Response filtered out by response filter")
                    return response
            else:
                if not response_filter.apply(response, None):
                    logger.debug("Response filtered out by response filter")
                    return response
        response_meta = ResponseMetadata(
            hishel_from_cache=False,
            hishel_created_at=time.time(),
            hishel_revalidated=False,
            hishel_stored=True,
        )
        response.metadata.update(response_meta)  # type: ignore

        logger.debug("Storing response in cache ignoring specification")
        entry = await self.storage.create_entry(
            request,
            response,
            cache_key,
        )
        return entry.response

    async def _handle_request_respecting_spec(self, request: Request) -> Response:
        assert isinstance(self.policy, SpecificationPolicy)
        state: AnyState = IdleClient(options=self.policy.cache_options)

        while state:
            logger.debug(f"Handling state: {state.__class__.__name__}")
            if isinstance(state, IdleClient):
                state = await self._handle_idle_state(state, request)
            elif isinstance(state, CacheMiss):
                state = await self._handle_cache_miss(state)
            elif isinstance(state, StoreAndUse):
                return await self._handle_store_and_use(state, request)
            elif isinstance(state, CouldNotBeStored):
                return state.response
            elif isinstance(state, NeedRevalidation):
                state = await self._handle_revalidation(state)
            elif isinstance(state, FromCache):
                await self._maybe_refresh_entry_ttl(state.entry)
                return state.entry.response
            elif isinstance(state, NeedToBeUpdated):
                state = await self._handle_update(state)
            elif isinstance(state, InvalidateEntries):
                state = await self._handle_invalidate_entries(state)
            else:
                assert_never(state)

        raise RuntimeError("Unreachable")

    async def _handle_idle_state(self, state: IdleClient, request: Request) -> AnyState:
        stored_entries = await self.storage.get_entries(await self._get_key_for_request(request))
        return state.next(request, stored_entries)

    async def _handle_cache_miss(self, state: CacheMiss) -> AnyState:
        response = await self.send_request(state.request)
        return state.next(response)

    async def _handle_store_and_use(self, state: StoreAndUse, request: Request) -> Response:
        entry = await self.storage.create_entry(
            request,
            state.response,
            await self._get_key_for_request(request),
        )
        return entry.response

    async def _handle_revalidation(self, state: NeedRevalidation) -> AnyState:
        revalidation_response = await self.send_request(state.request)
        return state.next(revalidation_response)

    async def _handle_update(self, state: NeedToBeUpdated) -> AnyState:
        for updating_entry in state.updating_entries:
            await self.storage.update_entry(
                updating_entry.id,
                lambda existing_entry: replace(
                    existing_entry,
                    response=replace(existing_entry.response, headers=updating_entry.response.headers),
                ),
            )
        return state.next()

    async def _handle_invalidate_entries(self, state: InvalidateEntries) -> AnyState:
        for entry_id in state.entry_ids:
            await self.storage.remove_entry(entry_id)
        return state.next()
