import types
import typing as tp

from httpcore._async.interfaces import AsyncRequestInterface
from httpcore._models import Request, Response

from .._controller import Controller
from .._serializers import JSONSerializer
from .._utils import generate_key
from ._storages import AsyncBaseStorage, AsyncFileStorage

T = tp.TypeVar("T")

__all__ = ("AsyncCacheConnectionPool",)


class AsyncCacheConnectionPool(AsyncRequestInterface):
    def __init__(
        self,
        pool: AsyncRequestInterface,
        storage: tp.Optional[AsyncBaseStorage] = None,
        controller: tp.Optional[Controller] = None,
    ) -> None:
        self._pool = pool
        self._storage = (
            storage
            if storage is not None
            else AsyncFileStorage(serializer=JSONSerializer())
        )
        self._controller = controller if controller is not None else Controller()

    async def handle_async_request(self, request: Request) -> Response:
        key = generate_key(request)
        stored_resposne = await self._storage.retreive(key)

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

                response = await self._pool.handle_async_request(res)

                # Merge headers with the stale response.
                full_response = self._controller.handle_validation_response(
                    old_response=stored_resposne, new_response=response
                )

                await full_response.aread()
                await self._storage.store(key, full_response)
                full_response.extensions["from_cache"] = response.status == 304  # type: ignore[index]
                return full_response

        response = await self._pool.handle_async_request(request)

        if self._controller.is_cachable(request=request, response=response):
            await response.aread()
            await self._storage.store(key, response)

        response.extensions["from_cache"] = False  # type: ignore[index]
        return response

    async def aclose(self) -> None:
        await self._storage.aclose()

    async def __aenter__(self: T) -> T:
        return self

    async def __aexit__(
        self,
        exc_type: tp.Optional[tp.Type[BaseException]] = None,
        exc_value: tp.Optional[BaseException] = None,
        traceback: tp.Optional[types.TracebackType] = None,
    ) -> None:
        await self.aclose()
