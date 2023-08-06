import types
import typing as tp

from httpcore._sync.interfaces import RequestInterface
from httpcore._exceptions import ConnectError
from httpcore._models import Request, Response

from .._controller import Controller, allowed_stale
from .._serializers import JSONSerializer
from .._utils import generate_key
from ._storages import BaseStorage, FileStorage

T = tp.TypeVar("T")

__all__ = ("CacheConnectionPool",)


class CacheConnectionPool(RequestInterface):
    """An HTTP Core Connection Pool that supports HTTP caching.

    :param pool: `Connection Pool` that our class wraps in order to add an HTTP Cache layer on top of
    :type pool: RequestInterface
    :param storage: Storage that handles how the responses should be saved., defaults to None
    :type storage: tp.Optional[BaseStorage], optional
    :param controller: Controller that manages the cache behavior at the specification level, defaults to None
    :type controller: tp.Optional[Controller], optional
    """

    def __init__(
        self,
        pool: RequestInterface,
        storage: tp.Optional[BaseStorage] = None,
        controller: tp.Optional[Controller] = None,
    ) -> None:
        self._pool = pool
        self._storage = (
            storage
            if storage is not None
            else FileStorage(serializer=JSONSerializer())
        )
        self._controller = controller if controller is not None else Controller()

    def handle_request(self, request: Request) -> Response:
        """
        Handles HTTP requests while also implementing HTTP caching.

        :param request: An HTTP request
        :type request: httpcore.Request
        :return: An HTTP response
        :rtype: httpcore.Response
        """

        key = generate_key(request)
        stored_data = self._storage.retreive(key)

        if stored_data:
            # Try using the stored response if it was discovered.

            stored_resposne, stored_request = stored_data

            res = self._controller.construct_response_from_cache(
                request=request,
                response=stored_resposne,
                original_request=stored_request,
            )

            if isinstance(res, Response):
                # Simply use the response if the controller determines it is ready for use.
                res.extensions["from_cache"] = True  # type: ignore[index]
                return res

            if isinstance(res, Request):
                # Re-validating the response.

                try:
                    response = self._pool.handle_request(res)
                except ConnectError:
                    if self._controller._allow_stale and allowed_stale(
                        response=stored_resposne
                    ):
                        stored_resposne.extensions["from_cache"] = True  # type: ignore[index]
                        return stored_resposne
                    raise  # pragma: no cover
                # Merge headers with the stale response.
                full_response = self._controller.handle_validation_response(
                    old_response=stored_resposne, new_response=response
                )

                full_response.read()
                self._storage.store(key, response=full_response, request=request)
                full_response.extensions["from_cache"] = response.status == 304  # type: ignore[index]
                return full_response

        response = self._pool.handle_request(request)

        if self._controller.is_cachable(request=request, response=response):
            response.read()
            self._storage.store(key, response=response, request=request)

        response.extensions["from_cache"] = False  # type: ignore[index]
        return response

    def close(self) -> None:
        self._storage.close()

    def __enter__(self: T) -> T:
        return self

    def __exit__(
        self,
        exc_type: tp.Optional[tp.Type[BaseException]] = None,
        exc_value: tp.Optional[BaseException] = None,
        traceback: tp.Optional[types.TracebackType] = None,
    ) -> None:
        self.close()
