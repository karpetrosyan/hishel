from __future__ import annotations

import ssl
import typing as t
from typing import (
    AsyncIterable,
    AsyncIterator,
    Iterator,
    Union,
    cast,
    overload,
)

from httpx import RequestNotRead

from hishel import AsyncCacheProxy, Headers, Request, Response
from hishel._core._storages._async_base import AsyncBaseStorage
from hishel._core.models import RequestMetadata, extract_metadata_from_headers
from hishel._policies import CachePolicy
from hishel._utils import (
    filter_mapping,
    make_async_iterator,
)

try:
    import httpx
except ImportError as e:
    raise ImportError(
        "httpx is required to use hishel.httpx module. "
        "Please install hishel with the 'httpx' extra, "
        "e.g., 'pip install hishel[httpx]'."
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
) -> httpx.Request: ...
@overload
def _internal_to_httpx(
    value: Response,
) -> httpx.Response: ...
def _internal_to_httpx(
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
            stream=_IteratorStream(value._aiter_stream()),
            extensions=value.metadata,
        )
    elif isinstance(value, Response):
        return httpx.Response(
            status_code=value.status_code,
            headers=value.headers,
            stream=_IteratorStream(value._aiter_stream()),
            extensions=value.metadata,
        )


@overload
def _httpx_to_internal(
    value: httpx.Request,
) -> Request: ...
@overload
def _httpx_to_internal(
    value: httpx.Response,
) -> Response: ...
def _httpx_to_internal(
    value: Union[httpx.Request, httpx.Response],
) -> Union[Request, Response]:
    """
    Convert httpx.Request/httpx.Response to internal Request/Response.
    """
    headers = Headers(
        filter_mapping(
            Headers({key: value for key, value in value.headers.items()}),
            ["Transfer-Encoding"],
        )
    )
    if isinstance(value, httpx.Request):
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
            stream = make_async_iterator([value.content])
        except RequestNotRead:
            stream = cast(AsyncIterator[bytes], value.stream)

        return Request(
            method=value.method,
            url=str(value.url),
            headers=headers,
            stream=stream,
            metadata=headers_metadata,
        )
    elif isinstance(value, httpx.Response):
        stream = (
            make_async_iterator([value.content]) if value.is_stream_consumed else value.aiter_raw(chunk_size=CHUNK_SIZE)
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


class _IteratorStream(httpx.SyncByteStream, httpx.AsyncByteStream):
    def __init__(self, iterator: Iterator[bytes] | AsyncIterator[bytes]) -> None:
        self.iterator = iterator

    async def __aiter__(self) -> AsyncIterator[bytes]:
        assert isinstance(self.iterator, (AsyncIterator, AsyncIterable))
        async for chunk in self.iterator:
            yield chunk


class AsyncCacheTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        next_transport: httpx.AsyncBaseTransport,
        storage: AsyncBaseStorage | None = None,
        policy: CachePolicy | None = None,
    ) -> None:
        self.next_transport = next_transport
        self._cache_proxy: AsyncCacheProxy = AsyncCacheProxy(
            request_sender=self.request_sender,
            storage=storage,
            policy=policy,
        )
        self.storage = self._cache_proxy.storage

    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        internal_request = _httpx_to_internal(request)
        internal_response = await self._cache_proxy.handle_request(internal_request)
        response = _internal_to_httpx(internal_response)
        return response

    async def aclose(self) -> None:
        await self.next_transport.aclose()
        await self.storage.close()
        await super().aclose()

    async def request_sender(self, request: Request) -> Response:
        httpx_request = _internal_to_httpx(request)
        httpx_response = await self.next_transport.handle_async_request(httpx_request)
        if httpx_response.status_code == 304:
            # 304 should not have a body, but we read it to ensure we'll not let the stream unconsumed
            await httpx_response.aread()
        return _httpx_to_internal(httpx_response)


class AsyncCacheClient(httpx.AsyncClient):
    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        self.storage: AsyncBaseStorage | None = kwargs.pop("storage", None)
        self.policy: CachePolicy | None = kwargs.pop("policy", None)
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
            policy=self.policy,
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
            policy=self.policy,
        )
