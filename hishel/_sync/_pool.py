import types
import typing as tp

from httpcore._sync.interfaces import RequestInterface
from httpcore._models import Request, Response

from .._controller import Controller
from .._serializers import JSONSerializer
from .._utils import generate_key
from ._storages import BaseStorage, FileStorage

T = tp.TypeVar("T")

__all__ = ("CacheConnectionPool",)


class CacheConnectionPool(RequestInterface):
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
        key = generate_key(request)
        stored_resposne = self._storage.retreive(key)

        if stored_resposne:
            # Try using the stored response if it was discovered.

            res = self._controller.construct_response_from_cache(
                request=request, response=stored_resposne
            )

            if isinstance(res, Response):
                # Simply use the response if the controller determines it is ready for use.
                res.extensions["from_cache"] = True  # type: ignore[index]
                return res

            if isinstance(res, Request):
                # Re-validating the response.

                response = self._pool.handle_request(res)

                # Merge headers with the stale response.
                full_response = self._controller.handle_validation_response(
                    old_response=stored_resposne, new_response=response
                )

                full_response.read()
                self._storage.store(key, full_response)
                full_response.extensions["from_cache"] = response.status == 304  # type: ignore[index]
                return full_response

        response = self._pool.handle_request(request)

        if self._controller.is_cachable(request=request, response=response):
            response.read()
            self._storage.store(key, response)

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
