import logging
import typing as tp

from httpcore._sync.interfaces import RequestInterface
from httpcore._models import Request, Response

from .._controller import Controller
from .._serializers import DictSerializer
from .._utils import generate_key, normalized_url
from ._storages import BaseStorage, FileStorage

logger = logging.getLogger('hishel.pool')

__all__ = (
    "CacheConnectionPool",
)

class CacheConnectionPool(RequestInterface):

    def __init__(self,
                 pool: RequestInterface,
                 storage: tp.Optional[BaseStorage] = None,
                 cache_controller: tp.Optional[Controller] = None) -> None:
        self._pool = pool

        if storage is not None:  # pragma: no cover
            self._storage = storage
        else:
            self._storage = FileStorage(serializer=DictSerializer())

        if cache_controller is not None:  # pragma: no cover
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

        url = normalized_url(request.url)

        if stored_resposne:
            stored_resposne.read()
            logger.debug(f"The cached response for the `{url}` url was found.")
            res = self._controller.construct_response_from_cache(request=request, response=stored_resposne)

            if isinstance(res, Response):
                logger.debug(f"For the `{url}` url, the cached response was used.")
                return res
            elif isinstance(res, Request):
                logger.debug(f"Validating the response associated with the `{url}` url.")
                response = self._pool.handle_request(res)
                response.read()
                updated_response = self._controller.handle_validation_response(
                    old_response=stored_resposne, new_response=response
                )
                self._storage.store(key, updated_response)
                return updated_response

            assert False, "invalid return value for `construct_response_from_cache`"
        logger.debug(f"A cached response to the url `{url}` was not found.")
        response = self._pool.handle_request(request)
        response.read()

        if self._controller.is_cachable(request=request, response=response):
            self._storage.store(key, response)
        else:  # pragma: no cover
            logger.debug(f"The response to the `{url}` url is not cacheable.")

        return response
