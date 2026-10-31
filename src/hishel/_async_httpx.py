from __future__ import annotations

import hashlib
import ssl
import typing as t
from typing import AsyncIterable, AsyncIterator, Iterator, TypedDict, cast

from hishel import AsyncSqliteStorage, CacheOptions, Headers, Request, Response
from hishel._async_rfc import handle_request_with_rfc
from hishel._core._storages._async_base import AsyncBaseStorage
from hishel._utils import make_async_iterator

try:
    import httpx
except ImportError as e:
    raise ImportError(
        "httpx is required to use hishel.httpx module. "
        "Please install hishel with the 'httpx' extra, "
        "e.g., 'pip install hishel[httpx]'."
    ) from e


CACHEABLE_METHODS = frozenset({"GET", "HEAD"})


class CacheConfig(TypedDict, total=False):
    """Set on a transport, and overridable per request with the ``caching`` extension."""

    storage: AsyncBaseStorage
    rfc: bool | CacheOptions


def _headers_to_internal(headers: httpx.Headers) -> Headers:
    grouped: dict[str, list[str]] = {}
    for key, value in headers.multi_items():
        grouped.setdefault(key, []).append(value)
    # The body is stored without its transfer encoding.
    grouped.pop("transfer-encoding", None)
    return Headers(grouped)


def _headers_to_httpx(headers: Headers) -> list[tuple[bytes, bytes]]:
    # As bytes, because httpx encodes str headers as ASCII and raises on anything else.
    return [(key.encode(), value.encode()) for key in headers for value in headers.get_list(key) or []]


def _request_headers_with_changes(original: httpx.Headers, wanted: Headers) -> httpx.Headers:
    """
    Apply what differs from ``original`` to its raw pairs, leaving every other
    pair as it was, including duplicates, order and casing.
    """
    changed = {key.encode(): value.encode() for key, value in wanted.items() if original.get(key) != value}
    kept = [(key, value) for key, value in original.raw if key.lower() not in changed]
    return httpx.Headers([*kept, *changed.items()])


def _request_to_internal(request: httpx.Request) -> Request:
    return Request(method=request.method, url=str(request.url), headers=_headers_to_internal(request.headers))


def _response_to_internal(response: httpx.Response) -> Response:
    headers = _headers_to_internal(response.headers)
    if not response.is_stream_consumed:
        return Response(status_code=response.status_code, headers=headers, stream=response.aiter_raw())

    if "content-encoding" in headers:
        # Already read and decoded, so what we have no longer matches these headers.
        del headers["content-encoding"]
        headers.pop("content-length", None)
        headers["content-length"] = str(len(response.content))
    return Response(status_code=response.status_code, headers=headers, stream=make_async_iterator([response.content]))


def _response_to_httpx(response: Response, upstream: httpx.Response | None = None) -> httpx.Response:
    assert isinstance(response.stream, (AsyncIterator, AsyncIterable))
    return httpx.Response(
        status_code=response.status_code,
        headers=_headers_to_httpx(response.headers),
        stream=_ResponseStream(response.stream, upstream),
        extensions=upstream.extensions if upstream is not None else {},
    )


class _ResponseStream(httpx.SyncByteStream, httpx.AsyncByteStream):
    def __init__(self, iterator: Iterator[bytes] | AsyncIterator[bytes], upstream: httpx.Response | None) -> None:
        self.iterator = iterator
        self.upstream = upstream

    async def __aiter__(self) -> AsyncIterator[bytes]:
        assert isinstance(self.iterator, (AsyncIterator, AsyncIterable))
        async for chunk in self.iterator:
            yield chunk

    async def aclose(self) -> None:
        # Closing the iterator discards a partial save, but it doesn't reach the
        # iterator it was reading from, so the upstream response is closed here.
        if hasattr(self.iterator, "aclose"):
            await self.iterator.aclose()
        if self.upstream is not None:
            await self.upstream.aclose()


class AsyncCacheTransport(httpx.AsyncBaseTransport):
    """
    By default, caches successful GET and HEAD responses by method and URL, ignoring
    HTTP caching headers, and serves an entry until the storage's TTL or TTI expires
    it. With ``rfc=True`` or ``CacheOptions``, follows RFC 9111 instead.
    """

    def __init__(
        self,
        next_transport: httpx.AsyncBaseTransport,
        storage: AsyncBaseStorage | None = None,
        rfc: bool | CacheOptions = False,
    ) -> None:
        self.next_transport = next_transport
        self.config = CacheConfig(storage=storage or AsyncSqliteStorage(), rfc=rfc)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        overrides = cast(CacheConfig, request.extensions.get("caching", {}))
        effective_config: CacheConfig = {**self.config, **overrides}

        storage = effective_config["storage"]
        key = hashlib.sha256(f"{request.method} {request.url}".encode()).hexdigest()

        rfc = effective_config["rfc"]
        if rfc is False:
            return await self._handle_without_rfc(request, storage, key)
        return await self._handle_with_rfc(request, storage, key, CacheOptions() if rfc is True else rfc)

    async def _handle_with_rfc(
        self,
        request: httpx.Request,
        storage: AsyncBaseStorage,
        key: str,
        options: CacheOptions,
    ) -> httpx.Response:
        upstream: httpx.Response | None = None

        async def send(internal_request: Request) -> Response:
            nonlocal upstream
            # The original request is what gets sent, so that nothing about it is
            # lost. The state machine only changes it to add revalidation headers,
            # and those are only for this send, so the caller never sees them.
            original_headers = request.headers
            request.headers = original_headers.copy()
            for key_, value in internal_request.headers.items():
                if original_headers.get(key_) != value:
                    request.headers[key_] = value
            try:
                response = await self.next_transport.handle_async_request(request)
            finally:
                request.headers = original_headers

            if response.status_code == 304:
                # The body served will be the cached one, so this connection is done.
                await response.aread()
            else:
                upstream = response
            return _response_to_internal(response)

        response = await handle_request_with_rfc(_request_to_internal(request), send, storage, key, options)
        return _response_to_httpx(response, upstream)

    async def _handle_without_rfc(self, request: httpx.Request, storage: AsyncBaseStorage, key: str) -> httpx.Response:
        if request.method not in CACHEABLE_METHODS:
            return await self.next_transport.handle_async_request(request)

        entries = await storage.get_entries(key)
        if entries:
            return _response_to_httpx(entries[0].response)

        response = await self.next_transport.handle_async_request(request)
        # A 206 only holds part of the body, so it can't answer later requests.
        if not response.is_success or response.status_code == 206:
            return response

        entry = await storage.create_entry(_request_to_internal(request), _response_to_internal(response), key)
        return _response_to_httpx(entry.response, upstream=response)

    async def aclose(self) -> None:
        await self.next_transport.aclose()
        await self.config["storage"].close()


class AsyncCacheClient(httpx.AsyncClient):
    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        self.storage: AsyncBaseStorage | None = kwargs.pop("storage", None)
        self.rfc: bool | CacheOptions = kwargs.pop("rfc", False)
        super().__init__(*args, **kwargs)

    def _init_transport(
        self,
        verify: ssl.SSLContext | str | bool = True,
        cert: t.Union[str, t.Tuple[str, str], t.Tuple[str, str, str], None] = None,
        trust_env: bool = True,
        http1: bool = True,
        http2: bool = False,
        limits: httpx.Limits = httpx.Limits(max_connections=100, max_keepalive_connections=20),
        transport: httpx.AsyncBaseTransport | None = None,
        **kwargs: t.Any,
    ) -> httpx.AsyncBaseTransport:
        if transport is not None:
            return transport

        return AsyncCacheTransport(
            next_transport=httpx.AsyncHTTPTransport(
                verify=verify,
                cert=cert,
                trust_env=trust_env,
                http1=http1,
                http2=http2,
                limits=limits,
            ),
            storage=self.storage,
            rfc=self.rfc,
        )

    def _init_proxy_transport(
        self,
        proxy: httpx.Proxy,
        verify: ssl.SSLContext | str | bool = True,
        cert: t.Union[str, t.Tuple[str, str], t.Tuple[str, str, str], None] = None,
        trust_env: bool = True,
        http1: bool = True,
        http2: bool = False,
        limits: httpx.Limits = httpx.Limits(max_connections=100, max_keepalive_connections=20),
        **kwargs: t.Any,
    ) -> httpx.AsyncBaseTransport:
        return AsyncCacheTransport(
            next_transport=httpx.AsyncHTTPTransport(
                verify=verify,
                cert=cert,
                trust_env=trust_env,
                http1=http1,
                http2=http2,
                limits=limits,
                proxy=proxy,
            ),
            storage=self.storage,
            rfc=self.rfc,
        )
