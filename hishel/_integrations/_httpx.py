from __future__ import annotations

from dataclasses import replace
from typing import AsyncIterator, Iterable, Iterator, Union, overload

import httpx
from typing_extensions import assert_never

from hishel import Headers, Request, Response, SyncLmdbStorage
from hishel._core._async._storages._lmdb import AsyncLmdbStorage
from hishel._core._spec import (
    AnyState,
    CacheMiss,
    CouldNotBeStored,
    FromCache,
    IdleClient,
    NeedRevalidation,
    NeedToBeUpdated,
    StoreAndUse,
    create_idle_state,
)
from hishel._core.models import AnyIterable


@overload
def internal_to_httpx(
    value: Request,
) -> httpx.Request: ...


@overload
def internal_to_httpx(
    value: Response,
) -> httpx.Response: ...


def internal_to_httpx(
    value: Union[Request, Response],
) -> Union[httpx.Request, httpx.Response]:
    """
    Convert internal Request/Response to httpx.Request/httpx.Response.
    """
    if isinstance(value, Request):
        return httpx.Request(
            method=value.method,
            url=value.url,
            headers=value.headers,
            content=value.stream,
            extensions=value.extra,
        )
    elif isinstance(value, Response):
        return httpx.Response(
            status_code=value.status_code,
            headers=value.headers,
            content=value.stream,
            extensions=value.extra,
        )


@overload
def httpx_to_internal(
    value: httpx.Request,
) -> Request: ...


@overload
def httpx_to_internal(
    value: httpx.Response,
) -> Response: ...


def httpx_to_internal(
    value: Union[httpx.Request, httpx.Response],
) -> Union[Request, Response]:
    """
    Convert httpx.Request/httpx.Response to internal Request/Response.
    """
    stream: httpx.SyncByteStream | httpx.AsyncByteStream | httpx.ByteStream | list[bytes] | AnyIterable
    try:
        stream = AnyIterable(value.content)
    except (httpx.RequestNotRead, httpx.ResponseNotRead):
        stream = value.stream

    stream_iterator: Iterator[bytes] | AsyncIterator[bytes]
    if isinstance(stream, Iterable):
        stream_iterator = iter(stream)
    else:
        # Mypy cannot infer that stream is AsyncByteStream here
        stream_iterator = stream.__aiter__()  # type: ignore[union-attr]

    if isinstance(value, httpx.Request):
        return Request(
            method=value.method,
            url=str(value.url),
            headers=Headers({key: value for key, value in value.headers.items()}),
            stream=stream_iterator,
            extra={},
        )
    elif isinstance(value, httpx.Response):
        return Response(
            status_code=value.status_code,
            headers=Headers({key: value for key, value in value.headers.items()}),
            stream=stream_iterator,
            extra={},
        )


class AsyncCacheTransport(httpx.AsyncBaseTransport):
    def __init__(self, transport: httpx.AsyncBaseTransport) -> None:
        self._transport: httpx.AsyncBaseTransport = transport
        self.storage = AsyncLmdbStorage()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        state: AnyState = create_idle_state("client")

        while state:
            if isinstance(state, IdleClient):
                new_pair = await self.storage.create_pair(
                    str(request.url),
                    httpx_to_internal(request),
                )
                stored_pairs = await self.storage.get_pairs(str(request.url))

                state = state.next(
                    new_pair,
                    stored_pairs,
                )
            elif isinstance(state, CacheMiss):
                response = await self._transport.handle_async_request(internal_to_httpx(state.request))

                complete_pair = await self.storage.add_response(state.pair_id, httpx_to_internal(response))
                state = state.next(complete_pair)
            elif isinstance(state, StoreAndUse):
                complete_pair = await self.storage.add_response(state.pair.id, state.pair.response)
                return internal_to_httpx(state.pair.response)
            elif isinstance(state, CouldNotBeStored):
                return internal_to_httpx(state.pair.response)
            elif isinstance(state, NeedRevalidation):
                revalidation_response = await self._transport.handle_async_request(internal_to_httpx(state.request))

                revalidation_complete_pair = await self.storage.add_response(
                    state.pair_id, httpx_to_internal(revalidation_response)
                )
                state = state.next(revalidation_complete_pair)
            elif isinstance(state, FromCache):
                return internal_to_httpx(state.pair.response)
            elif isinstance(state, NeedToBeUpdated):
                for pair in state.updating_pairs:
                    await self.storage.update_pair(
                        pair.id,
                        lambda complete_pair: replace(
                            complete_pair, response=replace(pair.response, headers=pair.response.headers)
                        ),
                    )
                state = state.next()
            else:
                assert_never(state)

        raise RuntimeError("Unreachable")


class CacheTransport(httpx.BaseTransport):
    def __init__(self, transport: httpx.BaseTransport) -> None:
        self._transport = transport
        self.storage = SyncLmdbStorage()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        state: AnyState = create_idle_state("client")

        while state:
            print(state.__class__.__name__)
            if isinstance(state, IdleClient):
                new_pair = self.storage.create_pair(
                    str(request.url),
                    httpx_to_internal(request),
                )
                stored_pairs = self.storage.get_pairs(str(request.url))

                state = state.next(
                    new_pair,
                    stored_pairs,
                )
            elif isinstance(state, CacheMiss):
                response = self._transport.handle_request(internal_to_httpx(state.request))

                complete_pair = self.storage.add_response(state.pair_id, httpx_to_internal(response))
                state = state.next(complete_pair)
            elif isinstance(state, StoreAndUse):
                complete_pair = self.storage.add_response(state.pair.id, state.pair.response)
                return internal_to_httpx(state.pair.response)
            elif isinstance(state, CouldNotBeStored):
                return internal_to_httpx(state.pair.response)
            elif isinstance(state, NeedRevalidation):
                revalidation_response = self._transport.handle_request(internal_to_httpx(state.request))

                revalidation_complete_pair = self.storage.add_response(
                    state.pair_id, httpx_to_internal(revalidation_response)
                )
                state = state.next(revalidation_complete_pair)
            elif isinstance(state, FromCache):
                return internal_to_httpx(state.pair.response)
            elif isinstance(state, NeedToBeUpdated):
                for pair in state.updating_pairs:
                    self.storage.update_pair(
                        pair.id,
                        lambda complete_pair: replace(
                            complete_pair, response=replace(pair.response, headers=pair.response.headers)
                        ),
                    )
                state = state.next()
            else:
                assert_never(state)

        raise RuntimeError("Unreachable")
