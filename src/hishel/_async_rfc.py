from __future__ import annotations

from typing import Awaitable, Callable

from typing_extensions import assert_never

from hishel import (
    AnyState,
    AsyncBaseStorage,
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
)
from hishel._core._spec import InvalidateEntries


async def handle_request_with_rfc(
    request: Request,
    send: Callable[[Request], Awaitable[Response]],
    storage: AsyncBaseStorage,
    key: str,
    options: CacheOptions,
    *,
    ttl: float | None = None,
    tti: float | None = None,
) -> Response:
    """
    Answer a request by following the RFC 9111 state machine.

    This knows nothing about any HTTP library, so that every integration can use
    it: ``send`` is how a request reaches the server.
    """
    state: AnyState = IdleClient(options=options)

    while True:
        if isinstance(state, IdleClient):
            state = state.next(request, await storage.get_entries(key))
        elif isinstance(state, (CacheMiss, NeedRevalidation)):
            state = state.next(await send(state.request))
        elif isinstance(state, StoreAndUse):
            entry = await storage.create_entry(request, state.response, key, ttl=ttl, tti=tti)
            return entry.response
        elif isinstance(state, CouldNotBeStored):
            return state.response
        elif isinstance(state, FromCache):
            return state.entry.response
        elif isinstance(state, NeedToBeUpdated):
            for updating_entry in state.updating_entries:
                await storage.update_headers(updating_entry.id, updating_entry.response.headers)
            state = state.next()
        elif isinstance(state, InvalidateEntries):
            for entry_id in state.entry_ids:
                await storage.remove_entry(entry_id)
            state = state.next()
        else:
            assert_never(state)
