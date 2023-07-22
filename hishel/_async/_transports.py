import logging
import typing as tp
from typing import AsyncIterator

import httpcore
import httpx
from httpx._types import AsyncByteStream

from hishel._utils import (
    generate_key,
    normalized_url,
)

from .._controller import Controller
from .._serializers import DictSerializer
from ._storages import AsyncBaseStorage, AsyncFileStorage

logger = logging.getLogger('hishel.transports')

__all__ = (
    "AsyncCacheTransport",
)

async def to_httpx_response(httpcore_response: httpcore.Response) -> httpx.Response:

    response = httpx.Response(
        status_code=httpcore_response.status,
        headers=httpcore_response.headers,
        stream=MockStream(httpcore_response.content),
        extensions=httpcore_response.extensions
    )
    return response

async def to_httpcore_response(httpx_response: httpx.Response) -> httpcore.Response:

    raw_bytes = b''.join([raw_bytes async for raw_bytes in httpx_response.aiter_raw()])
    response = httpcore.Response(
        status=httpx_response.status_code,
        headers=httpx_response.headers.raw,
        content=raw_bytes,
        extensions=httpx_response.extensions
    )
    await response.aread()
    return response

async def to_httpx_request(httpcore_request: httpcore.Request) -> httpx.Request:
    raw_bytes = b''.join([raw_bytes async for raw_bytes in httpcore_request.stream]) #  type: ignore
    return httpx.Request(
        httpcore_request.method,
        normalized_url(httpcore_request.url),
        headers=httpcore_request.headers,
        extensions=httpcore_request.extensions,
        stream=MockStream(raw_bytes)
    )

def to_httpcore_request(httpx_request: httpx.Request) -> httpcore.Request:
    return httpcore.Request(
        httpx_request.method,
        str(httpx_request.url),
        headers=httpx_request.headers.raw,
        content=httpx_request.content,
        extensions=httpx_request.extensions
    )

class MockStream(AsyncByteStream):

    def __init__(self, content: bytes) -> None:
        self.content = content

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield self.content

class AsyncCacheTransport(httpx.AsyncBaseTransport):

    def __init__(self,
                 transport: httpx.AsyncBaseTransport,
                 storage: tp.Optional[AsyncBaseStorage] = None,
                 cache_controller: tp.Optional[Controller] = None) -> None:
        self._transport = transport

        if storage is not None:
            self._storage = storage
        else:
            self._storage = AsyncFileStorage(serializer=DictSerializer())

        if cache_controller is not None:
            self._controller = cache_controller
        else:
            self._controller = Controller()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        httpcore_request = to_httpcore_request(httpx_request=request)
        key = generate_key(
            httpcore_request.method,
            httpcore_request.url,
            httpcore_request.headers
        )
        url = normalized_url(httpcore_request.url)

        stored_resposne = await self._storage.retreive(key)

        if stored_resposne:
            await stored_resposne.aread()
            logger.debug(f"The cached response for the `{url}` url was found.")
            res = self._controller.construct_response_from_cache(request=httpcore_request, response=stored_resposne)

            if isinstance(res, httpcore.Response):
                logger.debug(f"For the `{url}` url, the cached response was used.")
                return await to_httpx_response(res)
            elif isinstance(res, httpcore.Request):
                logger.debug(f"Validating the response associated with the `{url}` url.")
                response = await self._transport.handle_async_request(await to_httpx_request(res))
                updated_response = self._controller.handle_validation_response(
                    old_response=stored_resposne,
                    new_response=await to_httpcore_response(response)
                )
                await self._storage.store(key, updated_response)
                return await to_httpx_response(updated_response)

            assert False, "invalid return value for `construct_response_from_cache`"
        logger.debug(f"A cached response to the url `{url}` was not found.")
        response = await self._transport.handle_async_request(request)

        httpcore_response = await to_httpcore_response(response)
        if self._controller.is_cachable(request=httpcore_request, response=httpcore_response):
            await self._storage.store(key, httpcore_response)
        else:
            logger.debug(f"The response to the `{url}` url is not cacheable.")

        return await to_httpx_response(httpcore_response=httpcore_response)
