from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import replace
from typing import Iterator, Awaitable, Callable

from typing_extensions import assert_never

from hishel import (
    AnyState,
    SyncBaseStorage,
    SyncSqliteStorage,
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
from hishel._core._spec import InvalidatePairs, vary_headers_match
from hishel._core.models import CompletePair, ResponseMetadata

logger = logging.getLogger("hishel.integrations.clients")


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

    def _get_key_for_request(self, request: Request) -> str:
        if request.metadata.get("hishel_body_key"):
            assert isinstance(request.stream, Iterator)
            collected = b"".join([chunk for chunk in request.stream])
            hash_ = hashlib.sha256(collected).hexdigest()
            return f"{str(request.url)}-{hash_}"
        return str(request.url)

    def _maybe_refresh_pair_ttl(self, pair: CompletePair) -> None:
        if pair.request.metadata.get("hishel_refresh_ttl_on_access"):
            self.storage.update_pair(
                pair.id,
                lambda complete_pair: replace(
                    complete_pair,
                    meta=replace(complete_pair.meta, created_at=time.time()),
                ),
            )

    def _handle_request_ignoring_spec(self, request: Request) -> Response:
        logger.debug("Trying to get cached response ignoring specification")
        pairs = self.storage.get_pairs(self._get_key_for_request(request))

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
                response_meta = ResponseMetadata(
                    hishel_spec_ignored=True,
                    hishel_from_cache=True,
                    hishel_created_at=pair.meta.created_at,
                    hishel_revalidated=False,
                    hishel_stored=False,
                )
                pair.response.metadata.update(response_meta)  # type: ignore
                self._maybe_refresh_pair_ttl(pair)
                return pair.response

        incomplete_pair = self.storage.create_pair(
            request,
        )
        response = self.send_request(incomplete_pair.request)

        logger.debug("Storing response in cache ignoring specification")
        complete_pair = self.storage.add_response(
            incomplete_pair.id,
            response,
            self._get_key_for_request(request),
        )
        return complete_pair.response

    def _handle_request_respecting_spec(self, request: Request) -> Response:
        state: AnyState = create_idle_state("client", self.cache_options)

        while state:
            logger.debug(f"Handling state: {state.__class__.__name__}")
            if isinstance(state, IdleClient):
                state = self._handle_idle_state(state, request)
            elif isinstance(state, CacheMiss):
                state = self._handle_cache_miss(state)
            elif isinstance(state, StoreAndUse):
                return self._handle_store_and_use(state, request)
            elif isinstance(state, CouldNotBeStored):
                return state.response
            elif isinstance(state, NeedRevalidation):
                state = self._handle_revalidation(state)
            elif isinstance(state, FromCache):
                self._maybe_refresh_pair_ttl(state.pair)
                return state.pair.response
            elif isinstance(state, NeedToBeUpdated):
                state = self._handle_update(state)
            elif isinstance(state, InvalidatePairs):
                state = self._handle_invalidate_pairs(state)
            else:
                assert_never(state)

        raise RuntimeError("Unreachable")

    def _handle_idle_state(self, state: IdleClient, request: Request) -> AnyState:
        stored_pairs = self.storage.get_pairs(self._get_key_for_request(request))
        return state.next(request, stored_pairs)

    def _handle_cache_miss(self, state: CacheMiss) -> AnyState:
        incomplete_pair = self.storage.create_pair(state.request)
        response = self.send_request(incomplete_pair.request)
        return state.next(response, incomplete_pair.id)

    def _handle_store_and_use(self, state: StoreAndUse, request: Request) -> Response:
        complete_pair = self.storage.add_response(
            state.pair_id,
            state.response,
            self._get_key_for_request(request),
        )
        return complete_pair.response

    def _handle_revalidation(self, state: NeedRevalidation) -> AnyState:
        revalidation_response = self.send_request(state.request)
        return state.next(revalidation_response)

    def _handle_update(self, state: NeedToBeUpdated) -> AnyState:
        for pair in state.updating_pairs:
            self.storage.update_pair(
                pair.id,
                lambda complete_pair: replace(
                    complete_pair,
                    response=replace(pair.response, headers=pair.response.headers),
                ),
            )
        return state.next()

    def _handle_invalidate_pairs(self, state: InvalidatePairs) -> AnyState:
        for pair_id in state.pair_ids:
            self.storage.remove(pair_id)
        return state.next()
