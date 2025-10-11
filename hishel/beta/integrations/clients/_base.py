from __future__ import annotations

import logging
import time
import uuid
from dataclasses import replace
from typing import Awaitable, Callable, Optional

from typing_extensions import assert_never

from hishel._utils import GeneratorWithReturnValue
from hishel.beta import (
    AnyState,
    AsyncBaseStorage,
    CacheMiss,
    CacheOptions,
    CouldNotBeStored,
    FromCache,
    IdleClient,
    KeyGen,
    NeedRevalidation,
    NeedToBeUpdated,
    Request,
    Response,
    StoreAndUse,
    SyncBaseStorage,
    create_idle_state,
)
from hishel.beta._core._async._storages._sqlite import AsyncSqliteStorage
from hishel.beta._core._spec import vary_headers_match
from hishel.beta._core._sync._storages._sqlite import SyncSqliteStorage
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

    def _get_key_for_pair(self, request: Request, keygen: Optional[GeneratorWithReturnValue] = None) -> bytes:
        if keygen is not None:
            assert keygen.value is not None
            return keygen.value
        if self.cache_options.keygen is None:
            return str(request.url).encode("utf-8")
        elif callable(self.cache_options.keygen):
            key = self.cache_options.keygen(request)
            if isinstance(key, str):
                return key.encode("utf-8")
            return key
        elif isinstance(self.cache_options.keygen, KeyGen):
            raise ValueError("KeyGen generator should be provided")
        else:
            assert_never(self.cache_options.keygen)

    async def _maybe_refresh_pair_ttl(self, pair: CompletePair) -> None:
        if pair.request.metadata.get("hishel_refresh_ttl_on_access"):
            await self.storage.update_pair(
                pair.id,
                lambda complete_pair: replace(complete_pair, meta=replace(complete_pair.meta, created_at=time.time())),
            )

    async def _handle_request_ignoring_spec(self, request: Request) -> Response:
        logger.debug("Trying to get cached response ignoring specification")
        pairs = await self.storage.get_pairs(str(request.url))

        logger.debug(f"Found {len(pairs)} cached pairs for the request %s")

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
                await self._maybe_refresh_pair_ttl(pair)
                return pair.response

        key: str | bytes | None = None
        keygen_generator: GeneratorWithReturnValue | None = None
        if self.cache_options.keygen is None:
            logger.debug("No keygen provided, using URL as key")
            key = str(request.url)
        elif callable(self.cache_options.keygen):
            logger.debug("Using callable keygen to generate key")
            key = self.cache_options.keygen(request)
        elif isinstance(self.cache_options.keygen, KeyGen):
            logger.debug("Using streaming keygen to generate key")
            keygen_generator = GeneratorWithReturnValue(self.cache_options.keygen.decoder(), request.stream)
            request = replace(request, stream=keygen_generator)
        else:
            assert_never(self.cache_options.keygen)

        incomplete_pair = await self.storage.create_pair(
            request,
        )
        response = await self.send_request(incomplete_pair.request)

        key = self._get_key_for_pair(request, keygen=keygen_generator)

        logger.debug("Storing response in cache ignoring specification")
        complete_pair = await self.storage.add_response(
            incomplete_pair.id,
            response,
            key,
        )
        return complete_pair.response

    async def _handle_request_respecting_spec(self, request: Request) -> Response:
        state: AnyState = create_idle_state("client", self.cache_options)
        pair_to_keygen: dict[uuid.UUID, GeneratorWithReturnValue] = {}

        while state:
            logger.debug(f"Handling state: {state.__class__.__name__}")
            if isinstance(state, IdleClient):
                state = await self._handle_idle_state(state, request, pair_to_keygen)
            elif isinstance(state, CacheMiss):
                state = await self._handle_cache_miss(state)
            elif isinstance(state, StoreAndUse):
                return await self._handle_store_and_use(state, request, pair_to_keygen)
            elif isinstance(state, CouldNotBeStored):
                return state.response
            elif isinstance(state, NeedRevalidation):
                state = await self._handle_revalidation(state, request, pair_to_keygen)
            elif isinstance(state, FromCache):
                await self._maybe_refresh_pair_ttl(state.pair)
                return state.pair.response
            elif isinstance(state, NeedToBeUpdated):
                state = await self._handle_update(state)
            else:
                assert_never(state)

        raise RuntimeError("Unreachable")

    async def _handle_idle_state(
        self, state: IdleClient, request: Request, pair_to_keygen: dict[uuid.UUID, GeneratorWithReturnValue]
    ) -> AnyState:
        new_pair = await self.storage.create_pair(request)

        if isinstance(self.cache_options.keygen, KeyGen):
            keygen_generator = GeneratorWithReturnValue(self.cache_options.keygen.decoder(), new_pair.request.stream)
            request = replace(new_pair.request, stream=keygen_generator)
            pair_to_keygen[new_pair.id] = keygen_generator

        stored_pairs = await self.storage.get_pairs(str(new_pair.request.url))
        return state.next(new_pair, stored_pairs)

    async def _handle_cache_miss(self, state: CacheMiss) -> AnyState:
        response = await self.send_request(state.request)
        return state.next(response)

    async def _handle_store_and_use(
        self, state: StoreAndUse, request: Request, pair_to_keygen: dict[uuid.UUID, GeneratorWithReturnValue]
    ) -> Response:
        key = self._get_key_for_pair(request, keygen=pair_to_keygen.get(state.pair_id))
        complete_pair = await self.storage.add_response(state.pair_id, state.response, key)
        return complete_pair.response

    async def _handle_revalidation(
        self, state: NeedRevalidation, request: Request, pair_to_keygen: dict[uuid.UUID, GeneratorWithReturnValue]
    ) -> AnyState:
        revalidation_response = await self.send_request(state.request)
        key = self._get_key_for_pair(request, keygen=pair_to_keygen.get(state.pair_id))
        revalidation_complete_pair = await self.storage.add_response(state.pair_id, revalidation_response, key)
        return state.next(revalidation_complete_pair)

    async def _handle_update(self, state: NeedToBeUpdated) -> AnyState:
        for pair in state.updating_pairs:
            await self.storage.update_pair(
                pair.id,
                lambda complete_pair: replace(
                    complete_pair, response=replace(pair.response, headers=pair.response.headers)
                ),
            )
        return state.next()


class SyncCacheProxy:
    """
    A proxy for HTTP caching in clients.

    This class is independent of any specific HTTP library and works only with internal models.
    It delegates request execution to a user-provided callable, making it compatible with any
    HTTP client. Caching behavior can be configured to either fully respect HTTP
    caching rules or bypass them entirely.
    """

    def __init__(
        self,
        send_request: Callable[[Request], Response],
        storage: SyncBaseStorage | None = None,
        cache_options: CacheOptions | None = None,
        ignore_specification: bool = False,
    ) -> None:
        self.send_request = send_request
        self.storage = storage if storage is not None else SyncSqliteStorage()
        self.cache_options = cache_options if cache_options is not None else CacheOptions()
        self.ignore_specification = ignore_specification

    def handle_request(self, request: Request) -> Response:
        if self.ignore_specification or request.metadata.get("hishel_spec_ignore"):
            return self._handle_request_ignoring_spec(request)
        return self._handle_request_respecting_spec(request)

    def _get_key_for_pair(self, request: Request, keygen: Optional[GeneratorWithReturnValue] = None) -> bytes:
        if keygen is not None:
            assert keygen.value is not None
            return keygen.value
        if self.cache_options.keygen is None:
            return str(request.url).encode("utf-8")
        elif callable(self.cache_options.keygen):
            key = self.cache_options.keygen(request)
            if isinstance(key, str):
                return key.encode("utf-8")
            return key
        elif isinstance(self.cache_options.keygen, KeyGen):
            raise ValueError("KeyGen generator should be provided")
        else:
            assert_never(self.cache_options.keygen)

    def _maybe_refresh_pair_ttl(self, pair: CompletePair) -> None:
        if pair.request.metadata.get("hishel_refresh_ttl_on_access"):
            self.storage.update_pair(
                pair.id,
                lambda complete_pair: replace(complete_pair, meta=replace(complete_pair.meta, created_at=time.time())),
            )

    def _handle_request_ignoring_spec(self, request: Request) -> Response:
        logger.debug("Trying to get cached response ignoring specification")
        pairs = self.storage.get_pairs(str(request.url))

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
                self._maybe_refresh_pair_ttl(pair)
                return pair.response

        key: str | bytes | None = None
        keygen_generator: GeneratorWithReturnValue | None = None
        if self.cache_options.keygen is None:
            logger.debug("No keygen provided, using URL as key")
            key = str(request.url)
        elif callable(self.cache_options.keygen):
            logger.debug("Using callable keygen to generate key")
            key = self.cache_options.keygen(request)
        elif isinstance(self.cache_options.keygen, KeyGen):
            logger.debug("Using streaming keygen to generate key")
            keygen_generator = GeneratorWithReturnValue(self.cache_options.keygen.decoder(), request.stream)
            request = replace(request, stream=keygen_generator)
        else:
            assert_never(self.cache_options.keygen)

        incomplete_pair = self.storage.create_pair(
            request,
        )
        response = self.send_request(incomplete_pair.request)

        key = self._get_key_for_pair(request, keygen=keygen_generator)

        logger.debug("Storing response in cache ignoring specification")
        complete_pair = self.storage.add_response(
            incomplete_pair.id,
            response,
            key,
        )
        return complete_pair.response

    def _handle_request_respecting_spec(self, request: Request) -> Response:
        state: AnyState = create_idle_state("client", self.cache_options)
        pair_to_keygen: dict[uuid.UUID, GeneratorWithReturnValue] = {}

        while state:
            logger.debug(f"Handling state: {state.__class__.__name__}")
            if isinstance(state, IdleClient):
                state = self._handle_idle_state(state, request, pair_to_keygen)
            elif isinstance(state, CacheMiss):
                state = self._handle_cache_miss(state)
            elif isinstance(state, StoreAndUse):
                return self._handle_store_and_use(state, request, pair_to_keygen)
            elif isinstance(state, CouldNotBeStored):
                return state.response
            elif isinstance(state, NeedRevalidation):
                state = self._handle_revalidation(state, request, pair_to_keygen)
            elif isinstance(state, FromCache):
                self._maybe_refresh_pair_ttl(state.pair)
                return state.pair.response
            elif isinstance(state, NeedToBeUpdated):
                state = self._handle_update(state)
            else:
                assert_never(state)

        raise RuntimeError("Unreachable")

    def _handle_idle_state(
        self, state: IdleClient, request: Request, pair_to_keygen: dict[uuid.UUID, GeneratorWithReturnValue]
    ) -> AnyState:
        new_pair = self.storage.create_pair(request)

        if isinstance(self.cache_options.keygen, KeyGen):
            keygen_generator = GeneratorWithReturnValue(self.cache_options.keygen.decoder(), new_pair.request.stream)
            request = replace(new_pair.request, stream=keygen_generator)
            pair_to_keygen[new_pair.id] = keygen_generator

        stored_pairs = self.storage.get_pairs(str(new_pair.request.url))
        return state.next(new_pair, stored_pairs)

    def _handle_cache_miss(self, state: CacheMiss) -> AnyState:
        response = self.send_request(state.request)
        return state.next(response)

    def _handle_store_and_use(
        self, state: StoreAndUse, request: Request, pair_to_keygen: dict[uuid.UUID, GeneratorWithReturnValue]
    ) -> Response:
        key = self._get_key_for_pair(request, keygen=pair_to_keygen.get(state.pair_id))
        complete_pair = self.storage.add_response(state.pair_id, state.response, key)
        return complete_pair.response

    def _handle_revalidation(
        self, state: NeedRevalidation, request: Request, pair_to_keygen: dict[uuid.UUID, GeneratorWithReturnValue]
    ) -> AnyState:
        revalidation_response = self.send_request(state.request)
        key = self._get_key_for_pair(request, keygen=pair_to_keygen.get(state.pair_id))
        revalidation_complete_pair = self.storage.add_response(state.pair_id, revalidation_response, key)
        return state.next(revalidation_complete_pair)

    def _handle_update(self, state: NeedToBeUpdated) -> AnyState:
        for pair in state.updating_pairs:
            self.storage.update_pair(
                pair.id,
                lambda complete_pair: replace(
                    complete_pair, response=replace(pair.response, headers=pair.response.headers)
                ),
            )
        return state.next()
