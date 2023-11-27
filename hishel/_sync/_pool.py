import datetime
import types
import typing as tp

from httpcore._sync.interfaces import RequestInterface
from httpcore._exceptions import ConnectError
from httpcore._models import Request, Response

from .._controller import Controller, allowed_stale
from .._headers import parse_cache_control
from .._serializers import JSONSerializer, Metadata
from .._utils import extract_header_values_decoded, generate_key
from ._storages import BaseStorage, FileStorage

T = tp.TypeVar("T")

__all__ = ("CacheConnectionPool",)


def generate_504() -> Response:
    return Response(status=504)


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
        self._storage = storage if storage is not None else FileStorage(serializer=JSONSerializer())
        self._controller = controller if controller is not None else Controller()

    def handle_request(self, request: Request) -> Response:
        """
        Handles HTTP requests while also implementing HTTP caching.

        :param request: An HTTP request
        :type request: httpcore.Request
        :return: An HTTP response
        :rtype: httpcore.Response
        """

        if request.extensions.get("cache_disabled", False):
            request.headers.extend([(b"cache-control", b"no-cache"), (b"cache-control", b"max-age=0")])

        key = generate_key(request)
        stored_data = self._storage.retreive(key)

        request_cache_control = parse_cache_control(extract_header_values_decoded(request.headers, b"Cache-Control"))

        if request_cache_control.only_if_cached and not stored_data:
            return generate_504()

        if stored_data:
            # Try using the stored response if it was discovered.

            stored_resposne, stored_request, metadata = stored_data

            res = self._controller.construct_response_from_cache(
                request=request,
                response=stored_resposne,
                original_request=stored_request,
            )

            if isinstance(res, Response):
                # Simply use the response if the controller determines it is ready for use.
                metadata["number_of_uses"] += 1
                stored_resposne.read()
                self._storage.store(
                    key=key,
                    request=request,
                    response=stored_resposne,
                    metadata=metadata,
                )
                res.extensions["from_cache"] = True  # type: ignore[index]
                res.extensions["cache_metadata"] = metadata  # type: ignore[index]
                return res

            if request_cache_control.only_if_cached:
                return generate_504()

            if isinstance(res, Request):
                # Re-validating the response.

                try:
                    response = self._pool.handle_request(res)
                except ConnectError:
                    if self._controller._allow_stale and allowed_stale(response=stored_resposne):
                        stored_resposne.extensions["from_cache"] = True  # type: ignore[index]
                        stored_resposne.extensions["cache_metadata"] = metadata  # type: ignore[index]
                        return stored_resposne
                    raise  # pragma: no cover
                # Merge headers with the stale response.
                full_response = self._controller.handle_validation_response(
                    old_response=stored_resposne, new_response=response
                )

                full_response.read()
                metadata["number_of_uses"] += response.status == 304
                self._storage.store(key, response=full_response, request=request, metadata=metadata)
                full_response.extensions["from_cache"] = response.status == 304  # type: ignore[index]
                if full_response.extensions["from_cache"]:
                    full_response.extensions["cache_metadata"] = metadata  # type: ignore[index]
                return full_response

        response = self._pool.handle_request(request)

        if self._controller.is_cachable(request=request, response=response):
            response.read()
            metadata = Metadata(
                cache_key=key, created_at=datetime.datetime.now(datetime.timezone.utc), number_of_uses=0
            )
            self._storage.store(key, response=response, request=request, metadata=metadata)

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
