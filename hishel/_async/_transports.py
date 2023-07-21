import logging
import typing as tp

import httpcore
import httpx

from hishel._utils import (
    generate_key,
    normalized_url,
    to_httpcore_request,
    to_httpcore_response,
    to_httpx_request,
    to_httpx_response,
)

from .._controller import Controller
from .._serializers import DictSerializer
from ._storages import AsyncBaseStorage, AsyncFileStorage

logger = logging.getLogger('hishel.transports')

__all__ = (
    "AsyncCacheTransport",
)

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
                return to_httpx_response(res)
            elif isinstance(res, httpcore.Request):
                logger.debug(f"Validating the response associated with the `{url}` url.")
                response = await self._transport.handle_async_request(to_httpx_request(res))
                await response.aread()
                updated_response = self._controller.handle_validation_response(
                    old_response=stored_resposne, new_response=to_httpcore_response(response)
                )
                await self._storage.store(key, updated_response)
                return to_httpx_response(updated_response)

            assert False, "invalid return value for `construct_response_from_cache`"
        logger.debug(f"A cached response to the url `{url}` was not found.")
        response = await self._transport.handle_async_request(request)
        await response.aread()

        httpcore_response = to_httpcore_response(response)
        if self._controller.is_cachable(request=httpcore_request, response=httpcore_response):
            await self._storage.store(key, httpcore_response)
        else:
            logger.debug(f"The response to the `{url}` url is not cacheable.")

        return response
