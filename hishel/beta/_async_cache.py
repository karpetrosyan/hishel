from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import replace
from typing import AsyncIterator, Awaitable, Callable

from typing_extensions import assert_never

from hishel.beta import (
    AnyState,
    AsyncBaseStorage,
    AsyncSqliteStorage,
    CacheMiss,
    CacheOptions,
    CouldNotBeStored,
    FromCache,
    IdleClient,
    NeedRevalidation,
    NeedToBeUpdated,
    Request,
    Response,
    StoreAndUse,
    create_idle_state,
)
from hishel.beta._core._spec import InvalidatePairs, vary_headers_match
from hishel.beta._core.models import CompletePair

logger = logging.getLogger("hishel.integrations.clients")


class AsyncCacheProxy:
    """
    A proxy for HTTP caching in clients.

    This class is independent of any specific HTTP library and works only with internal models.
    It delegates request execution to a user-provided callable, making it compatible with any
    HTTP client. Caching behavior can be configured to either fully respect HTTP
    caching rules or bypass them entirely.
    """

    def __init__(
        self,
        send_request: Callable[[Request], Awaitable[Response]],
        storage: AsyncBaseStorage | None = None,
        cache_options: CacheOptions | None = None,
        ignore_specification: bool = False,
    ) -> None:
        self.send_request = send_request
        self.storage = storage if storage is not None else AsyncSqliteStorage()
        self.cache_options = cache_options if cache_options is not None else CacheOptions()
        self.ignore_specification = ignore_specification

    async def handle_request(self, request: Request) -> Response:
        if self.ignore_specification or request.metadata.get("hishel_spec_ignore"):
            return await self._handle_request_ignoring_spec(request)
        return await self._handle_request_respecting_spec(request)

    async def _get_key_for_request(self, request: Request) -> str:
        if request.metadata.get("hishel_body_key"):
            assert isinstance(request.stream, AsyncIterator)
            collected = b"".join([chunk async for chunk in request.stream])
            hash_ = hashlib.sha256(collected).hexdigest()
            return f"{str(request.url)}-{hash_}"
        return str(request.url)

    async def _maybe_refresh_pair_ttl(self, pair: CompletePair) -> None:
        if pair.request.metadata.get("hishel_refresh_ttl_on_access"):
            await self.storage.update_pair(
                pair.id,
                lambda complete_pair: replace(complete_pair, meta=replace(complete_pair.meta, created_at=time.time())),
            )

    async def _handle_request_ignoring_spec(self, request: Request) -> Response:
        logger.debug("Trying to get cached response ignoring specification")
        pairs = await self.storage.get_pairs(await self._get_key_for_request(request))

        logger.debug(f"Found {len(pairs)} cached pairs for the request")

        for pair in pairs:
            if (
                str(pair.request.url) == str(request.url)
                and pair.request.method == request.method
                and vary_headers_match(
                    request,
                    pair,
                )
            ):
                logger.debug(
                    "Found matching cached response for the request",
                )
                pair.response.metadata["hishel_from_cache"] = True  # type: ignore
                await self._maybe_refresh_pair_ttl(pair)
                return pair.response

        incomplete_pair = await self.storage.create_pair(
            request,
        )
        response = await self.send_request(incomplete_pair.request)

        logger.debug("Storing response in cache ignoring specification")
        complete_pair = await self.storage.add_response(
            incomplete_pair.id, response, await self._get_key_for_request(request)
        )
        return complete_pair.response

    async def _handle_request_respecting_spec(self, request: Request) -> Response:
        state: AnyState = create_idle_state("client", self.cache_options)

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
                await self._maybe_refresh_pair_ttl(state.pair)
                return state.pair.response
            elif isinstance(state, NeedToBeUpdated):
                state = await self._handle_update(state)
            elif isinstance(state, InvalidatePairs):
                state = await self._handle_invalidate_pairs(state)
            else:
                assert_never(state)

        raise RuntimeError("Unreachable")

    async def _handle_idle_state(self, state: IdleClient, request: Request) -> AnyState:
        stored_pairs = await self.storage.get_pairs(await self._get_key_for_request(request))
        return state.next(request, stored_pairs)

    async def _handle_cache_miss(self, state: CacheMiss) -> AnyState:
        incomplete_pair = await self.storage.create_pair(state.request)
        response = await self.send_request(incomplete_pair.request)
        return state.next(response, incomplete_pair.id)

    async def _handle_store_and_use(self, state: StoreAndUse, request: Request) -> Response:
        complete_pair = await self.storage.add_response(
            state.pair_id, state.response, await self._get_key_for_request(request)
        )
        return complete_pair.response

    async def _handle_revalidation(self, state: NeedRevalidation) -> AnyState:
        revalidation_response = await self.send_request(state.request)
        return state.next(revalidation_response)

    async def _handle_update(self, state: NeedToBeUpdated) -> AnyState:
        for pair in state.updating_pairs:
            await self.storage.update_pair(
                pair.id,
                lambda complete_pair: replace(
                    complete_pair, response=replace(pair.response, headers=pair.response.headers)
                ),
            )
        return state.next()

    async def _handle_invalidate_pairs(self, state: InvalidatePairs) -> AnyState:
        for pair_id in state.pair_ids:
            await self.storage.remove(pair_id)
        return state.next()
