import types
import typing as tp

from httpcore._async.interfaces import AsyncRequestInterface
from httpcore._models import Request, Response

from .._controller import Controller
from .._serializers import JSONSerializer
from ._request_handler import AsyncCacheRequestHandler
from ._storages import AsyncBaseStorage, AsyncFileStorage

T = tp.TypeVar("T")

__all__ = ("AsyncCacheConnectionPool",)


class AsyncCacheConnectionPool(AsyncRequestInterface):
    """An HTTP Core Connection Pool that supports HTTP caching.

    :param pool: `Connection Pool` that our class wraps in order to add an HTTP Cache layer on top of
    :type pool: AsyncRequestInterface
    :param storage: Storage that handles how the responses should be saved., defaults to None
    :type storage: tp.Optional[AsyncBaseStorage], optional
    :param controller: Controller that manages the cache behavior at the specification level, defaults to None
    :type controller: tp.Optional[Controller], optional
    """

    def __init__(
        self,
        pool: AsyncRequestInterface,
        storage: tp.Optional[AsyncBaseStorage] = None,
        controller: tp.Optional[Controller] = None,
    ) -> None:
        self._pool = pool

        self._storage = storage if storage is not None else AsyncFileStorage(serializer=JSONSerializer())

        if not isinstance(self._storage, AsyncBaseStorage):
            raise TypeError(f"Expected subclass of `AsyncBaseStorage` but got `{storage.__class__.__name__}`")

        self._controller = controller if controller is not None else Controller()

        self._request_handler = AsyncCacheRequestHandler(
            controller=self._controller,
            storage=self._storage,
            base_request_handler=self._pool.handle_async_request,
        )

    async def handle_async_request(self, request: Request) -> Response:
        """
        Handles HTTP requests while also implementing HTTP caching.

        :param request: An HTTP request
        :type request: httpcore.Request
        :return: An HTTP response
        :rtype: httpcore.Response
        """
        return await self._request_handler.handle_async_request(request)

    async def aclose(self) -> None:
        await self._storage.aclose()

        if hasattr(self._pool, "aclose"):  # pragma: no cover
            await self._pool.aclose()

    async def __aenter__(self: T) -> T:
        return self

    async def __aexit__(
        self,
        exc_type: tp.Optional[tp.Type[BaseException]] = None,
        exc_value: tp.Optional[BaseException] = None,
        traceback: tp.Optional[types.TracebackType] = None,
    ) -> None:
        await self.aclose()
