from __future__ import annotations

import hashlib
import http.client
import math
from io import RawIOBase
from typing import Callable, Iterator, Mapping

from hishel import CacheOptions, Headers, Request, Response, SyncBaseStorage, SyncSqliteStorage
from hishel._sync_rfc import handle_request_with_rfc

try:
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3 import HTTPHeaderDict, HTTPResponse
    from urllib3.util.retry import Retry
except ImportError as e:
    raise ImportError(
        "requests is required to use hishel.requests module. "
        "Please install hishel with the 'requests' extra, "
        "e.g., 'pip install hishel[requests]'."
    ) from e


CACHEABLE_METHODS = frozenset({"GET", "HEAD"})

TTL_HEADER = "X-Hishel-Ttl"
TTI_HEADER = "X-Hishel-Tti"
KEY_HEADER = "X-Hishel-Key"


class _IteratorStream(RawIOBase):
    """Reads an iterator like a file, which is what urllib3 expects a body to be."""

    def __init__(self, iterator: Iterator[bytes], upstream: requests.Response | None) -> None:
        self.iterator = iterator
        self.upstream = upstream
        self.leftover = b""

    def readable(self) -> bool:
        return True

    def read(self, size: int | None = -1) -> bytes:
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

    def close(self) -> None:
        # Closing the iterator discards a partial save, but it doesn't reach the
        # iterator it was reading from, so the upstream response is closed here.
        if not self.closed:
            if hasattr(self.iterator, "close"):
                self.iterator.close()
            if self.upstream is not None:
                self.upstream.close()
        super().close()


def _seconds_from_header(request: requests.PreparedRequest, name: str) -> float | None:
    value = request.headers.get(name)
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        seconds = math.nan
    # Written this way so that nan fails as well.
    if not 0 <= seconds < math.inf:
        raise ValueError(f"{name} must be a number of seconds, got {value!r}.")
    return seconds


def _key_from_header(request: requests.PreparedRequest) -> str | None:
    value = request.headers.get(KEY_HEADER)
    if value is None:
        return None
    if not value:
        raise ValueError(f"{KEY_HEADER} must not be empty.")
    return value.decode("latin-1") if isinstance(value, bytes) else value


def _request_to_internal(request: requests.PreparedRequest) -> Request:
    assert request.method
    headers = {
        # Requests allows bytes as header values.
        key.lower(): value.decode("latin-1") if isinstance(value, bytes) else value
        for key, value in request.headers.items()
    }
    return Request(method=request.method, url=str(request.url), headers=Headers(headers))


def _response_to_internal(response: requests.Response) -> Response:
    # The headers of the raw response, because the ones on the response join repeated values with commas.
    raw_headers = response.raw.headers
    headers = {key.lower(): raw_headers.getlist(key) for key in raw_headers}
    # The body is stored without its transfer encoding.
    headers.pop("transfer-encoding", None)
    return Response(
        status_code=response.status_code,
        headers=Headers(headers),
        stream=response.raw.stream(decode_content=False),
    )


class CacheAdapter(HTTPAdapter):
    """
    By default, caches successful GET and HEAD responses by method and URL, ignoring
    HTTP caching headers, and serves an entry until the storage's TTL or TTI expires
    it. With ``rfc=True`` or ``CacheOptions``, follows RFC 9111 instead.

    The ``X-Hishel-Ttl`` and ``X-Hishel-Tti`` request headers override the storage's
    TTL and TTI for a response being stored, and ``X-Hishel-Key`` overrides the cache
    key. None of them are sent to the server.
    """

    def __init__(
        self,
        pool_connections: int = 10,
        pool_maxsize: int = 10,
        max_retries: int | Retry = 0,
        pool_block: bool = False,
        storage: SyncBaseStorage | None = None,
        rfc: bool | CacheOptions = False,
    ) -> None:
        super().__init__(pool_connections, pool_maxsize, max_retries, pool_block)
        self.storage = storage or SyncSqliteStorage()
        self.rfc = rfc

    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: None | float | tuple[float, float] | tuple[float, None] = None,
        verify: bool | str = True,
        cert: None | bytes | str | tuple[bytes | str, bytes | str] = None,
        proxies: Mapping[str, str] | None = None,
    ) -> requests.Response:
        def send_upstream(prepared: requests.PreparedRequest) -> requests.Response:
            # Always streamed, because Session.send is what reads the body when the caller didn't ask to stream.
            return super(CacheAdapter, self).send(
                prepared, stream=True, timeout=timeout, verify=verify, cert=cert, proxies=proxies
            )

        ttl = _seconds_from_header(request, TTL_HEADER)
        tti = _seconds_from_header(request, TTI_HEADER)
        key = _key_from_header(request)
        if ttl is not None or tti is not None or key is not None:
            # A copy, so that the caller's request keeps its headers.
            request = request.copy()
            request.headers.pop(TTL_HEADER, None)
            request.headers.pop(TTI_HEADER, None)
            request.headers.pop(KEY_HEADER, None)

        if key is None:
            # In RFC mode, all methods share a key, so that an unsafe request finds the entries it invalidates.
            # The prefix keeps it apart from the key 1.x used, which Redis may still hold in another format.
            identity = f"RFC {request.url}" if self.rfc is not False else f"{request.method} {request.url}"
            key = hashlib.sha256(identity.encode()).hexdigest()
        if self.rfc is False:
            return self._send_without_rfc(request, send_upstream, key, ttl, tti)
        options = CacheOptions() if self.rfc is True else self.rfc
        return self._send_with_rfc(request, send_upstream, key, options, ttl, tti)

    def _send_with_rfc(
        self,
        request: requests.PreparedRequest,
        send_upstream: Callable[[requests.PreparedRequest], requests.Response],
        key: str,
        options: CacheOptions,
        ttl: float | None,
        tti: float | None,
    ) -> requests.Response:
        upstream: requests.Response | None = None

        internal_request = _request_to_internal(request)

        def send(state_request: Request) -> Response:
            nonlocal upstream
            # A copy of the original request is what gets sent, so that nothing about
            # it is lost. The state machine only changes it to add revalidation
            # headers, and those are only for this send, so the caller never sees them.
            prepared = request.copy()
            for name, value in state_request.headers.items():
                if internal_request.headers.get(name) != value:
                    prepared.headers[name] = value

            response = send_upstream(prepared)
            if response.status_code == 304:
                # The body served will be the cached one, so this connection is done.
                response.raw.read()
            else:
                upstream = response
            return _response_to_internal(response)

        response = handle_request_with_rfc(internal_request, send, self.storage, key, options, ttl=ttl, tti=tti)
        return self._response_to_requests(request, response, upstream)

    def _send_without_rfc(
        self,
        request: requests.PreparedRequest,
        send_upstream: Callable[[requests.PreparedRequest], requests.Response],
        key: str,
        ttl: float | None,
        tti: float | None,
    ) -> requests.Response:
        if request.method not in CACHEABLE_METHODS:
            return send_upstream(request)

        # A custom key can be shared by GET and HEAD, whose responses aren't interchangeable.
        entries = [entry for entry in self.storage.get_entries(key) if entry.request.method == request.method]
        if entries:
            return self._response_to_requests(request, entries[0].response)

        response = send_upstream(request)
        # A 206 only holds part of the body, so it can't answer later requests.
        if not 200 <= response.status_code < 300 or response.status_code == 206:
            return response

        entry = self.storage.create_entry(
            _request_to_internal(request),
            _response_to_internal(response),
            key,
            ttl=ttl,
            tti=tti,
        )
        return self._response_to_requests(request, entry.response, upstream=response)

    def _response_to_requests(
        self,
        request: requests.PreparedRequest,
        response: Response,
        upstream: requests.Response | None = None,
    ) -> requests.Response:
        assert isinstance(response.stream, Iterator)
        raw = HTTPResponse(
            body=_IteratorStream(response.stream, upstream),
            headers=HTTPHeaderDict(
                [(key, value) for key in response.headers for value in response.headers.get_list(key) or []]
            ),
            status=response.status_code,
            reason=http.client.responses.get(response.status_code),
            preload_content=False,
            decode_content=False,
            # What Requests reads cookies from, for a response that came from the server.
            original_response=upstream.raw._original_response if upstream is not None else None,
            # Without this, the Content-Length of a HEAD response counts as a missing body.
            request_method=request.method,
        )
        return self.build_response(request, raw)

    def close(self) -> None:
        super().close()
        self.storage.close()
