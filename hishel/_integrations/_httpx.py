from dataclasses import replace
from typing import Union, overload

import httpx
import lmdb

from hishel._controller import Controller
from hishel._core._sync._storages._lmdb import SyncLmdbStorage
from hishel._core.models import Headers, Request, Response


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
            extra={},
        )
    elif isinstance(value, httpx.Response):
        return Response(
            status_code=value.status_code,
            headers=Headers({key: value for key, value in value.headers.items()}),
            stream=stream,
            extra={},
        )


class CacheTransport(httpx.BaseTransport):
    def __init__(self, transport: httpx.BaseTransport) -> None:
        self._transport = transport
        self.storage = SyncLmdbStorage(lmdb.open("hishel_cache", max_dbs=100))
        self.controller = Controller()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        pairs = self.storage.get_responses(str(request.url))

        cached_pair = pairs[0] if pairs else None
        internal_request = httpx_to_internal(request)

        if cached_pair:
            print("cached")
            assert cached_pair.response

            what_to_do = self.controller.construct_response_from_cache(
                request=internal_request,
                response=cached_pair.response,
                original_request=cached_pair.request,
            )
            print(what_to_do, "what_to_do")

            if isinstance(what_to_do, Request):
                print("revalidating cached response")
                revalidation_response = self._transport.handle_request(internal_to_httpx(what_to_do))

                print("revalidation_response", revalidation_response)
                internal_revalidation_response = httpx_to_internal(revalidation_response)

                modified_response = self.controller.handle_validation_response(
                    old_response=cached_pair.response,
                    new_response=internal_revalidation_response,
                )

                if (
                    self.controller.is_cachable(internal_request, internal_revalidation_response)
                    and internal_revalidation_response.status_code != 304
                ):
                    self.storage.set_pair(
                        cached_pair.id,
                        replace(cached_pair, response=modified_response),
                    )

                return internal_to_httpx(modified_response)
            elif isinstance(what_to_do, Response):
                return internal_to_httpx(what_to_do)
            else:
                print("cache was found but it is not valid anymore")
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
            print("stored")
            internal_response = self.storage.store_response(id, internal_response)

        return internal_to_httpx(internal_response)
