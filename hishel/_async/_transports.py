from __future__ import annotations

import types
import typing as tp

import httpcore
import httpx
from httpx import AsyncByteStream

from hishel._utils import normalized_url

from .._controller import Controller
from .._serializers import JSONSerializer
from ._request_handler import AsyncCacheRequestHandler
from ._storages import AsyncBaseStorage, AsyncFileStorage

if tp.TYPE_CHECKING:  # pragma: no cover
    from typing_extensions import Self

__all__ = ("AsyncCacheTransport",)


HTTPX_EXC_TO_HTTPCORE_EXC = {
    httpx.TimeoutException: httpcore.TimeoutException,
    httpx.ConnectTimeout: httpcore.ConnectTimeout,
    httpx.ReadTimeout: httpcore.ReadTimeout,
    httpx.WriteTimeout: httpcore.WriteTimeout,
    httpx.PoolTimeout: httpcore.PoolTimeout,
    httpx.NetworkError: httpcore.NetworkError,
    httpx.ConnectError: httpcore.ConnectError,
    httpx.ReadError: httpcore.ReadError,
    httpx.WriteError: httpcore.WriteError,
    httpx.ProxyError: httpcore.ProxyError,
    httpx.UnsupportedProtocol: httpcore.UnsupportedProtocol,
    httpx.ProtocolError: httpcore.ProtocolError,
    httpx.LocalProtocolError: httpcore.LocalProtocolError,
    httpx.RemoteProtocolError: httpcore.RemoteProtocolError,
}
# Same thing:
# TODO: Decide.
# HTTPX_EXC_TO_HTTPCORE_EXC = {
#     httpx_exc: httpcore_exc
#     for httpcore_exc, httpx_exc
#     in httpx._transports.HTTPCORE_EXC_MAP.items()
# }


def make_httpcore_exc_from_httpx_exc(httpx_exc: httpx.TransportError) -> Exception:
    httpcore_exc_type = HTTPX_EXC_TO_HTTPCORE_EXC.get(type(httpx_exc))
    if httpcore_exc_type is not None:
        return httpcore_exc_type(httpx_exc)
    return httpx_exc


class AsyncCacheStream(AsyncByteStream):
    def __init__(self, httpcore_stream: tp.AsyncIterable[bytes]):
        self._httpcore_stream = httpcore_stream

    async def __aiter__(self) -> tp.AsyncIterator[bytes]:
        async for part in self._httpcore_stream:
            yield part

    async def aclose(self) -> None:
        if hasattr(self._httpcore_stream, "aclose"):
            await self._httpcore_stream.aclose()


class AsyncCacheTransport(httpx.AsyncBaseTransport):
    """
    An HTTPX Transport that supports HTTP caching.

    :param transport: `Transport` that our class wraps in order to add an HTTP Cache layer on top of
    :type transport: httpx.AsyncBaseTransport
    :param storage: Storage that handles how the responses should be saved., defaults to None
    :type storage: tp.Optional[AsyncBaseStorage], optional
    :param controller: Controller that manages the cache behavior at the specification level, defaults to None
    :type controller: tp.Optional[Controller], optional
    """

    def __init__(
        self,
        transport: httpx.AsyncBaseTransport,
        storage: tp.Optional[AsyncBaseStorage] = None,
        controller: tp.Optional[Controller] = None,
    ) -> None:
        self._transport = transport

        # TODO: Maybe pass storage and controller to the request handler.
        self._storage = storage if storage is not None else AsyncFileStorage(serializer=JSONSerializer())

        if not isinstance(self._storage, AsyncBaseStorage):
            raise TypeError(f"Expected subclass of `AsyncBaseStorage` but got `{storage.__class__.__name__}`")

        self._controller = controller if controller is not None else Controller()

        self._request_handler = AsyncCacheRequestHandler(
            controller=self._controller,
            storage=self._storage,
            base_request_handler=self._handle_async_httpcore_request,
        )

    async def _handle_async_httpcore_request(self, request: httpcore.Request) -> httpcore.Response:
        assert isinstance(request.stream, tp.AsyncIterable)
        httpx_request = httpx.Request(
            method=request.method,
            url=normalized_url(request.url),
            headers=request.headers,
            stream=AsyncCacheStream(request.stream),
            extensions=request.extensions,
        )
        try:
            httpx_response = await self._transport.handle_async_request(httpx_request)
        except httpx.TransportError as exc:
            raise make_httpcore_exc_from_httpx_exc(exc) from exc

        assert isinstance(httpx_response.stream, tp.AsyncIterable)
        httpcore_response = httpcore.Response(
            status=httpx_response.status_code,
            headers=httpx_response.headers.raw,
            content=AsyncCacheStream(httpx_response.stream),
            extensions=httpx_response.extensions,
        )
        return httpcore_response

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        """
        Handles HTTP requests while also implementing HTTP caching.

        :param request: An HTTP request
        :type request: httpx.Request
        :return: An HTTP response
        :rtype: httpx.Response
        """
        httpcore_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        response = await self._request_handler.handle_async_request(httpcore_request)
        assert isinstance(response.stream, tp.AsyncIterable)
        return httpx.Response(
            status_code=response.status,
            headers=response.headers,
            stream=AsyncCacheStream(response.stream),
            extensions=response.extensions,
        )

    async def aclose(self) -> None:
        await self._storage.aclose()
        await self._transport.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: tp.Optional[tp.Type[BaseException]] = None,
        exc_value: tp.Optional[BaseException] = None,
        traceback: tp.Optional[types.TracebackType] = None,
    ) -> None:
        await self.aclose()
