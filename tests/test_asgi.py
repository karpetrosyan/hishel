from __future__ import annotations

import gzip
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import anysqlite
import pytest
from inline_snapshot import snapshot
from time_machine import travel

from hishel import AsyncSqliteStorage, CacheOptions
from hishel.asgi import ASGICacheMiddleware, _ASGIScope


# Mock ASGI application that returns a simple response
async def simple_asgi_app(scope: _ASGIScope, receive: Any, send: Any) -> None:
    """Simple ASGI app that returns a 200 OK response with cache headers."""
    if scope["type"] != "http":
        return

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/plain"),
                (b"cache-control", b"public, max-age=3600"),
                (b"content-length", b"13"),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": b"Hello, World!",
            "more_body": False,
        }
    )


# Mock ASGI application that returns no-cache response
async def no_cache_asgi_app(scope: _ASGIScope, receive: Any, send: Any) -> None:
    """ASGI app that returns a response without cache headers."""
    if scope["type"] != "http":
        return

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/plain"),
                (b"cache-control", b"no-cache"),
                (b"content-length", b"13"),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": b"Hello, World!",
            "more_body": False,
        }
    )


# Mock ASGI application that returns gzipped content
async def gzipped_asgi_app(scope: _ASGIScope, receive: Any, send: Any) -> None:
    """ASGI app that returns gzip-encoded content."""
    if scope["type"] != "http":
        return

    data = gzip.compress(b"a" * 1000)
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/plain"),
                (b"content-encoding", b"gzip"),
                (b"content-length", str(len(data)).encode()),
                (b"cache-control", b"public, max-age=3600"),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": data,
            "more_body": False,
        }
    )


# Mock ASGI application that streams response in chunks
async def streaming_asgi_app(scope: _ASGIScope, receive: Any, send: Any) -> None:
    """ASGI app that streams response in multiple chunks."""
    if scope["type"] != "http":
        return

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/plain"),
                (b"cache-control", b"public, max-age=3600"),
            ],
        }
    )

    # Send multiple chunks
    for i in range(5):
        await send(
            {
                "type": "http.response.body",
                "body": f"Chunk {i}\n".encode(),
                "more_body": True,
            }
        )

    # Final chunk
    await send(
        {
            "type": "http.response.body",
            "body": b"",
            "more_body": False,
        }
    )


# Mock ASGI application that echoes the request method
async def echo_method_asgi_app(scope: _ASGIScope, receive: Any, send: Any) -> None:
    """ASGI app that echoes the HTTP method in the response."""
    if scope["type"] != "http":
        return

    method = scope.get("method", "UNKNOWN")
    body = f"Method: {method}".encode()

    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [
                (b"content-type", b"text/plain"),
                (b"cache-control", b"public, max-age=3600"),
                (b"content-length", str(len(body)).encode()),
            ],
        }
    )
    await send(
        {
            "type": "http.response.body",
            "body": body,
            "more_body": False,
        }
    )


# Helper function to create ASGI scope
def create_asgi_scope(
    method: str = "GET",
    path: str = "/",
    query_string: bytes = b"",
    headers: list[tuple[bytes, bytes]] | None = None,
) -> _ASGIScope:
    """Create a basic ASGI HTTP scope dictionary."""
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "https",
        "path": path,
        "query_string": query_string,
        "root_path": "",
        "headers": headers or [],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 8000),
        "state": {},
        "extensions": {},
    }


# Helper function to create a simple receive callable
async def simple_receive() -> dict[str, Any]:
    """Simple receive callable that returns http.disconnect."""
    return {"type": "http.disconnect"}


# Helper class to collect ASGI responses
class ResponseCollector:
    """Collect response data from ASGI send calls."""

    def __init__(self) -> None:
        self.status: int = 0
        self.headers: list[tuple[bytes, bytes]] = []
        self.body_chunks: list[bytes] = []

    async def send(self, message: dict[str, Any]) -> None:
        """Collect response data from send calls."""
        if message["type"] == "http.response.start":
            self.status = message["status"]
            self.headers = message.get("headers", [])
        elif message["type"] == "http.response.body":
            body = message.get("body", b"")
            if body:
                self.body_chunks.append(body)

    def get_body(self) -> bytes:
        """Get the complete response body."""
        return b"".join(self.body_chunks)

    def get_header(self, name: bytes) -> bytes | None:
        """Get a response header by name."""
        for key, value in self.headers:
            if key.lower() == name.lower():
                return value
        return None


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")), tick=False)
async def test_simple_caching(caplog: pytest.LogCaptureFixture) -> None:
    """Test that basic caching works with ASGI middleware."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))
    middleware = ASGICacheMiddleware(app=simple_asgi_app, storage=storage)

    # First request - cache miss
    scope = create_asgi_scope()
    collector1 = ResponseCollector()

    with caplog.at_level("DEBUG", logger="hishel"):
        await middleware(scope, simple_receive, collector1.send)

    assert collector1.status == 200
    assert collector1.get_body() == b"Hello, World!"

    # Check that cache miss occurred
    assert any("CacheMiss" in msg for msg in caplog.messages)

    collector2 = ResponseCollector()

    with caplog.at_level("DEBUG", logger="hishel"):
        await middleware(scope, simple_receive, collector2.send)

    assert caplog.messages == snapshot(
        [
            "Incoming HTTP request: method=GET path=/",
            "Building internal request: method=GET url=https://testserver:80/ headers_count=0",
            "Converted ASGI request to internal format: url=https://testserver:80/",
            "Handling request through cache proxy",
            "Handling state: IdleClient",
            "Handling state: CacheMiss",
            "Sending request to wrapped application: url=https://testserver:80/",
            "Application response started: status=200",
            "Received response body chunk: size=13 bytes",
            "Application response complete: status=200 total_bytes=13 chunks=1",
            "Storing response in cache",
            "Handling state: StoreAndUse",
            "Request processed: method=GET path=/ status=200",
            "Sending response to client: status=200 headers_count=3",
            "Response headers sent",
            "Sent response chunk: size=13 bytes",
            "Response fully sent: status=200 total_bytes=13 chunks=1",
            "Response sent successfully",
            "Incoming HTTP request: method=GET path=/",
            "Building internal request: method=GET url=https://testserver:80/ headers_count=0",
            "Converted ASGI request to internal format: url=https://testserver:80/",
            "Handling request through cache proxy",
            "Handling state: IdleClient",
            "Handling state: FromCache",
            "Request processed: method=GET path=/ status=200",
            "Sending response to client: status=200 headers_count=4",
            "Response headers sent",
            "Sent response chunk: size=13 bytes",
            "Response fully sent: status=200 total_bytes=13 chunks=1",
            "Response sent successfully",
        ]
    )
    assert collector2.status == 200
    assert collector2.get_body() == b"Hello, World!"

    await middleware.aclose()


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")), tick=False)
async def test_simple_caching_ignoring_spec(caplog: pytest.LogCaptureFixture) -> None:
    """Test caching with ignore_specification flag."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))
    middleware = ASGICacheMiddleware(
        app=no_cache_asgi_app,
        storage=storage,
        ignore_specification=True,
    )

    # First request
    scope = create_asgi_scope()
    collector1 = ResponseCollector()

    with caplog.at_level("DEBUG", logger="hishel"):
        await middleware(scope, simple_receive, collector1.send)

    assert collector1.status == 200
    assert collector1.get_body() == b"Hello, World!"

    # Should cache despite no-cache header
    assert any("ignoring specification" in msg.lower() for msg in caplog.messages)

    collector2 = ResponseCollector()

    with caplog.at_level("DEBUG", logger="hishel"):
        await middleware(scope, simple_receive, collector2.send)

    assert caplog.messages == snapshot(
        [
            "Incoming HTTP request: method=GET path=/",
            "Building internal request: method=GET url=https://testserver:80/ headers_count=0",
            "Converted ASGI request to internal format: url=https://testserver:80/",
            "Handling request through cache proxy",
            "Trying to get cached response ignoring specification",
            "Found 0 cached entries for the request",
            "Sending request to wrapped application: url=https://testserver:80/",
            "Application response started: status=200",
            "Received response body chunk: size=13 bytes",
            "Application response complete: status=200 total_bytes=13 chunks=1",
            "Storing response in cache ignoring specification",
            "Request processed: method=GET path=/ status=200",
            "Sending response to client: status=200 headers_count=3",
            "Response headers sent",
            "Sent response chunk: size=13 bytes",
            "Response fully sent: status=200 total_bytes=13 chunks=1",
            "Response sent successfully",
            "Incoming HTTP request: method=GET path=/",
            "Building internal request: method=GET url=https://testserver:80/ headers_count=0",
            "Converted ASGI request to internal format: url=https://testserver:80/",
            "Handling request through cache proxy",
            "Trying to get cached response ignoring specification",
            "Found 1 cached entries for the request",
            "Found matching cached response for the request",
            "Request processed: method=GET path=/ status=200",
            "Sending response to client: status=200 headers_count=3",
            "Response headers sent",
            "Sent response chunk: size=13 bytes",
            "Response fully sent: status=200 total_bytes=13 chunks=1",
            "Response sent successfully",
        ]
    )
    assert collector2.status == 200
    assert collector2.get_body() == b"Hello, World!"

    await middleware.aclose()


@pytest.mark.anyio
async def test_encoded_content_caching() -> None:
    """Test that gzip-encoded content is cached correctly."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))
    middleware = ASGICacheMiddleware(
        app=gzipped_asgi_app,
        storage=storage,
        ignore_specification=True,
    )

    # First request - cache miss
    scope = create_asgi_scope()
    collector1 = ResponseCollector()
    await middleware(scope, simple_receive, collector1.send)

    assert collector1.status == 200
    data = collector1.get_body()
    assert collector1.get_header(b"content-encoding") == b"gzip"
    assert len(data) > 0
    # Verify it's actually gzipped
    decompressed = gzip.decompress(data)
    assert decompressed == b"a" * 1000

    # Second request - cache hit
    collector2 = ResponseCollector()
    await middleware(scope, simple_receive, collector2.send)

    assert collector2.status == 200
    cached_data = collector2.get_body()
    assert cached_data == data
    assert collector2.get_header(b"content-encoding") == b"gzip"

    await middleware.aclose()


@pytest.mark.anyio
async def test_streaming_response_caching() -> None:
    """Test that streaming responses are cached correctly."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))
    middleware = ASGICacheMiddleware(
        app=streaming_asgi_app,
        storage=storage,
        ignore_specification=True,
    )

    # First request - cache miss
    scope = create_asgi_scope()
    collector1 = ResponseCollector()
    await middleware(scope, simple_receive, collector1.send)

    assert collector1.status == 200
    body1 = collector1.get_body()
    expected = b"".join(f"Chunk {i}\n".encode() for i in range(5))
    assert body1 == expected

    # Second request - cache hit
    collector2 = ResponseCollector()
    await middleware(scope, simple_receive, collector2.send)

    assert collector2.status == 200
    body2 = collector2.get_body()
    assert body2 == body1

    await middleware.aclose()


@pytest.mark.anyio
async def test_different_methods() -> None:
    """Test that different HTTP methods are cached separately."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))
    middleware = ASGICacheMiddleware(
        app=echo_method_asgi_app,
        storage=storage,
        ignore_specification=True,
    )

    # GET request
    scope_get = create_asgi_scope(method="GET")
    collector_get = ResponseCollector()
    await middleware(scope_get, simple_receive, collector_get.send)

    assert collector_get.status == 200
    assert collector_get.get_body() == b"Method: GET"

    # POST request
    scope_post = create_asgi_scope(method="POST")
    collector_post = ResponseCollector()
    await middleware(scope_post, simple_receive, collector_post.send)

    assert collector_post.status == 200
    assert collector_post.get_body() == b"Method: POST"

    # Second GET request - should hit cache
    collector_get2 = ResponseCollector()
    await middleware(scope_get, simple_receive, collector_get2.send)

    assert collector_get2.status == 200
    assert collector_get2.get_body() == b"Method: GET"

    await middleware.aclose()


@pytest.mark.anyio
async def test_different_paths() -> None:
    """Test that different paths are cached separately."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))
    middleware = ASGICacheMiddleware(
        app=simple_asgi_app,
        storage=storage,
        ignore_specification=True,
    )

    # Request to /path1
    scope1 = create_asgi_scope(path="/path1")
    collector1 = ResponseCollector()
    await middleware(scope1, simple_receive, collector1.send)

    assert collector1.status == 200

    # Request to /path2
    scope2 = create_asgi_scope(path="/path2")
    collector2 = ResponseCollector()
    await middleware(scope2, simple_receive, collector2.send)

    assert collector2.status == 200

    # Second request to /path1 - should hit cache
    collector1_cached = ResponseCollector()
    await middleware(scope1, simple_receive, collector1_cached.send)

    assert collector1_cached.status == 200

    await middleware.aclose()


@pytest.mark.anyio
async def test_query_strings() -> None:
    """Test that query strings are included in cache keys."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))
    middleware = ASGICacheMiddleware(
        app=simple_asgi_app,
        storage=storage,
        ignore_specification=True,
    )

    # Request with query string 1
    scope1 = create_asgi_scope(query_string=b"param=value1")
    collector1 = ResponseCollector()
    await middleware(scope1, simple_receive, collector1.send)

    assert collector1.status == 200

    # Request with query string 2
    scope2 = create_asgi_scope(query_string=b"param=value2")
    collector2 = ResponseCollector()
    await middleware(scope2, simple_receive, collector2.send)

    assert collector2.status == 200

    # Second request with query string 1 - should hit cache
    collector1_cached = ResponseCollector()
    await middleware(scope1, simple_receive, collector1_cached.send)

    assert collector1_cached.status == 200

    await middleware.aclose()


@pytest.mark.anyio
async def test_non_http_scope() -> None:
    """Test that non-HTTP scopes are passed through without caching."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

    # Track if the app was called
    app_called = False

    async def websocket_app(scope: _ASGIScope, receive: Any, send: Any) -> None:
        nonlocal app_called
        app_called = True

    middleware = ASGICacheMiddleware(app=websocket_app, storage=storage)

    # WebSocket scope
    scope = {
        "type": "websocket",
        "path": "/ws",
    }

    await middleware(scope, simple_receive, lambda msg: None)  # type: ignore

    # App should have been called directly
    assert app_called

    await middleware.aclose()


@pytest.mark.anyio
async def test_custom_cache_options() -> None:
    """Test that custom cache options are respected."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))
    cache_options = CacheOptions()

    middleware = ASGICacheMiddleware(
        app=simple_asgi_app,
        storage=storage,
        cache_options=cache_options,
    )

    scope = create_asgi_scope()
    collector = ResponseCollector()
    await middleware(scope, simple_receive, collector.send)

    assert collector.status == 200
    assert collector.get_body() == b"Hello, World!"

    await middleware.aclose()


@pytest.mark.anyio
async def test_request_with_body() -> None:
    """Test that requests with bodies are handled correctly."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

    # Track if body was received
    received_body = []

    async def body_echo_app(scope: _ASGIScope, receive: Any, send: Any) -> None:
        """ASGI app that collects the request body."""
        if scope["type"] != "http":
            return

        # Read request body
        while True:
            message = await receive()
            if message["type"] == "http.request":
                body = message.get("body", b"")
                if body:
                    received_body.append(body)
                if not message.get("more_body", False):
                    break
            elif message["type"] == "http.disconnect":
                break

        # Send response
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"text/plain"),
                    (b"cache-control", b"public, max-age=3600"),
                ],
            }
        )
        await send(
            {
                "type": "http.response.body",
                "body": b"Body received",
                "more_body": False,
            }
        )

    middleware = ASGICacheMiddleware(app=body_echo_app, storage=storage)

    # Create receive callable that sends body
    body_sent = False

    async def receive_with_body() -> dict[str, Any]:
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {
                "type": "http.request",
                "body": b"Test body content",
                "more_body": False,
            }
        return {"type": "http.disconnect"}

    scope = create_asgi_scope(method="POST")
    collector = ResponseCollector()
    await middleware(scope, receive_with_body, collector.send)

    assert collector.status == 200
    assert collector.get_body() == b"Body received"
    assert b"Test body content" in received_body

    await middleware.aclose()


@pytest.mark.anyio
async def test_headers_are_preserved() -> None:
    """Test that response headers are preserved in cached responses."""
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))
    middleware = ASGICacheMiddleware(
        app=simple_asgi_app,
        storage=storage,
        ignore_specification=True,
    )

    # First request
    scope = create_asgi_scope()
    collector1 = ResponseCollector()
    await middleware(scope, simple_receive, collector1.send)

    assert collector1.get_header(b"content-type") == b"text/plain"
    assert collector1.get_header(b"cache-control") is not None

    # Second request - from cache
    collector2 = ResponseCollector()
    await middleware(scope, simple_receive, collector2.send)

    # Headers should be preserved
    assert collector2.get_header(b"content-type") == b"text/plain"
    assert collector2.get_header(b"cache-control") is not None

    await middleware.aclose()
