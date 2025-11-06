from __future__ import annotations

from io import RawIOBase
from typing import Any, Iterator, Mapping, Optional, overload

from typing_extensions import assert_never

from hishel import Headers, Request, Response as Response
from hishel._core._storages._sync_base import SyncBaseStorage
from hishel._core.models import extract_metadata_from_headers
from hishel._policies import CachePolicy
from hishel._sync_cache import SyncCacheProxy
from hishel._utils import filter_mapping, snake_to_header

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3 import HTTPResponse
    from urllib3.util.retry import Retry as Retry
except ImportError:  # pragma: no cover
    raise ImportError(
        "The 'requests' library is required to use the requests integration. "
        "Install hishel with 'pip install hishel[requests]'."
    )

# 128 KB
CHUNK_SIZE = 131072


class _IteratorStream(RawIOBase):
    def __init__(self, iterator: Iterator[bytes]):
        self.iterator = iterator
        self.leftover = b""

    def readable(self) -> bool:
        return True

    def readinto(self, b: bytearray) -> Optional[int]:  # type: ignore
        chunk = self.read(len(b))
        if not chunk:
            return 0
        n = len(chunk)
        b[:n] = chunk
        return n

    def read(self, size: int = -1) -> bytes:
        if size is None or size < 0:
            result = self.leftover + b"".join(self.iterator)
            self.leftover = b""
            return result

        while len(self.leftover) < size:
            try:
                self.leftover += next(self.iterator)
            except StopIteration:
                break

        result = self.leftover[:size]
        self.leftover = self.leftover[size:]
        return result


@overload
def _requests_to_internal(
    model: requests.models.PreparedRequest,
) -> Request: ...


@overload
def _requests_to_internal(
    model: requests.models.Response,
) -> Response: ...


def _requests_to_internal(
    model: requests.models.PreparedRequest | requests.models.Response,
) -> Request | Response:
    if isinstance(model, requests.models.PreparedRequest):
        body: bytes
        if isinstance(model.body, str):
            body = model.body.encode("utf-8")
        elif isinstance(model.body, bytes):
            body = model.body
        else:
            body = b""
        assert model.method
        return Request(
            method=model.method,
            url=str(model.url),
            headers=Headers(model.headers),
            stream=iter([body]),
            metadata=extract_metadata_from_headers(model.headers),
        )
    elif isinstance(model, requests.models.Response):
        try:
            stream = model.raw.stream(amt=CHUNK_SIZE, decode_content=None)
            headers = Headers(filter_mapping(model.headers, ["transfer-encoding"]))
        except requests.exceptions.StreamConsumedError:
            stream = iter([model.content])
            # If the stream was consumed and we don't know about the original
            # data and its size, fix the Content-Length header and remove
            # Content-Encoding so we can recreate it later properly.
            headers = Headers(filter_mapping(model.headers, ["content-encoding", "transfer-encoding"]))

        return Response(
            status_code=model.status_code,
            headers=headers,
            stream=stream,
        )
    else:
        assert_never(model)
    raise RuntimeError("This line should never be reached, but is here to satisfy type checkers.")


@overload
def _internal_to_requests(model: Request) -> requests.models.PreparedRequest: ...
@overload
def _internal_to_requests(model: Response) -> requests.models.Response: ...
def _internal_to_requests(
    model: Request | Response,
) -> requests.models.Response | requests.models.PreparedRequest:
    if isinstance(model, Response):
        response = requests.models.Response()

        assert isinstance(model.stream, Iterator)
        stream = _IteratorStream(model.stream)

        urllib_response = HTTPResponse(
            body=stream,
            headers={
                **model.headers,
                **{snake_to_header(k): str(v) for k, v in model.metadata.items()},
            },
            status=model.status_code,
            preload_content=False,
            decode_content=False,
        )

        # Set up the response object
        response.raw = urllib_response
        response.status_code = model.status_code
        response.headers.update(model.headers)
        response.headers.update({snake_to_header(k): str(v) for k, v in model.metadata.items()})
        response.url = ""  # Will be set by requests

        return response
    else:
        assert isinstance(model.stream, Iterator)
        request = requests.Request(
            method=model.method,
            url=model.url,
            headers=model.headers,
            data=b"".join(model.stream) if model.stream else None,
        )
        return request.prepare()


class CacheAdapter(HTTPAdapter):
    """
    A custom HTTPAdapter that can be used with requests to capture HTTP interactions
    for snapshot testing.
    """

    def __init__(
        self,
        pool_connections: int = 10,
        pool_maxsize: int = 10,
        max_retries: int = 0,
        pool_block: bool = False,
        storage: SyncBaseStorage | None = None,
        policy: CachePolicy | None = None,
    ):
        super().__init__(pool_connections, pool_maxsize, max_retries, pool_block)
        self._cache_proxy = SyncCacheProxy(
            request_sender=self._send_request,
            storage=storage,
            policy=policy,
        )
        self.storage = self._cache_proxy.storage

    def send(
        self,
        request: requests.models.PreparedRequest,
        stream: bool = False,
        timeout: None | float | tuple[float, float] | tuple[float, None] = None,
        verify: bool | str = True,
        cert: None | bytes | str | tuple[bytes | str, bytes | str] = None,
        proxies: Mapping[str, str] | None = None,
    ) -> requests.models.Response:
        internal_request = _requests_to_internal(request)
        internal_response = self._cache_proxy.handle_request(internal_request)
        response = _internal_to_requests(internal_response)

        # Set the original request on the response
        response.request = request
        response.connection = self  # type: ignore

        return response

    def _send_request(self, request: Request) -> Response:
        requests_request = _internal_to_requests(request)
        response = super().send(
            requests_request,
            stream=True,
        )
        return _requests_to_internal(response)

    def close(self) -> Any:
        self.storage.close()
