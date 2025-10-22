from __future__ import annotations

import typing as t
from typing import AsyncIterator

from hishel import AsyncBaseStorage, CacheOptions, Headers, Request, Response
from hishel._async_cache import AsyncCacheProxy


class ASGIScope(t.TypedDict, total=False):
    """ASGI HTTP scope type."""

    type: str
    asgi: dict[str, str]
    http_version: str
    method: str
    scheme: str
    path: str
    query_string: bytes
    root_path: str
    headers: list[tuple[bytes, bytes]]
    server: tuple[str, int | None] | None
    client: tuple[str, int] | None
    state: dict[str, t.Any]
    extensions: dict[str, t.Any]


Scope = ASGIScope
Receive = t.Callable[[], t.Awaitable[dict[str, t.Any]]]
Send = t.Callable[[dict[str, t.Any]], t.Awaitable[None]]
ASGIApp = t.Callable[[Scope, Receive, Send], t.Awaitable[None]]


async def empty_receive() -> dict[str, t.Any]:
    """Default receive callable that returns an empty message."""
    return {"type": "http.disconnect"}


class ASGICacheMiddleware:
    """
    ASGI middleware that provides HTTP caching capabilities.

    This middleware intercepts HTTP requests and responses, caching them
    according to HTTP caching specifications (RFC 9111) or custom rules.

    The middleware uses async iterators for request and response bodies,
    ensuring memory-efficient streaming without loading entire payloads
    into memory. This is particularly important for large file uploads
    or downloads.

    Args:
        app: The ASGI application to wrap.
        storage: The storage backend to use for caching. Defaults to AsyncSqliteStorage.
        cache_options: Configuration options for caching behavior.
        ignore_specification: If True, bypasses HTTP caching rules and caches all responses.

    Example:
        ```python
        from hishel.asgi import ASGICacheMiddleware
        from hishel import AsyncSqliteStorage, CacheOptions

        # Wrap your ASGI app
        app = ASGICacheMiddleware(
            app=my_asgi_app,
            storage=AsyncSqliteStorage(),
            cache_options=CacheOptions(),
        )
        ```
    """

    def __init__(
        self,
        app: ASGIApp,
        storage: AsyncBaseStorage | None = None,
        cache_options: CacheOptions | None = None,
        ignore_specification: bool = False,
    ) -> None:
        self.app = app
        self._cache_proxy = AsyncCacheProxy(
            send_request=self._send_request_to_app,
            storage=storage,
            cache_options=cache_options,
            ignore_specification=ignore_specification,
        )
        self.storage = self._cache_proxy.storage

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """
        Handle an ASGI request.

        Args:
            scope: The ASGI scope dictionary.
            receive: The ASGI receive callable.
            send: The ASGI send callable.
        """
        # Only handle HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Store original scope and receive for later use
        self._current_scope = scope
        self._current_receive = receive

        # Convert ASGI request to internal Request (using async iterator, not reading into memory)
        request = self._asgi_to_internal_request(scope, receive)

        # Handle request through cache proxy
        response = await self._cache_proxy.handle_request(request)

        # Send the cached or fresh response
        await self._send_internal_response(response, send)

    async def _send_request_to_app(self, request: Request) -> Response:
        """
        Send a request to the wrapped ASGI application and return the response.

        This is the callback used by AsyncCacheProxy to get fresh responses.

        Args:
            request: The internal Request object.

        Returns:
            The internal Response object from the application.
        """
        # Create a buffered receive callable that replays the request body from the stream
        body_iterator = request.aiter_stream()
        body_exhausted = False

        async def receive() -> dict[str, t.Any]:
            nonlocal body_exhausted
            if body_exhausted:
                return {"type": "http.disconnect"}

            try:
                chunk = await body_iterator.__anext__()
                return {
                    "type": "http.request",
                    "body": chunk,
                    "more_body": True,
                }
            except StopAsyncIteration:
                body_exhausted = True
                return {
                    "type": "http.request",
                    "body": b"",
                    "more_body": False,
                }

        # Collect response from the app
        response_started = False
        status_code = 200
        response_headers: list[tuple[bytes, bytes]] = []
        response_body_chunks: list[bytes] = []

        async def send(message: dict[str, t.Any]) -> None:
            nonlocal response_started, status_code, response_headers
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                response_headers = message.get("headers", [])
            elif message["type"] == "http.response.body":
                body_chunk = message.get("body", b"")
                if body_chunk:
                    response_body_chunks.append(body_chunk)

        # Call the wrapped application
        await self.app(self._current_scope, receive, send)

        # Convert to internal Response
        headers_dict = {key.decode("latin1"): value.decode("latin1") for key, value in response_headers}

        async def response_stream() -> AsyncIterator[bytes]:
            for chunk in response_body_chunks:
                yield chunk

        return Response(
            status_code=status_code,
            headers=Headers(headers_dict),
            stream=response_stream(),
            metadata={},
        )

    def _asgi_to_internal_request(self, scope: Scope, receive: Receive) -> Request:
        """
        Convert an ASGI HTTP scope to an internal Request object.

        Args:
            scope: The ASGI scope dictionary.
            receive: The ASGI receive callable.

        Returns:
            The internal Request object.
        """
        # Build URL
        scheme = scope.get("scheme", "http")
        server = scope.get("server", ("localhost", 80))
        host = server[0]
        port = server[1] if server[1] is not None else (443 if scheme == "https" else 80)

        # Add port to host if non-standard
        if (scheme == "http" and port != 80) or (scheme == "https" and port != 443):
            host = f"{host}:{port}"

        path = scope.get("path", "/")
        query_string = scope.get("query_string", b"")
        if query_string:
            path = f"{path}?{query_string.decode('latin1')}"

        url = f"{scheme}://{host}{path}"

        # Extract headers
        headers_dict = {key.decode("latin1"): value.decode("latin1") for key, value in scope.get("headers", [])}

        # Create async iterator for request body that reads from ASGI receive
        async def request_stream() -> AsyncIterator[bytes]:
            while True:
                message = await receive()
                if message["type"] == "http.request":
                    body = message.get("body", b"")
                    if body:
                        yield body
                    if not message.get("more_body", False):
                        break
                elif message["type"] == "http.disconnect":
                    break

        return Request(
            method=scope.get("method", "GET"),
            url=url,
            headers=Headers(headers_dict),
            stream=request_stream(),
            metadata={},
        )

    async def _send_internal_response(self, response: Response, send: Send) -> None:
        """
        Send an internal Response to the ASGI send callable.

        Args:
            response: The internal Response object.
            send: The ASGI send callable.
        """
        # Convert headers to ASGI format
        headers: list[tuple[bytes, bytes]] = [
            (key.encode("latin1"), value.encode("latin1")) for key, value in response.headers.items()
        ]

        # Send response.start
        await send(
            {
                "type": "http.response.start",
                "status": response.status_code,
                "headers": headers,
            }
        )

        # Send response body in chunks
        async for chunk in response.aiter_stream():
            await send(
                {
                    "type": "http.response.body",
                    "body": chunk,
                    "more_body": True,
                }
            )

        # Send final empty chunk to signal end
        await send(
            {
                "type": "http.response.body",
                "body": b"",
                "more_body": False,
            }
        )

    async def aclose(self) -> None:
        """Close the storage backend and release resources."""
        await self.storage.close()
