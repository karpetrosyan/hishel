# from __future__ import annotations

# import types
# import typing as tp

# import httpcore
from typing import Union, overload

import httpx
import lmdb

from hishel._controller import Controller
from hishel._core._sync._storages._lmdb import SyncLmdbStorage
from hishel._core.models import Headers, Request, Response

# from httpx import AsyncByteStream, Request, Response
# from httpx._exceptions import ConnectError

# from .._controller import Controller, allowed_stale
# from .._headers import parse_cache_control
# from .._serializers import JSONSerializer, Metadata
# from .._utils import extract_header_values_decoded, normalized_url
# from ._storages import AsyncBaseStorage, AsyncFileStorage

# if tp.TYPE_CHECKING:  # pragma: no cover
#     from typing_extensions import Self

# __all__ = ("AsyncCacheTransport",)


# async def fake_stream(content: bytes) -> tp.AsyncIterable[bytes]:
#     yield content


# def generate_504() -> Response:
#     return Response(status_code=504)


# class AsyncCacheStream(AsyncByteStream):
#     def __init__(self, httpcore_stream: tp.AsyncIterable[bytes]):
#         self._httpcore_stream = httpcore_stream

#     async def __aiter__(self) -> tp.AsyncIterator[bytes]:
#         async for part in self._httpcore_stream:
#             yield part

#     async def aclose(self) -> None:
#         if hasattr(self._httpcore_stream, "aclose"):
#             await self._httpcore_stream.aclose()


# class AsyncCacheTransport(httpx.AsyncBaseTransport):
#     """
#     An HTTPX Transport that supports HTTP caching.

#     :param transport: `Transport` that our class wraps in order to add an HTTP Cache layer on top of
#     :type transport: httpx.AsyncBaseTransport
#     :param storage: Storage that handles how the responses should be saved., defaults to None
#     :type storage: tp.Optional[AsyncBaseStorage], optional
#     :param controller: Controller that manages the cache behavior at the specification level, defaults to None
#     :type controller: tp.Optional[Controller], optional
#     """

#     def __init__(
#         self,
#         transport: httpx.AsyncBaseTransport,
#         storage: tp.Optional[AsyncBaseStorage] = None,
#         controller: tp.Optional[Controller] = None,
#     ) -> None:
#         self._transport = transport

#         self._storage = storage if storage is not None else AsyncFileStorage(serializer=JSONSerializer())

#         if not isinstance(self._storage, AsyncBaseStorage):  # pragma: no cover
#             raise TypeError(f"Expected subclass of `AsyncBaseStorage` but got `{storage.__class__.__name__}`")

#         self._controller = controller if controller is not None else Controller()

#     async def handle_async_request(self, request: Request) -> Response:
#         """
#         Handles HTTP requests while also implementing HTTP caching.

#         :param request: An HTTP request
#         :type request: httpx.Request
#         :return: An HTTP response
#         :rtype: httpx.Response
#         """

#         if request.extensions.get("cache_disabled", False):
#             request.headers.update(
#                 [
#                     ("Cache-Control", "no-store"),
#                     ("Cache-Control", "no-cache"),
#                     *[("cache-control", value) for value in request.headers.get_list("cache-control")],
#                 ]
#             )

#         if request.method not in ["GET", "HEAD"]:
#             # If the HTTP method is, for example, POST,
#             # we must also use the request data to generate the hash.
#             body_for_key = await request.aread()
#             request.stream = AsyncCacheStream(fake_stream(body_for_key))
#         else:
#             body_for_key = b""

#         # Construct the HTTPCore request because Controllers and Storages work with HTTPCore requests.
#         httpcore_request = httpcore.Request(
#             method=request.method,
#             url=httpcore.URL(
#                 scheme=request.url.raw_scheme,
#                 host=request.url.raw_host,
#                 port=request.url.port,
#                 target=request.url.raw_path,
#             ),
#             headers=request.headers.raw,
#             content=request.stream,
#             extensions=request.extensions,
#         )

#         key = self._controller._key_generator(httpcore_request, body_for_key)
#         stored_data = await self._storage.retrieve(key)

#         request_cache_control = parse_cache_control(
#             extract_header_values_decoded(request.headers.raw, b"Cache-Control")
#         )

#         if request_cache_control.only_if_cached and not stored_data:
#             return generate_504()

#         if stored_data:
#             # Try using the stored response if it was discovered.

#             stored_response, stored_request, metadata = stored_data

#             # Immediately read the stored response to avoid issues when trying to access the response body.
#             stored_response.read()

#             res = self._controller.construct_response_from_cache(
#                 request=httpcore_request,
#                 response=stored_response,
#                 original_request=stored_request,
#             )

#             if isinstance(res, httpcore.Response):
#                 # Simply use the response if the controller determines it is ready for use.
#                 return await self._create_hishel_response(
#                     key=key,
#                     response=res,
#                     request=httpcore_request,
#                     cached=True,
#                     revalidated=False,
#                     metadata=metadata,
#                 )

#             if request_cache_control.only_if_cached:
#                 return generate_504()

#             if isinstance(res, httpcore.Request):
#                 # Controller has determined that the response needs to be re-validated.
#                 assert isinstance(res.stream, tp.AsyncIterable)
#                 revalidation_request = Request(
#                     method=res.method.decode(),
#                     url=normalized_url(res.url),
#                     headers=res.headers,
#                     stream=AsyncCacheStream(res.stream),
#                     extensions=res.extensions,
#                 )
#                 try:
#                     revalidation_response = await self._transport.handle_async_request(revalidation_request)
#                 except ConnectError:
#                     # If there is a connection error, we can use the stale response if allowed.
#                     if self._controller._allow_stale and allowed_stale(response=stored_response):
#                         return await self._create_hishel_response(
#                             key=key,
#                             response=stored_response,
#                             request=httpcore_request,
#                             cached=True,
#                             revalidated=False,
#                             metadata=metadata,
#                         )
#                     raise  # pragma: no cover
#                 assert isinstance(revalidation_response.stream, tp.AsyncIterable)
#                 httpcore_revalidation_response = httpcore.Response(
#                     status=revalidation_response.status_code,
#                     headers=revalidation_response.headers.raw,
#                     content=AsyncCacheStream(revalidation_response.stream),
#                     extensions=revalidation_response.extensions,
#                 )

#                 # Merge headers with the stale response.
#                 final_httpcore_response = self._controller.handle_validation_response(
#                     old_response=stored_response,
#                     new_response=httpcore_revalidation_response,
#                 )

#                 await final_httpcore_response.aread()
#                 await revalidation_response.aclose()

#                 assert isinstance(final_httpcore_response.stream, tp.AsyncIterable)

#                 # RFC 9111: 4.3.3. Handling a Validation Response
#                 # A 304 (Not Modified) response status code indicates that the stored response can be updated and
#                 # reused. A full response (i.e., one containing content) indicates that none of the stored responses
#                 # nominated in the conditional request are suitable. Instead, the cache MUST use the full response to
#                 # satisfy the request. The cache MAY store such a full response, subject to its constraints.
#                 if revalidation_response.status_code != 304 and self._controller.is_cachable(
#                     request=httpcore_request, response=final_httpcore_response
#                 ):
#                     await self._storage.store(key, response=final_httpcore_response, request=httpcore_request)

#                 return await self._create_hishel_response(
#                     key=key,
#                     response=final_httpcore_response,
#                     request=httpcore_request,
#                     cached=revalidation_response.status_code == 304,
#                     revalidated=True,
#                     metadata=metadata,
#                 )

#         regular_response = await self._transport.handle_async_request(request)
#         assert isinstance(regular_response.stream, tp.AsyncIterable)
#         httpcore_regular_response = httpcore.Response(
#             status=regular_response.status_code,
#             headers=regular_response.headers.raw,
#             content=AsyncCacheStream(regular_response.stream),
#             extensions=regular_response.extensions,
#         )
#         await httpcore_regular_response.aread()
#         await httpcore_regular_response.aclose()

#         if self._controller.is_cachable(request=httpcore_request, response=httpcore_regular_response):
#             await self._storage.store(
#                 key,
#                 response=httpcore_regular_response,
#                 request=httpcore_request,
#             )

#         return await self._create_hishel_response(
#             key=key,
#             response=httpcore_regular_response,
#             request=httpcore_request,
#             cached=False,
#             revalidated=False,
#         )

#     async def _create_hishel_response(
#         self,
#         key: str,
#         response: httpcore.Response,
#         request: httpcore.Request,
#         cached: bool,
#         revalidated: bool,
#         metadata: Metadata | None = None,
#     ) -> Response:
#         if cached:
#             assert metadata
#             metadata["number_of_uses"] += 1
#             await self._storage.update_metadata(key=key, request=request, response=response, metadata=metadata)
#             response.extensions["from_cache"] = True  # type: ignore[index]
#             response.extensions["cache_metadata"] = metadata  # type: ignore[index]
#         else:
#             response.extensions["from_cache"] = False  # type: ignore[index]
#         response.extensions["revalidated"] = revalidated  # type: ignore[index]
#         return Response(
#             status_code=response.status,
#             headers=response.headers,
#             stream=AsyncCacheStream(fake_stream(response.content)),
#             extensions=response.extensions,
#         )

#     async def aclose(self) -> None:
#         await self._storage.aclose()
#         await self._transport.aclose()

#     async def __aenter__(self) -> Self:
#         return self

#     async def __aexit__(
#         self,
#         exc_type: tp.Optional[tp.Type[BaseException]] = None,
#         exc_value: tp.Optional[BaseException] = None,
#         traceback: tp.Optional[types.TracebackType] = None,
#     ) -> None:
#         await self.aclose()


# class AsyncCacheClient(httpx.AsyncClient):
#     def __init__(self, *args: tp.Any, **kwargs: tp.Any):
#         self._storage = kwargs.pop("storage") if "storage" in kwargs else None
#         self._controller = kwargs.pop("controller") if "controller" in kwargs else None
#         super().__init__(*args, **kwargs)

#     def _init_transport(self, *args, **kwargs) -> AsyncCacheTransport:  # type: ignore
#         _transport = super()._init_transport(*args, **kwargs)
#         return AsyncCacheTransport(
#             transport=_transport,
#             storage=self._storage,
#             controller=self._controller,
#         )

#     def _init_proxy_transport(self, *args, **kwargs) -> AsyncCacheTransport:  # type: ignore
#         _transport = super()._init_proxy_transport(*args, **kwargs)  # pragma: no cover
#         return AsyncCacheTransport(  # pragma: no cover
#             transport=_transport,
#             storage=self._storage,
#             controller=self._controller,
#         )


@overload
def internal_to_httpx(
    value: Request,
) -> httpx.Request: ...


@overload
def internal_to_httpx(
    value: Response,
) -> httpx.Response: ...


def internal_to_httpx(
    value: Union[Request, Response],
) -> Union[httpx.Request, httpx.Response]:
    if isinstance(value, Request):
        return httpx.Request(
            method=value.method,
            url=value.url,
            headers=value.headers,
            content=value.stream,
            extensions=value.extra,
        )
    elif isinstance(value, Response):
        return httpx.Response(
            status_code=value.status_code,
            headers=value.headers,
            content=value.stream,
            extensions=value.extra,
        )


@overload
def httpx_to_internal(
    value: httpx.Request,
) -> Request: ...


@overload
def httpx_to_internal(
    value: httpx.Response,
) -> Response: ...


def httpx_to_internal(
    value: Union[httpx.Request, httpx.Response],
) -> Union[Request, Response]:
    stream: httpx.SyncByteStream | httpx.AsyncByteStream | httpx.ByteStream | list[bytes]
    try:
        stream = [value.content]
    except (httpx.RequestNotRead, httpx.ResponseNotRead):
        stream = value.stream
    if isinstance(value, httpx.Request):
        return Request(
            method=value.method,
            url=str(value.url),
            headers=Headers({key: value for key, value in value.headers.items()}),
            stream=stream,
            extra=value.extensions,
        )
    elif isinstance(value, httpx.Response):
        return Response(
            status_code=value.status_code,
            headers=Headers({key: value for key, value in value.headers.items()}),
            stream=stream,
            extra=value.extensions,
        )


class CacheTransport(httpx.BaseTransport):
    def __init__(self, transport: httpx.BaseTransport) -> None:
        self._transport = transport
        self.storage = SyncLmdbStorage(lmdb.open("hishel_cache", max_dbs=100))
        self.controller = Controller()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        pair = self.storage.get_responses(str(request.url))

        cached_response = pair[0] if pair else None
        internal_request = httpx_to_internal(request)

        if cached_response:
            print("cached")
            assert cached_response.response

            what_to_do = self.controller.construct_response_from_cache(
                request=internal_request,
                response=cached_response.response,
                original_request=cached_response.request,
            )
            print(what_to_do, "what_to_do")

            if isinstance(what_to_do, Request):
                print("revalidating cached response")
                revalidation_response = self._transport.handle_request(internal_to_httpx(what_to_do))

                print("revalidation_response", revalidation_response)
                internal_revalidation_response = httpx_to_internal(revalidation_response)

                self.controller.handle_validation_response(
                    old_response=cached_response.response,
                    new_response=internal_revalidation_response,
                )

                if (
                    self.controller.is_cachable(internal_request, internal_revalidation_response)
                    and internal_revalidation_response.status_code != 304
                ):
                    self.storage.store_response(
                        cached_response.id,
                        internal_revalidation_response,
                    )

                return internal_to_httpx(internal_revalidation_response)
            elif isinstance(what_to_do, httpx.Response):
                return internal_to_httpx(what_to_do)
        print("not cached")

        id, internal_request = self.storage.store_request(
            str(request.url),
            internal_request,
        )

        remote_response = self._transport.handle_request(
            httpx.Request(
                method=internal_request.method,
                url=internal_request.url,
                headers=internal_request.headers,
                content=internal_request.stream,
                extensions=internal_request.extra,
            )
        )

        internal_response = httpx_to_internal(remote_response)

        if self.controller.is_cachable(internal_request, internal_response):
            print("storing")
            internal_response = self.storage.store_response(id, internal_response)

        return internal_to_httpx(internal_response)
