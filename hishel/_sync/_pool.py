import logging
import ssl
import typing as tp

from httpcore import ConnectionPool
from httpcore._backends.base import SOCKET_OPTION, NetworkBackend
from httpcore._models import Request, Response

from .._controller import Controller
from .._serializers import PickleSerializer
from .._utils import generate_key
from ._storages import BaseStorage, FileStorage

logger = logging.getLogger('hishel.pool')

class CacheConnectionPool(ConnectionPool):

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
                 network_backend: tp.Optional[NetworkBackend] = None,
                 socket_options: tp.Optional[tp.Iterable[SOCKET_OPTION]] = None,
                 storage: tp.Optional[BaseStorage] = None,
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
            self._storage = FileStorage(serializer=PickleSerializer())

        if cache_controller is not None:
            self._controller = cache_controller
        else:
            self._controller = Controller()

    def handle_request(self, request: Request) -> Response:

        key = generate_key(
            request.method,
            request.url,
            request.headers
        )
        stored_resposne = self._storage.retreive(key)

        if stored_resposne:
            logger.debug("A response to this request was found.")
            res = self._controller.construct_response_from_cache(request=request, response=stored_resposne)

            if isinstance(res, Response):
                logger.debug(f"Using cached response for the {request.url}")
                return res
            elif isinstance(res, Request):
                response = super().handle_request(res)
                response.read()
                updated_response = self._controller.handle_validation_response(
                    old_response=stored_resposne, new_response=response)
                self._storage.store(key, updated_response)
                return updated_response
            assert False, "invalid return value for `construct_response_from_cache`"
        logger.debug("A response to this request was not found.")
        response = super().handle_request(request)
        response.read()

        if self._controller.is_cachable(request=request, response=response):
            self._storage.store(key, response)
        else:
            logger.debug("ignoring the response because it cannot be cached")

        return response
