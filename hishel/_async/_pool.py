import logging
import typing as tp

from httpcore._async.interfaces import AsyncRequestInterface
from httpcore._models import Request, Response

from .._controller import Controller
from .._serializers import PickleSerializer
from .._utils import generate_key
from ._storages import AsyncBaseStorage, AsyncFileStorage

logger = logging.getLogger('hishel.pool')

class AsyncCacheConnectionPool(AsyncRequestInterface):

    def __init__(self,
                 pool: AsyncRequestInterface,
                 storage: tp.Optional[AsyncBaseStorage] = None,
                 cache_controller: tp.Optional[Controller] = None) -> None:
        self._pool = pool

        if storage is not None:
            self._storage = storage
        else:
            self._storage = AsyncFileStorage(serializer=PickleSerializer())

        if cache_controller is not None:
            self._controller = cache_controller
        else:
            self._controller = Controller()

    async def handle_async_request(self, request: Request) -> Response:

        key = generate_key(
            request.method,
            request.url,
            request.headers
        )
        stored_resposne = await self._storage.retreive(key)

        if stored_resposne:
            await stored_resposne.aread()
            logger.debug("A response to this request was found.")
            res = self._controller.construct_response_from_cache(request=request, response=stored_resposne)

            if isinstance(res, Response):
                logger.debug(f"Using cached response for the {request.url}")
                return res
            elif isinstance(res, Request):
                response = await self._pool.handle_async_request(res)
                await response.aread()
                updated_response = self._controller.handle_validation_response(
                    old_response=stored_resposne, new_response=response
                )
                await self._storage.store(key, updated_response)
                return updated_response

            assert False, "invalid return value for `construct_response_from_cache`"
        logger.debug("A response to this request was not found.")
        response = await self._pool.handle_async_request(request)
        await response.aread()

        if self._controller.is_cachable(request=request, response=response):
            await self._storage.store(key, response)
        else:
            logger.debug("ignoring the response because it cannot be cached")

        return response
