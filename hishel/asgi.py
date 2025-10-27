from __future__ import annotations

import logging
import typing as t
from email.utils import formatdate
from typing import AsyncIterator

from hishel import AsyncBaseStorage, Headers, Request, Response
from hishel._async_cache import AsyncCacheProxy
from hishel._policies import CachePolicy
from hishel._utils import filter_mapping

# Configure logger for this module
logger = logging.getLogger(__name__)


class _ASGIScope(t.TypedDict, total=False):
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


_Scope = _ASGIScope
_Receive = t.Callable[[], t.Awaitable[dict[str, t.Any]]]
_Send = t.Callable[[dict[str, t.Any]], t.Awaitable[None]]
_ASGIApp = t.Callable[[_Scope, _Receive, _Send], t.Awaitable[None]]


class ASGICacheMiddleware:
    """
    ASGI middleware that provides HTTP caching capabilities.

    This middleware intercepts HTTP requests and responses, caching them
    according to HTTP caching specifications (RFC 9111) or custom rules.

    The middleware uses async iterators for request and response bodies,
    ensuring memory-efficient streaming without loading entire payloads
    into memory. This is particularly important for large file uploads
    or downloads.

    This implementation is thread-safe by creating a new cache proxy for
    each request with closures that capture the request context.

    Args:
        app: The ASGI application to wrap.
        storage: The storage backend to use for caching. Defaults to AsyncSqliteStorage.
        policy: Caching policy to use. Can be SpecificationPolicy (respects RFC 9111) or
            FilterPolicy (user-defined filtering). Defaults to SpecificationPolicy().

    Example:
        ```python
        from hishel.asgi import ASGICacheMiddleware
        from hishel import AsyncSqliteStorage
        from hishel._policies import SpecificationPolicy, CacheOptions

        # Wrap your ASGI app
        app = ASGICacheMiddleware(
            app=my_asgi_app,
            storage=AsyncSqliteStorage(),
            policy=SpecificationPolicy(cache_options=CacheOptions()),
        )
        ```
    """

    def __init__(
        self,
        app: _ASGIApp,
        storage: AsyncBaseStorage | None = None,
        policy: CachePolicy | None = None,
    ) -> None:
        self.app = app
        self.storage = storage
        self._policy = policy

        logger.info(
            "Initialized ASGICacheMiddleware with storage=%s, policy=%s",
            type(storage).__name__ if storage else "None",
            type(policy).__name__ if policy else "None",
        )

    async def __call__(self, scope: _Scope, receive: _Receive, send: _Send) -> None:
        """
        Handle an ASGI request.

        Args:
            scope: The ASGI scope dictionary.
            receive: The ASGI receive callable.
            send: The ASGI send callable.
        """
        # Only handle HTTP requests
        if scope["type"] != "http":
            logger.debug("Skipping non-HTTP request: type=%s", scope["type"])
            await self.app(scope, receive, send)
            return

        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        query_string = scope.get("query_string", b"").decode("latin1")
        full_path = f"{path}?{query_string}" if query_string else path

        logger.debug("Incoming HTTP request: method=%s path=%s", method, full_path)

        try:
            # Create a closure that captures scope and receive for this specific request
            # This makes the code thread-safe by avoiding shared instance state
            async def send_request_to_app(request: Request) -> Response:
                """
                Send a request to the wrapped ASGI application and return the response.
                This closure captures 'scope' and 'receive' from the outer function scope.
                """
                logger.debug("Sending request to wrapped application: url=%s", request.url)

                # Create a buffered receive callable that replays the request body from the stream
                body_iterator = request._aiter_stream()
                body_exhausted = False
                bytes_received = 0

                async def inner_receive() -> dict[str, t.Any]:
                    nonlocal body_exhausted, bytes_received
                    if body_exhausted:
                        return {"type": "http.disconnect"}

                    try:
                        chunk = await body_iterator.__anext__()
                        bytes_received += len(chunk)
                        logger.debug("Received request body chunk: size=%d bytes", len(chunk))
                        return {
                            "type": "http.request",
                            "body": chunk,
                            "more_body": True,
                        }
                    except StopAsyncIteration:
                        body_exhausted = True
                        logger.debug(
                            "Request body fully consumed: total_bytes=%d",
                            bytes_received,
                        )
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
                bytes_sent = 0

                async def inner_send(message: dict[str, t.Any]) -> None:
                    nonlocal response_started, status_code, response_headers, bytes_sent
                    if message["type"] == "http.response.start":
                        response_started = True
                        status_code = message["status"]
                        response_headers = message.get("headers", [])
                        logger.debug("Application response started: status=%d", status_code)
                    elif message["type"] == "http.response.body":
                        body_chunk = message.get("body", b"")
                        if body_chunk:
                            response_body_chunks.append(body_chunk)
                            bytes_sent += len(body_chunk)
                            logger.debug(
                                "Received response body chunk: size=%d bytes",
                                len(body_chunk),
                            )

                try:
                    # Call the wrapped application with captured scope
                    await self.app(scope, inner_receive, inner_send)
                    logger.info(
                        "Application response complete: status=%d total_bytes=%d chunks=%d",
                        status_code,
                        bytes_sent,
                        len(response_body_chunks),
                    )
                except Exception as e:
                    logger.error(
                        "Error calling wrapped application: url=%s error=%s",
                        request.url,
                        str(e),
                        exc_info=True,
                    )
                    raise

                # Convert to internal Response
                headers_dict = {key.decode("latin1"): value.decode("latin1") for key, value in response_headers}

                # Add Date header if not present
                if not any(key.lower() == "date" for key in headers_dict.keys()):
                    date_header = formatdate(timeval=None, localtime=False, usegmt=True)
                    headers_dict["Date"] = date_header
                    logger.debug("Added Date header to response: %s", date_header)

                async def response_stream() -> AsyncIterator[bytes]:
                    for chunk in response_body_chunks:
                        yield chunk

                return Response(
                    status_code=status_code,
                    headers=Headers(filter_mapping(headers_dict, ["Transfer-Encoding"])),
                    stream=response_stream(),
                    metadata={},
                )

            # Create a new cache proxy for this request with the closure
            # This ensures complete isolation between concurrent requests
            cache_proxy = AsyncCacheProxy(
                request_sender=send_request_to_app,
                storage=self.storage,
                policy=self._policy,
            )

            # Convert ASGI request to internal Request (using async iterator, not reading into memory)
            request = self._asgi_to_internal_request(scope, receive)
            logger.debug("Converted ASGI request to internal format: url=%s", request.url)

            # Handle request through cache proxy
            logger.debug("Handling request through cache proxy")
            response = await cache_proxy.handle_request(request)

            logger.info(
                "Request processed: method=%s path=%s status=%d",
                method,
                full_path,
                response.status_code,
            )

            # Send the cached or fresh response
            await self._send_internal_response(response, send)
            logger.debug("Response sent successfully")

        except Exception as e:
            logger.error(
                "Error processing request: method=%s path=%s error=%s",
                method,
                full_path,
                str(e),
                exc_info=True,
            )
            raise

    def _asgi_to_internal_request(self, scope: _Scope, receive: _Receive) -> Request:
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
        server = scope.get("server")

        if server is None:
            server = ("localhost", 80)
            logger.debug("No server info in scope, using default: localhost:80")

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
        method = scope.get("method", "GET")

        # Extract headers
        headers_dict = {key.decode("latin1"): value.decode("latin1") for key, value in scope.get("headers", [])}

        logger.debug(
            "Building internal request: method=%s url=%s headers_count=%d",
            method,
            url,
            len(headers_dict),
        )

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
                    logger.debug("Client disconnected during request body streaming")
                    break

        return Request(
            method=method,
            url=url,
            headers=Headers(headers_dict),
            stream=request_stream(),
            # Metadatas don't make sense in ASGI scope, so we leave it empty
            metadata={},
        )

    async def _send_internal_response(self, response: Response, send: _Send) -> None:
        """
        Send an internal Response to the ASGI send callable.

        Args:
            response: The internal Response object.
            send: The ASGI send callable.
        """
        logger.debug(
            "Sending response to client: status=%d headers_count=%d",
            response.status_code,
            len(response.headers),
        )

        # Convert headers to ASGI format
        headers: list[tuple[bytes, bytes]] = [
            (key.encode("latin1"), value.encode("latin1")) for key, value in response.headers.items()
        ]

        try:
            # Send response.start
            await send(
                {
                    "type": "http.response.start",
                    "status": response.status_code,
                    "headers": headers,
                }
            )
            logger.debug("Response headers sent")

            # Send response body in chunks
            bytes_sent = 0
            chunk_count = 0
            async for chunk in response._aiter_stream():
                await send(
                    {
                        "type": "http.response.body",
                        "body": chunk,
                        "more_body": True,
                    }
                )
                bytes_sent += len(chunk)
                chunk_count += 1
                logger.debug("Sent response chunk: size=%d bytes", len(chunk))

            # Send final empty chunk to signal end
            await send(
                {
                    "type": "http.response.body",
                    "body": b"",
                    "more_body": False,
                }
            )
            logger.info(
                "Response fully sent: status=%d total_bytes=%d chunks=%d",
                response.status_code,
                bytes_sent,
                chunk_count,
            )

        except Exception as e:
            logger.error(
                "Error sending response: status=%d error=%s",
                response.status_code,
                str(e),
                exc_info=True,
            )
            raise

    async def aclose(self) -> None:
        """Close the storage backend and release resources."""
        logger.info("Closing ASGICacheMiddleware and storage backend")
        try:
            if self.storage:
                await self.storage.close()
                logger.info("Storage backend closed successfully")
        except Exception as e:
            logger.error("Error closing storage backend: %s", str(e), exc_info=True)
            raise
