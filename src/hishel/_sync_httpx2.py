from __future__ import annotations

import ssl
import typing as t
from typing import (
    Iterable,
    Iterator,
    Union,
    cast,
    overload,
)

from hishel import Headers, Request, Response, SyncCacheProxy
from hishel._core._storages._sync_base import SyncBaseStorage
from hishel._core.models import RequestMetadata, extract_metadata_from_headers
from hishel._policies import CachePolicy
from hishel._utils import (
    filter_mapping,
    make_sync_iterator,
)

try:
    import httpx2
    from httpx2 import RequestNotRead
except ImportError as e:
    raise ImportError(
        "httpx2 is required to use hishel.httpx2 module. "
        "Please install hishel with the 'httpx2' extra, "
        "e.g., 'pip install hishel[httpx2]'."
    ) from e

SOCKET_OPTION = t.Union[
    t.Tuple[int, int, int],
    t.Tuple[int, int, t.Union[bytes, bytearray]],
    t.Tuple[int, int, None, int],
]

# 128 KB
CHUNK_SIZE = 131072


@overload
def _internal_to_httpx(
    value: Request,
) -> httpx2.Request: ...
@overload
def _internal_to_httpx(
    value: Response,
) -> httpx2.Response: ...
def _internal_to_httpx(
    value: Union[Request, Response],
) -> Union[httpx2.Request, httpx2.Response]:
    """
    Convert internal Request/Response to httpx2.Request/httpx2.Response.
    """
    if isinstance(value, Request):
        return httpx2.Request(
            method=value.method,
            url=value.url,
            headers=value.headers,
            stream=_IteratorStream(value._iter_stream()),
            extensions=value.metadata,
        )
    elif isinstance(value, Response):
        return httpx2.Response(
            status_code=value.status_code,
            headers=value.headers,
            stream=_IteratorStream(value._iter_stream()),
            extensions=value.metadata,
        )


@overload
def _httpx_to_internal(
    value: httpx2.Request,
) -> Request: ...
@overload
def _httpx_to_internal(
    value: httpx2.Response,
) -> Response: ...
def _httpx_to_internal(
    value: Union[httpx2.Request, httpx2.Response],
) -> Union[Request, Response]:
    """
    Convert httpx2.Request/httpx2.Response to internal Request/Response.
    """
    headers = Headers(
        filter_mapping(
            Headers({key: value for key, value in value.headers.items()}),
            ["Transfer-Encoding"],
        )
    )
    if isinstance(value, httpx2.Request):
        extension_metadata = RequestMetadata(
            hishel_refresh_ttl_on_access=value.extensions.get("hishel_refresh_ttl_on_access"),
            hishel_ttl=value.extensions.get("hishel_ttl"),
            hishel_spec_ignore=value.extensions.get("hishel_spec_ignore"),
            hishel_body_key=value.extensions.get("hishel_body_key"),
        )
        headers_metadata = extract_metadata_from_headers(value.headers)

        for key, val in extension_metadata.items():
            if key in value.extensions:
                headers_metadata[key] = val  # type: ignore

        try:
            stream = make_sync_iterator([value.content])
        except RequestNotRead:
            stream = cast(Iterator[bytes], value.stream)

        return Request(
            method=value.method,
            url=str(value.url),
            headers=headers,
            stream=stream,
            metadata=headers_metadata,
        )
    elif isinstance(value, httpx2.Response):
        stream = (
            make_sync_iterator([value.content]) if value.is_stream_consumed else value.iter_raw(chunk_size=CHUNK_SIZE)
        )

        if value.is_stream_consumed and "content-encoding" in value.headers:
            # If the stream was consumed and we don't know about
            # the original data and its size, fix the Content-Length
            # header and remove Content-Encoding so we can recreate it later properly.
            headers = Headers(
                {
                    **filter_mapping(
                        headers,
                        ["content-encoding"],
                    ),
                    "content-length": str(len(value.content)),
                }
            )

        return Response(
            status_code=value.status_code,
            headers=headers,
            stream=stream,
            metadata={},
        )


class _IteratorStream(httpx2.SyncByteStream, httpx2.AsyncByteStream):
    def __init__(self, iterator: Iterator[bytes]) -> None:
        self.iterator = iterator

    def __iter__(self) -> Iterator[bytes]:
        assert isinstance(self.iterator, (Iterator, Iterable))
        for chunk in self.iterator:
            yield chunk


class SyncCacheTransport(httpx2.BaseTransport):
    def __init__(
        self,
        next_transport: httpx2.BaseTransport,
        storage: SyncBaseStorage | None = None,
        policy: CachePolicy | None = None,
    ) -> None:
        self.next_transport = next_transport
        self._cache_proxy: SyncCacheProxy = SyncCacheProxy(
            request_sender=self.request_sender,
            storage=storage,
            policy=policy,
        )
        self.storage = self._cache_proxy.storage

    def handle_request(
        self,
        request: httpx2.Request,
    ) -> httpx2.Response:
        internal_request = _httpx_to_internal(request)
        internal_response = self._cache_proxy.handle_request(internal_request)
        response = _internal_to_httpx(internal_response)
        return response

    def close(self) -> None:
        self.next_transport.close()
        self.storage.close()
        super().close()

    def request_sender(self, request: Request) -> Response:
        httpx_request = _internal_to_httpx(request)
        httpx_response = self.next_transport.handle_request(httpx_request)
        if httpx_response.status_code == 304:
            # 304 should not have a body, but we read it to ensure we'll not let the stream unconsumed
            httpx_response.read()
        return _httpx_to_internal(httpx_response)


class SyncCacheClient(httpx2.Client):
    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        self.storage: SyncBaseStorage | None = kwargs.pop("storage", None)
        self.policy: CachePolicy | None = kwargs.pop("policy", None)
        super().__init__(*args, **kwargs)

    def _init_transport(
        self,
        verify: ssl.SSLContext | str | bool = True,
        cert: t.Union[str, t.Tuple[str, str], t.Tuple[str, str, str], None] = None,
        trust_env: bool = True,
        http1: bool = True,
        http2: bool = False,
        limits: httpx2.Limits = httpx2.Limits(max_connections=100, max_keepalive_connections=20),
        transport: httpx2.BaseTransport | None = None,
        **kwargs: t.Any,
    ) -> httpx2.BaseTransport:
        if transport is not None:
            return transport

        return SyncCacheTransport(
            next_transport=httpx2.HTTPTransport(
                verify=verify,
                cert=cert,
                trust_env=trust_env,
                http1=http1,
                http2=http2,
                limits=limits,
            ),
            storage=self.storage,
            policy=self.policy,
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
    ) -> httpx2.BaseTransport:
        return SyncCacheTransport(
            next_transport=httpx2.HTTPTransport(
                verify=verify,
                cert=cert,
                trust_env=trust_env,
                http1=http1,
                http2=http2,
                limits=limits,
                proxy=proxy,
            ),
            storage=self.storage,
            policy=self.policy,
        )
