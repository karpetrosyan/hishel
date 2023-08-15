import datetime
import types
import typing as tp

import httpcore
import httpx
from httpx import Request, Response
from httpx._exceptions import ConnectError
from httpx._transports.default import AsyncResponseStream

from hishel._utils import extract_header_values_decoded, generate_key, normalized_url

from .._controller import Controller, allowed_stale
from .._headers import parse_cache_control
from .._serializers import JSONSerializer, Metadata
from ._storages import AsyncBaseStorage, AsyncFileStorage

if tp.TYPE_CHECKING:  # pragma: no cover
    from typing_extensions import Self

__all__ = ("AsyncCacheTransport",)


async def fake_stream(content: bytes) -> tp.AsyncIterable[bytes]:
    yield content


def generate_504() -> Response:
    return Response(status_code=504)


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
        self._storage = (
            storage
            if storage is not None
            else AsyncFileStorage(serializer=JSONSerializer())
        )
        self._controller = controller if controller is not None else Controller()

    async def handle_async_request(self, request: Request) -> Response:
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
        key = generate_key(httpcore_request)
        stored_data = await self._storage.retreive(key)

        request_cache_control = parse_cache_control(
            extract_header_values_decoded(request.headers.raw, b"Cache-Control")
        )

        if request_cache_control.only_if_cached and not stored_data:
            return generate_504()

        if stored_data:
            # Try using the stored response if it was discovered.

            stored_resposne, stored_request, metadata = stored_data

            res = self._controller.construct_response_from_cache(
                request=httpcore_request,
                response=stored_resposne,
                original_request=stored_request,
            )

            if isinstance(res, httpcore.Response):
                # Simply use the response if the controller determines it is ready for use.
                metadata["number_of_uses"] += 1
                stored_resposne.read()
                await self._storage.store(
                    key=key,
                    request=stored_request,
                    response=stored_resposne,
                    metadata=metadata,
                )
                res.extensions["from_cache"] = True  # type: ignore[index]
                return Response(
                    status_code=res.status,
                    headers=res.headers,
                    stream=AsyncResponseStream(fake_stream(stored_resposne.content)),
                    extensions=res.extensions,
                )

            if request_cache_control.only_if_cached:
                return generate_504()

            if isinstance(res, httpcore.Request):
                # Re-validating the response.
                assert isinstance(res.stream, tp.AsyncIterable)
                revalidation_request = Request(
                    method=res.method,
                    url=normalized_url(res.url),
                    headers=res.headers,
                    stream=AsyncResponseStream(res.stream),
                )
                try:
                    response = await self._transport.handle_async_request(
                        revalidation_request
                    )
                except ConnectError:
                    if self._controller._allow_stale and allowed_stale(
                        response=stored_resposne
                    ):
                        await stored_resposne.aread()
                        stored_resposne.extensions["from_cache"] = True  # type: ignore[index]
                        return Response(
                            status_code=stored_resposne.status,
                            headers=stored_resposne.headers,
                            stream=AsyncResponseStream(
                                fake_stream(stored_resposne.content)
                            ),
                            extensions=stored_resposne.extensions,
                        )
                    raise  # pragma: no cover
                assert isinstance(response.stream, tp.AsyncIterable)
                httpcore_response = httpcore.Response(
                    status=response.status_code,
                    headers=response.headers.raw,
                    content=AsyncResponseStream(response.stream),
                    extensions=response.extensions,
                )

                # Merge headers with the stale response.
                full_response = self._controller.handle_validation_response(
                    old_response=stored_resposne, new_response=httpcore_response
                )

                await full_response.aread()
                metadata["number_of_uses"] += response.status_code == 304

                await self._storage.store(
                    key,
                    response=full_response,
                    request=httpcore_request,
                    metadata=metadata,
                )

                assert isinstance(full_response.stream, tp.AsyncIterable)
                full_response.extensions["from_cache"] = (  # type: ignore[index]
                    httpcore_response.status == 304
                )
                return Response(
                    status_code=full_response.status,
                    headers=full_response.headers,
                    stream=AsyncResponseStream(fake_stream(full_response.content)),
                    extensions=full_response.extensions,
                )

        response = await self._transport.handle_async_request(request)
        assert isinstance(response.stream, tp.AsyncIterable)
        httpcore_response = httpcore.Response(
            status=response.status_code,
            headers=response.headers.raw,
            content=AsyncResponseStream(response.stream),
            extensions=response.extensions,
        )
        await httpcore_response.aread()

        if self._controller.is_cachable(
            request=httpcore_request, response=httpcore_response
        ):
            metadata = Metadata(
                cache_key=key, created_at=datetime.datetime.utcnow(), number_of_uses=0
            )
            await self._storage.store(
                key,
                response=httpcore_response,
                request=httpcore_request,
                metadata=metadata,
            )

        response.extensions["from_cache"] = False  # type: ignore[index]
        return Response(
            status_code=httpcore_response.status,
            headers=httpcore_response.headers,
            stream=AsyncResponseStream(fake_stream(httpcore_response.content)),
            extensions=httpcore_response.extensions,
        )

    async def aclose(self) -> None:
        await self._storage.aclose()

    async def __aenter__(self) -> "Self":
        return self

    async def __aexit__(
        self,
        exc_type: tp.Optional[tp.Type[BaseException]] = None,
        exc_value: tp.Optional[BaseException] = None,
        traceback: tp.Optional[types.TracebackType] = None,
    ) -> None:
        await self.aclose()
