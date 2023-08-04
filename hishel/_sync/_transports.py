import types
import typing as tp

import httpcore
import httpx
from httpx import Request, Response
from httpx._exceptions import ConnectError
from httpx._transports.default import ResponseStream

from hishel._utils import generate_key, normalized_url

from .._controller import Controller, allowed_stale
from .._serializers import JSONSerializer
from ._storages import BaseStorage, FileStorage

if tp.TYPE_CHECKING:  # pragma: no cover
    from typing_extensions import Self

__all__ = ("CacheTransport",)


def fake_stream(content: bytes) -> tp.Iterable[bytes]:
    yield content


class CacheTransport(httpx.BaseTransport):
    """
    An HTTPX Transport that supports HTTP caching.

    :param transport: `Transport` that our class wraps in order to add an HTTP Cache layer on top of
    :type transport: httpx.BaseTransport
    :param storage: Storage that handles how the responses should be saved., defaults to None
    :type storage: tp.Optional[BaseStorage], optional
    :param controller: Controller that manages the cache behavior at the specification level, defaults to None
    :type controller: tp.Optional[Controller], optional
    """

    def __init__(
        self,
        transport: httpx.BaseTransport,
        storage: tp.Optional[BaseStorage] = None,
        controller: tp.Optional[Controller] = None,
    ) -> None:
        self._transport = transport
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
        :type request: httpx.Request
        :return: An HTTP response
        :rtype: httpx.Response
        """
        httpcore_request = httpcore.Request(
            method=request.method,
            url=httpcore.URL(
                scheme=request.url.raw_scheme,
                host=request.url.raw_host,
                port=request.url.port,
                target=request.url.raw_path,
            ),
            headers=request.headers.raw,
            content=request.stream,
            extensions=request.extensions,
        )
        key = generate_key(httpcore_request)
        stored_data = self._storage.retreive(key)

        if stored_data:
            # Try using the stored response if it was discovered.

            stored_resposne, stored_request = stored_data

            res = self._controller.construct_response_from_cache(
                request=httpcore_request,
                response=stored_resposne,
                original_request=stored_request,
            )

            if isinstance(res, httpcore.Response):
                # Simply use the response if the controller determines it is ready for use.
                assert isinstance(res.stream, tp.Iterable)
                res.extensions["from_cache"] = True  # type: ignore[index]
                return Response(
                    status_code=res.status,
                    headers=res.headers,
                    stream=ResponseStream(res.stream),
                    extensions=res.extensions,
                )

            if isinstance(res, httpcore.Request):
                # Re-validating the response.
                assert isinstance(res.stream, tp.Iterable)
                revalidation_request = Request(
                    method=res.method,
                    url=normalized_url(res.url),
                    headers=res.headers,
                    stream=ResponseStream(res.stream),
                )
                try:
                    response = self._transport.handle_request(
                        revalidation_request
                    )
                except ConnectError:
                    if self._controller._allow_stale and allowed_stale(
                        response=stored_resposne
                    ):
                        stored_resposne.read()
                        stored_resposne.extensions["from_cache"] = True  # type: ignore[index]
                        return Response(
                            status_code=stored_resposne.status,
                            headers=stored_resposne.headers,
                            stream=ResponseStream(
                                fake_stream(stored_resposne.content)
                            ),
                            extensions=stored_resposne.extensions,
                        )
                    raise  # pragma: no cover
                assert isinstance(response.stream, tp.Iterable)
                httpcore_response = httpcore.Response(
                    status=response.status_code,
                    headers=response.headers.raw,
                    content=ResponseStream(response.stream),
                    extensions=response.extensions,
                )

                # Merge headers with the stale response.
                full_response = self._controller.handle_validation_response(
                    old_response=stored_resposne, new_response=httpcore_response
                )

                full_response.read()
                self._storage.store(
                    key, response=full_response, request=httpcore_request
                )

                assert isinstance(full_response.stream, tp.Iterable)
                full_response.extensions["from_cache"] = (  # type: ignore[index]
                    httpcore_response.status == 304
                )
                return Response(
                    status_code=full_response.status,
                    headers=full_response.headers,
                    stream=ResponseStream(fake_stream(full_response.content)),
                    extensions=full_response.extensions,
                )

        response = self._transport.handle_request(request)
        assert isinstance(response.stream, tp.Iterable)
        httpcore_response = httpcore.Response(
            status=response.status_code,
            headers=response.headers.raw,
            content=ResponseStream(response.stream),
            extensions=response.extensions,
        )
        httpcore_response.read()

        if self._controller.is_cachable(
            request=httpcore_request, response=httpcore_response
        ):
            self._storage.store(
                key, response=httpcore_response, request=httpcore_request
            )

        response.extensions["from_cache"] = False  # type: ignore[index]
        return Response(
            status_code=httpcore_response.status,
            headers=httpcore_response.headers,
            stream=ResponseStream(fake_stream(httpcore_response.content)),
            extensions=httpcore_response.extensions,
        )

    def close(self) -> None:
        self._storage.close()

    def __enter__(self) -> "Self":
        return self

    def __exit__(
        self,
        exc_type: tp.Optional[tp.Type[BaseException]] = None,
        exc_value: tp.Optional[BaseException] = None,
        traceback: tp.Optional[types.TracebackType] = None,
    ) -> None:
        self.close()
