from __future__ import annotations

import hashlib
import ssl
import typing as t
from typing import Iterable, Iterator, Iterator, TypedDict, cast

from hishel import SyncSqliteStorage, CacheOptions, Headers, Request, Response
from hishel._sync_rfc import handle_request_with_rfc
from hishel._core._storages._sync_base import SyncBaseStorage
from hishel._utils import make_sync_iterator

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

    storage: SyncBaseStorage
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
        return Response(status_code=response.status_code, headers=headers, stream=response.iter_raw())

    if "content-encoding" in headers:
        # Already read and decoded, so what we have no longer matches these headers.
        del headers["content-encoding"]
        headers.pop("content-length", None)
        headers["content-length"] = str(len(response.content))
    return Response(status_code=response.status_code, headers=headers, stream=make_sync_iterator([response.content]))


def _response_to_httpx(response: Response, upstream: httpx.Response | None = None) -> httpx.Response:
    assert isinstance(response.stream, (Iterator, Iterable))
    return httpx.Response(
        status_code=response.status_code,
        headers=_headers_to_httpx(response.headers),
        stream=_ResponseStream(response.stream, upstream),
        extensions=upstream.extensions if upstream is not None else {},
    )


class _ResponseStream(httpx.SyncByteStream, httpx.AsyncByteStream):
    def __init__(self, iterator: Iterator[bytes] | Iterator[bytes], upstream: httpx.Response | None) -> None:
        self.iterator = iterator
        self.upstream = upstream

    def __iter__(self) -> Iterator[bytes]:
        assert isinstance(self.iterator, (Iterator, Iterable))
        for chunk in self.iterator:
            yield chunk

    def close(self) -> None:
        # Closing the iterator discards a partial save, but it doesn't reach the
        # iterator it was reading from, so the upstream response is closed here.
        if hasattr(self.iterator, "close"):
            self.iterator.close()
        if self.upstream is not None:
            self.upstream.close()


class SyncCacheTransport(httpx.BaseTransport):
    """
    By default, caches successful GET and HEAD responses by method and URL, ignoring
    HTTP caching headers, and serves an entry until the storage's TTL or TTI expires
    it. With ``rfc=True`` or ``CacheOptions``, follows RFC 9111 instead.
    """

    def __init__(
        self,
        next_transport: httpx.BaseTransport,
        storage: SyncBaseStorage | None = None,
        rfc: bool | CacheOptions = False,
    ) -> None:
        self.next_transport = next_transport
        self.config = CacheConfig(storage=storage or SyncSqliteStorage(), rfc=rfc)

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        overrides = cast(CacheConfig, request.extensions.get("caching", {}))
        effective_config: CacheConfig = {**self.config, **overrides}

        storage = effective_config["storage"]
        key = hashlib.sha256(f"{request.method} {request.url}".encode()).hexdigest()

        rfc = effective_config["rfc"]
        if rfc is False:
            return self._handle_without_rfc(request, storage, key)
        return self._handle_with_rfc(request, storage, key, CacheOptions() if rfc is True else rfc)

    def _handle_with_rfc(
        self,
        request: httpx.Request,
        storage: SyncBaseStorage,
        key: str,
        options: CacheOptions,
    ) -> httpx.Response:
        upstream: httpx.Response | None = None

        def send(internal_request: Request) -> Response:
            nonlocal upstream
            # The original request is what gets sent, so that nothing about it is
            # lost. The state machine only changes it to add revalidation headers,
            # and those are only for this send, so the caller never sees them.
            original_headers = request.headers
            request.headers = _request_headers_with_changes(original_headers, internal_request.headers)
            try:
                response = self.next_transport.handle_request(request)
            finally:
                request.headers = original_headers

            if response.status_code == 304:
                # The body served will be the cached one, so this connection is done.
                response.read()
            else:
                upstream = response
            return _response_to_internal(response)

        response = handle_request_with_rfc(_request_to_internal(request), send, storage, key, options)
        return _response_to_httpx(response, upstream)

    def _handle_without_rfc(self, request: httpx.Request, storage: SyncBaseStorage, key: str) -> httpx.Response:
        if request.method not in CACHEABLE_METHODS:
            return self.next_transport.handle_request(request)

        entries = storage.get_entries(key)
        if entries:
            return _response_to_httpx(entries[0].response)

        response = self.next_transport.handle_request(request)
        # A 206 only holds part of the body, so it can't answer later requests.
        if not response.is_success or response.status_code == 206:
            return response

        entry = storage.create_entry(_request_to_internal(request), _response_to_internal(response), key)
        return _response_to_httpx(entry.response, upstream=response)

    def close(self) -> None:
        self.next_transport.close()
        self.config["storage"].close()


class SyncCacheClient(httpx.Client):
    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        self.storage: SyncBaseStorage | None = kwargs.pop("storage", None)
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
        transport: httpx.BaseTransport | None = None,
        **kwargs: t.Any,
    ) -> httpx.BaseTransport:
        if transport is not None:
            return transport

        return SyncCacheTransport(
            next_transport=httpx.HTTPTransport(
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
    ) -> httpx.BaseTransport:
        return SyncCacheTransport(
            next_transport=httpx.HTTPTransport(
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
