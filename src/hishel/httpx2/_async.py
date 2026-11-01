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
    import httpx2
except ImportError as e:
    raise ImportError(
        "httpx2 is required to use hishel.httpx2 module. "
        "Please install hishel with the 'httpx2' extra, "
        "e.g., 'pip install hishel[httpx2]'."
    ) from e


CACHEABLE_METHODS = frozenset({"GET", "HEAD"})


class CacheConfig(TypedDict, total=False):
    """Set on a transport, and overridable per request with the ``caching`` extension."""

    storage: AsyncBaseStorage
    rfc: bool | CacheOptions
    ttl: float | None
    tti: float | None
    key: str


def _headers_to_internal(headers: httpx2.Headers) -> Headers:
    grouped: dict[str, list[str]] = {}
    for key, value in headers.multi_items():
        grouped.setdefault(key, []).append(value)
    # The body is stored without its transfer encoding.
    grouped.pop("transfer-encoding", None)
    return Headers(grouped)


def _headers_to_httpx2(headers: Headers) -> list[tuple[bytes, bytes]]:
    # As bytes, because httpx2 encodes str headers as ASCII and raises on anything else.
    return [(key.encode(), value.encode()) for key in headers for value in headers.get_list(key) or []]


def _request_headers_with_changes(original: httpx2.Headers, wanted: Headers) -> httpx2.Headers:
    """
    Apply what differs from ``original`` to its raw pairs, leaving every other
    pair as it was, including duplicates, order and casing.
    """
    changed = {key.encode(): value.encode() for key, value in wanted.items() if original.get(key) != value}
    kept = [(key, value) for key, value in original.raw if key.lower() not in changed]
    return httpx2.Headers([*kept, *changed.items()])


def _request_to_internal(request: httpx2.Request) -> Request:
    return Request(method=request.method, url=str(request.url), headers=_headers_to_internal(request.headers))


def _response_to_internal(response: httpx2.Response) -> Response:
    headers = _headers_to_internal(response.headers)
    if not response.is_stream_consumed:
        return Response(status_code=response.status_code, headers=headers, stream=response.aiter_raw())

    if "content-encoding" in headers:
        # Already read and decoded, so what we have no longer matches these headers.
        del headers["content-encoding"]
        headers.pop("content-length", None)
        headers["content-length"] = str(len(response.content))
    return Response(status_code=response.status_code, headers=headers, stream=make_async_iterator([response.content]))


def _response_to_httpx2(response: Response, upstream: httpx2.Response | None = None) -> httpx2.Response:
    assert isinstance(response.stream, (AsyncIterator, AsyncIterable))
    return httpx2.Response(
        status_code=response.status_code,
        headers=_headers_to_httpx2(response.headers),
        stream=_ResponseStream(response.stream, upstream),
        extensions=upstream.extensions if upstream is not None else {},
    )


class _ResponseStream(httpx2.SyncByteStream, httpx2.AsyncByteStream):
    def __init__(self, iterator: Iterator[bytes] | AsyncIterator[bytes], upstream: httpx2.Response | None) -> None:
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


class AsyncCacheTransport(httpx2.AsyncBaseTransport):
    """
    By default, caches successful GET and HEAD responses by method and URL, ignoring
    HTTP caching headers, and serves an entry until the storage's TTL or TTI expires
    it. With ``rfc=True`` or ``CacheOptions``, follows RFC 9111 instead.
    """

    def __init__(
        self,
        next_transport: httpx2.AsyncBaseTransport,
        storage: AsyncBaseStorage | None = None,
        rfc: bool | CacheOptions = False,
    ) -> None:
        self.next_transport = next_transport
        self.config = CacheConfig(storage=storage or AsyncSqliteStorage(), rfc=rfc)

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        overrides = cast(CacheConfig, request.extensions.get("caching", {}))
        effective_config: CacheConfig = {**self.config, **overrides}

        storage = effective_config["storage"]
        rfc = effective_config["rfc"]
        key = effective_config.get("key")
        if key is None:
            # In RFC mode, all methods share a key, so that an unsafe request finds the entries it invalidates.
            # The prefix keeps it apart from the key 1.x used, which Redis may still hold in another format.
            identity = f"RFC {request.url}" if rfc is not False else f"{request.method} {request.url}"
            key = hashlib.sha256(identity.encode()).hexdigest()

        ttl, tti = effective_config.get("ttl"), effective_config.get("tti")
        if rfc is False:
            return await self._handle_without_rfc(request, storage, key, ttl, tti)
        return await self._handle_with_rfc(request, storage, key, CacheOptions() if rfc is True else rfc, ttl, tti)

    async def _handle_with_rfc(
        self,
        request: httpx2.Request,
        storage: AsyncBaseStorage,
        key: str,
        options: CacheOptions,
        ttl: float | None,
        tti: float | None,
    ) -> httpx2.Response:
        upstream: httpx2.Response | None = None

        async def send(internal_request: Request) -> Response:
            nonlocal upstream
            # The original request is what gets sent, so that nothing about it is
            # lost. The state machine only changes it to add revalidation headers,
            # and those are only for this send, so the caller never sees them.
            original_headers = request.headers
            request.headers = _request_headers_with_changes(original_headers, internal_request.headers)
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

        response = await handle_request_with_rfc(
            _request_to_internal(request),
            send,
            storage,
            key,
            options,
            ttl=ttl,
            tti=tti,
        )
        return _response_to_httpx2(response, upstream)

    async def _handle_without_rfc(
        self,
        request: httpx2.Request,
        storage: AsyncBaseStorage,
        key: str,
        ttl: float | None,
        tti: float | None,
    ) -> httpx2.Response:
        if request.method not in CACHEABLE_METHODS:
            return await self.next_transport.handle_async_request(request)

        # A custom key can be shared by GET and HEAD, whose responses aren't interchangeable.
        entries = [entry for entry in await storage.get_entries(key) if entry.request.method == request.method]
        if entries:
            return _response_to_httpx2(entries[0].response)

        response = await self.next_transport.handle_async_request(request)
        # A 206 only holds part of the body, so it can't answer later requests.
        if not response.is_success or response.status_code == 206:
            return response

        entry = await storage.create_entry(
            _request_to_internal(request),
            _response_to_internal(response),
            key,
            ttl=ttl,
            tti=tti,
        )
        return _response_to_httpx2(entry.response, upstream=response)

    async def aclose(self) -> None:
        await self.next_transport.aclose()
        await self.config["storage"].close()


class AsyncCacheClient(httpx2.AsyncClient):
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
        limits: httpx2.Limits = httpx2.Limits(max_connections=100, max_keepalive_connections=20),
        transport: httpx2.AsyncBaseTransport | None = None,
        **kwargs: t.Any,
    ) -> httpx2.AsyncBaseTransport:
        if transport is not None:
            return transport

        return AsyncCacheTransport(
            next_transport=httpx2.AsyncHTTPTransport(
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
        proxy: httpx2.Proxy,
        verify: ssl.SSLContext | str | bool = True,
        cert: t.Union[str, t.Tuple[str, str], t.Tuple[str, str, str], None] = None,
        trust_env: bool = True,
        http1: bool = True,
        http2: bool = False,
        limits: httpx2.Limits = httpx2.Limits(max_connections=100, max_keepalive_connections=20),
        **kwargs: t.Any,
    ) -> httpx2.AsyncBaseTransport:
        return AsyncCacheTransport(
            next_transport=httpx2.AsyncHTTPTransport(
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
