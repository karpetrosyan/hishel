import logging
import ssl
import typing as tp

from httpcore import AsyncConnectionPool
from httpcore._backends.base import SOCKET_OPTION, AsyncNetworkBackend
from httpcore._models import Request, Response

from .._controller import Controller
from .._serializers import PickleSerializer
from .._utils import generate_key
from ._storages import AsyncBaseStorage, AsyncFileStorage

logger = logging.getLogger('hishel.pool')

class AsyncCacheConnectionPool(AsyncConnectionPool):

    def __init__(self,
                 ssl_context: tp.Optional[ssl.SSLContext] = None,
                 max_connections: tp.Optional[int] = 10,
                 max_keepalive_connections: tp.Optional[int] = None,
                 keepalive_expiry: tp.Optional[float] = None,
                 http1: bool = True,
                 http2: bool = False,
                 retries: int = 0,
                 local_address: tp.Optional[str] = None,
                 uds: tp.Optional[str] = None,
                 network_backend: tp.Optional[AsyncNetworkBackend] = None,
                 socket_options: tp.Optional[tp.Iterable[SOCKET_OPTION]] = None,
                 storage: tp.Optional[AsyncBaseStorage] = None,
                 cache_controller: tp.Optional[Controller] = None) -> None:
        super().__init__(ssl_context,
                         max_connections,
                         max_keepalive_connections,
                         keepalive_expiry,
                         http1,
                         http2,
                         retries,
                         local_address,
                         uds,
                         network_backend,
                         socket_options
                         )

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
            logger.debug("A response to this request was found.")
            res = self._controller.construct_response_from_cache(request=request, response=stored_resposne)

            if isinstance(res, Response):
                logger.debug(f"Using cached response for the {request.url}")
                return res
            elif isinstance(res, Request):
                response = await super().handle_async_request(res)
                await response.aread()
                updated_response = self._controller.handle_validation_response(
                    old_response=stored_resposne, new_response=response)
                await self._storage.store(key, updated_response)
                return updated_response
            assert False, "invalid return value for `construct_response_from_cache`"
        logger.debug("A response to this request was not found.")
        response = await super().handle_async_request(request)
        await response.aread()

        if self._controller.is_cachable(request=request, response=response):
            await self._storage.store(key, response)
        else:
            logger.debug("ignoring the response because it cannot be cached")

        return response
