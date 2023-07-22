import logging
import typing as tp
from typing import Iterator

import httpcore
import httpx
from httpx._types import SyncByteStream

from hishel._utils import (
    generate_key,
    normalized_url,
)

from .._controller import Controller
from .._serializers import DictSerializer
from ._storages import BaseStorage, FileStorage

logger = logging.getLogger('hishel.transports')

__all__ = (
    "CacheTransport",
)

def to_httpx_response(httpcore_response: httpcore.Response) -> httpx.Response:

    response = httpx.Response(
        status_code=httpcore_response.status,
        headers=httpcore_response.headers,
        stream=MockStream(httpcore_response.content),
        extensions=httpcore_response.extensions
    )
    return response

def to_httpcore_response(httpx_response: httpx.Response) -> httpcore.Response:

    raw_bytes = b''.join([raw_bytes for raw_bytes in httpx_response.iter_raw()])
    response = httpcore.Response(
        status=httpx_response.status_code,
        headers=httpx_response.headers.raw,
        content=raw_bytes,
        extensions=httpx_response.extensions
    )
    response.read()
    return response

def to_httpx_request(httpcore_request: httpcore.Request) -> httpx.Request:
    raw_bytes = b''.join([raw_bytes for raw_bytes in httpcore_request.stream]) #  type: ignore
    return httpx.Request(
        httpcore_request.method,
        normalized_url(httpcore_request.url),
        headers=httpcore_request.headers,
        extensions=httpcore_request.extensions,
        stream=MockStream(raw_bytes)
    )

def to_httpcore_request(httpx_request: httpx.Request) -> httpcore.Request:
    return httpcore.Request(
        httpx_request.method,
        str(httpx_request.url),
        headers=httpx_request.headers.raw,
        content=httpx_request.content,
        extensions=httpx_request.extensions
    )

class MockStream(SyncByteStream):

    def __init__(self, content: bytes) -> None:
        self.content = content

    def __iter__(self) -> Iterator[bytes]:
        yield self.content

class CacheTransport(httpx.BaseTransport):

    def __init__(self,
                 transport: httpx.BaseTransport,
                 storage: tp.Optional[BaseStorage] = None,
                 cache_controller: tp.Optional[Controller] = None) -> None:
        self._transport = transport

        if storage is not None:
            self._storage = storage
        else:
            self._storage = FileStorage(serializer=DictSerializer())

        if cache_controller is not None:
            self._controller = cache_controller
        else:
            self._controller = Controller()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        httpcore_request = to_httpcore_request(httpx_request=request)
        key = generate_key(
            httpcore_request.method,
            httpcore_request.url,
            httpcore_request.headers
        )
        url = normalized_url(httpcore_request.url)

        stored_resposne = self._storage.retreive(key)

        if stored_resposne:
            stored_resposne.read()
            logger.debug(f"The cached response for the `{url}` url was found.")
            res = self._controller.construct_response_from_cache(request=httpcore_request, response=stored_resposne)

            if isinstance(res, httpcore.Response):
                logger.debug(f"For the `{url}` url, the cached response was used.")
                return to_httpx_response(res)
            elif isinstance(res, httpcore.Request):
                logger.debug(f"Validating the response associated with the `{url}` url.")
                response = self._transport.handle_request(to_httpx_request(res))
                updated_response = self._controller.handle_validation_response(
                    old_response=stored_resposne,
                    new_response=to_httpcore_response(response)
                )
                self._storage.store(key, updated_response)
                return to_httpx_response(updated_response)

            assert False, "invalid return value for `construct_response_from_cache`"
        logger.debug(f"A cached response to the url `{url}` was not found.")
        response = self._transport.handle_request(request)

        httpcore_response = to_httpcore_response(response)
        if self._controller.is_cachable(request=httpcore_request, response=httpcore_response):
            self._storage.store(key, httpcore_response)
        else:
            logger.debug(f"The response to the `{url}` url is not cacheable.")

        return to_httpx_response(httpcore_response=httpcore_response)
