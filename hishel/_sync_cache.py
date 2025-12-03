from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import replace
from typing import Iterable, Iterator, Awaitable, Callable

from typing_extensions import assert_never

from hishel import (
    AnyState,
    SyncBaseStorage,
    SyncSqliteStorage,
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
from hishel._utils import make_sync_iterator

logger = logging.getLogger("hishel.integrations.clients")


class SyncCacheProxy:
    """
    A proxy for HTTP caching in clients.

    This class is independent of any specific HTTP library and works only with internal models.
    It delegates request execution to a user-provided callable, making it compatible with any
    HTTP client. Caching behavior is determined by the policy object.

    Args:
        request_sender: Callable that sends HTTP requests and returns responses.
        storage: Storage backend for cache entries. Defaults to SyncSqliteStorage.
        policy: Caching policy to use. Can be SpecificationPolicy (respects RFC 9111) or
            FilterPolicy (user-defined filtering). Defaults to SpecificationPolicy().
    """

    def __init__(
        self,
        request_sender: Callable[[Request], Response],
        storage: SyncBaseStorage | None = None,
        policy: CachePolicy | None = None,
    ) -> None:
        self.send_request = request_sender
        self.storage = storage if storage is not None else SyncSqliteStorage()
        self.policy = policy if policy is not None else SpecificationPolicy()

    def handle_request(self, request: Request) -> Response:
        if isinstance(self.policy, FilterPolicy):
            return self._handle_request_with_filters(request)
        return self._handle_request_respecting_spec(request)

    def _get_key_for_request(self, request: Request) -> str:
        if self.policy.use_body_key or request.metadata.get("hishel_body_key"):
            assert isinstance(request.stream, (Iterator, Iterable))
            collected = b"".join([chunk for chunk in request.stream])
            hash_ = hashlib.sha256(collected).hexdigest()
            request.stream = make_sync_iterator([collected])
            return hash_
        return hashlib.sha256(str(request.url).encode("utf-8")).hexdigest()

    def _maybe_refresh_entry_ttl(self, entry: Entry) -> None:
        if entry.request.metadata.get("hishel_refresh_ttl_on_access"):
            self.storage.update_entry(
                entry.id,
                lambda current_entry: replace(
                    current_entry,
                    meta=replace(current_entry.meta, created_at=time.time()),
                ),
            )

    def _handle_request_with_filters(self, request: Request) -> Response:
        assert isinstance(self.policy, FilterPolicy)

        for request_filter in self.policy.request_filters:
            if request_filter.needs_body():
                body = request.read()
                if not request_filter.apply(request, body):
                    logger.debug("Request filtered out by request filter")
                    return self.send_request(request)
            else:
                if not request_filter.apply(request, None):
                    logger.debug("Request filtered out by request filter")
                    return self.send_request(request)

        logger.debug("Trying to get cached response ignoring specification")
        cache_key = self._get_key_for_request(request)
        entries = self.storage.get_entries(cache_key)

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
                self._maybe_refresh_entry_ttl(entry)
                return entry.response

        response = self.send_request(request)
        for response_filter in self.policy.response_filters:
            if response_filter.needs_body():
                body = response.read()
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
        entry = self.storage.create_entry(
            request,
            response,
            cache_key,
        )
        return entry.response

    def _handle_request_respecting_spec(self, request: Request) -> Response:
        assert isinstance(self.policy, SpecificationPolicy)
        state: AnyState = IdleClient(options=self.policy.cache_options)

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
                self._maybe_refresh_entry_ttl(state.entry)
                return state.entry.response
            elif isinstance(state, NeedToBeUpdated):
                state = self._handle_update(state)
            elif isinstance(state, InvalidateEntries):
                state = self._handle_invalidate_entries(state)
            else:
                assert_never(state)

        raise RuntimeError("Unreachable")

    def _handle_idle_state(self, state: IdleClient, request: Request) -> AnyState:
        stored_entries = self.storage.get_entries(self._get_key_for_request(request))
        return state.next(request, stored_entries)

    def _handle_cache_miss(self, state: CacheMiss) -> AnyState:
        response = self.send_request(state.request)
        return state.next(response)

    def _handle_store_and_use(self, state: StoreAndUse, request: Request) -> Response:
        entry = self.storage.create_entry(
            request,
            state.response,
            self._get_key_for_request(request),
        )
        return entry.response

    def _handle_revalidation(self, state: NeedRevalidation) -> AnyState:
        revalidation_response = self.send_request(state.request)
        return state.next(revalidation_response)

    def _handle_update(self, state: NeedToBeUpdated) -> AnyState:
        for updating_entry in state.updating_entries:
            self.storage.update_entry(
                updating_entry.id,
                lambda existing_entry: replace(
                    existing_entry,
                    response=replace(existing_entry.response, headers=updating_entry.response.headers),
                ),
            )
        return state.next()

    def _handle_invalidate_entries(self, state: InvalidateEntries) -> AnyState:
        for entry_id in state.entry_ids:
            self.storage.remove_entry(entry_id)
        return state.next()
