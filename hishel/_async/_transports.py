import types
import typing as tp

import httpcore
import httpx
from httpx import Request, Response
from httpx._transports.default import AsyncResponseStream

from hishel._utils import generate_key, normalized_url

from .._controller import Controller
from .._serializers import JSONSerializer
from ._storages import AsyncBaseStorage, AsyncFileStorage

if tp.TYPE_CHECKING:  # pragma: no cover
    from typing_extensions import Self

__all__ = ("AsyncCacheTransport",)


class AsyncCacheTransport(httpx.AsyncBaseTransport):
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
        stored_resposne = await self._storage.retreive(key)

        if stored_resposne:
            # Try using the stored response if it was discovered.

            res = self._controller.construct_response_from_cache(
                request=httpcore_request, response=stored_resposne
            )

            if isinstance(res, httpcore.Response):
                # Simply use the response if the controller determines it is ready for use.
                assert isinstance(res.stream, tp.AsyncIterable)
                res.extensions["from_cache"] = True  # type: ignore[index]
                return Response(
                    status_code=res.status,
                    headers=res.headers,
                    stream=AsyncResponseStream(res.stream),
                    extensions=res.extensions,
                )

            if isinstance(res, httpcore.Request):
                # Re-validating the response.
                assert isinstance(res.stream, tp.AsyncIterable)
                revalidation_request = Request(
                    method=res.method,
                    url=normalized_url(res.url),
                    headers=res.headers,
                    stream=AsyncResponseStream(res.stream),
                )
                response = await self._transport.handle_async_request(
                    revalidation_request
                )
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
                await self._storage.store(key, full_response)

                assert isinstance(full_response.stream, tp.AsyncIterable)
                full_response.extensions["from_cache"] = (  # type: ignore[index]
                    httpcore_response.status == 304
                )
                return Response(
                    status_code=full_response.status,
                    headers=full_response.headers,
                    stream=AsyncResponseStream(full_response.stream),
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

        if self._controller.is_cachable(
            request=httpcore_request, response=httpcore_response
        ):
            await httpcore_response.aread()
            await self._storage.store(key, httpcore_response)

        response.extensions["from_cache"] = False  # type: ignore[index]
        return response

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
