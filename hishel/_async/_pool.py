import datetime
import types
import typing as tp

from httpcore._async.interfaces import AsyncRequestInterface
from httpcore._exceptions import ConnectError
from httpcore._models import Request, Response

from .._controller import Controller, allowed_stale
from .._serializers import JSONSerializer, Metadata
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
        stored_data = await self._storage.retreive(key)

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
                await self._storage.store(
                    key=key,
                    request=request,
                    response=stored_resposne,
                    metadata=metadata,
                )
                res.extensions["from_cache"] = True  # type: ignore[index]
                return res

            if isinstance(res, Request):
                # Re-validating the response.

                try:
                    response = await self._pool.handle_async_request(res)
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

                await full_response.aread()
                metadata["number_of_uses"] += response.status == 200
                await self._storage.store(
                    key, response=full_response, request=request, metadata=metadata
                )
                full_response.extensions["from_cache"] = response.status == 304  # type: ignore[index]
                return full_response

        response = await self._pool.handle_async_request(request)

        if self._controller.is_cachable(request=request, response=response):
            await response.aread()
            metadata = Metadata(
                cache_key=key, created_at=datetime.datetime.utcnow(), number_of_uses=0
            )
            await self._storage.store(
                key, response=response, request=request, metadata=metadata
            )

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
