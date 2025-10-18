from __future__ import annotations

import ssl
import typing as t
from typing import AsyncIterator, Iterable, Iterator, Union, overload

import httpx

from hishel import Headers, Request, Response
from hishel._async_cache import AsyncCacheProxy
from hishel._core._base._storages._base import AsyncBaseStorage, SyncBaseStorage
from hishel._core._spec import (
    CacheOptions,
)
from hishel._core.models import AnyIterable
from hishel._sync_cache import SyncCacheProxy

SOCKET_OPTION = t.Union[
    t.Tuple[int, int, int],
    t.Tuple[int, int, t.Union[bytes, bytearray]],
    t.Tuple[int, int, None, int],
]

# 128 KB
CHUNK_SIZE = 131072


class IteratorStream(httpx.SyncByteStream, httpx.AsyncByteStream):
    def __init__(self, iterator: Iterator[bytes] | AsyncIterator[bytes]) -> None:
        self.iterator = iterator

    def __iter__(self) -> Iterator[bytes]:
        assert isinstance(self.iterator, (Iterator))
        yield from self.iterator

    async def __aiter__(self) -> AsyncIterator[bytes]:
        assert isinstance(self.iterator, (AsyncIterator))
        async for chunk in self.iterator:
            yield chunk


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
            stream=IteratorStream(value.stream),
            extensions=value.metadata,
        )
    elif isinstance(value, Response):
        return httpx.Response(
            status_code=value.status_code,
            headers=value.headers,
            stream=IteratorStream(value.stream),
            extensions=value.metadata,
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
    stream: Union[Iterator[bytes], AsyncIterator[bytes]]
    try:
        stream = AnyIterable(value.content)
    except (httpx.RequestNotRead, httpx.ResponseNotRead):
        if isinstance(value, httpx.Response):
            stream = (
                value.iter_raw(chunk_size=CHUNK_SIZE)
                if isinstance(value.stream, Iterable)
                else value.aiter_raw(chunk_size=CHUNK_SIZE)
            )
        else:
            stream = value.stream  # type: ignore
    if isinstance(value, httpx.Request):
        return Request(
            method=value.method,
            url=str(value.url),
            headers=Headers({key: value for key, value in value.headers.items()}),
            stream=stream,
            metadata={
                "hishel_refresh_ttl_on_access": value.extensions.get("hishel_refresh_ttl_on_access"),
                "hishel_ttl": value.extensions.get("hishel_ttl"),
                "hishel_spec_ignore": value.extensions.get("hishel_spec_ignore"),
            },
        )
    elif isinstance(value, httpx.Response):
        return Response(
            status_code=value.status_code,
            headers=Headers({key: value for key, value in value.headers.items()}),
            stream=stream,
            metadata={},
        )


class SyncCacheTransport(httpx.BaseTransport):
    def __init__(
        self,
        next_transport: httpx.BaseTransport,
        storage: SyncBaseStorage | None = None,
        cache_options: CacheOptions | None = None,
        ignore_specification: bool = False,
    ) -> None:
        self.next_transport = next_transport
        self._cache_proxy: SyncCacheProxy = SyncCacheProxy(
            send_request=self.sync_send_request,
            storage=storage,
            cache_options=cache_options,
            ignore_specification=ignore_specification,
        )
        self.storage = self._cache_proxy.storage

    def handle_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        internal_request = httpx_to_internal(request)
        internal_response = self._cache_proxy.handle_request(internal_request)
        response = internal_to_httpx(internal_response)
        return response

    def close(self) -> None:
        self.next_transport.close()
        self.storage.close()
        super().close()

    def sync_send_request(self, request: Request) -> Response:
        httpx_request = internal_to_httpx(request)
        httpx_response = self.next_transport.handle_request(httpx_request)
        return httpx_to_internal(httpx_response)


class SyncCacheClient(httpx.Client):
    @overload
    def __init__(
        self,
        *,
        storage: SyncBaseStorage | None = None,
        cache_options: CacheOptions | None = None,
        **kwargs: t.Any,
    ) -> None: ...
    @overload
    def __init__(
        self,
        *args: t.Any,
        **kwargs: t.Any,
    ) -> None: ...
    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        self.storage: SyncBaseStorage | None = kwargs.pop("storage", None)
        self.cache_options: CacheOptions | None = kwargs.pop("cache_options", None)
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
            cache_options=self.cache_options,
            ignore_specification=False,
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
            cache_options=self.cache_options,
            ignore_specification=False,
        )


class AsyncCacheTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        next_transport: httpx.AsyncBaseTransport,
        storage: AsyncBaseStorage | None = None,
        cache_options: CacheOptions | None = None,
        ignore_specification: bool = False,
    ) -> None:
        self.next_transport = next_transport
        self._cache_proxy: AsyncCacheProxy = AsyncCacheProxy(
            send_request=self.async_send_request,
            storage=storage,
            cache_options=cache_options,
            ignore_specification=ignore_specification,
        )
        self.storage = self._cache_proxy.storage

    async def handle_async_request(
        self,
        request: httpx.Request,
    ) -> httpx.Response:
        internal_request = httpx_to_internal(request)
        internal_response = await self._cache_proxy.handle_request(internal_request)
        response = internal_to_httpx(internal_response)
        return response

    async def aclose(self) -> None:
        await self.next_transport.aclose()
        await self.storage.close()
        await super().aclose()

    async def async_send_request(self, request: Request) -> Response:
        httpx_request = internal_to_httpx(request)
        httpx_response = await self.next_transport.handle_async_request(httpx_request)
        return httpx_to_internal(httpx_response)


class AsyncCacheClient(httpx.AsyncClient):
    def __init__(self, *args: t.Any, **kwargs: t.Any) -> None:
        self.storage: AsyncBaseStorage | None = kwargs.pop("storage", None)
        self.cache_options: CacheOptions | None = kwargs.pop("cache_options", None)
        self.ignore_specification: bool = kwargs.pop("ignore_specification", False)
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
            cache_options=self.cache_options,
            ignore_specification=False,
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
            cache_options=self.cache_options,
            ignore_specification=self.ignore_specification,
        )
