---
icon: material/butterfly
---

# HTTPX Integration

Hishel provides seamless integration with [HTTPX](https://www.python-httpx.org/), adding RFC 9111-compliant HTTP caching to your HTTPX applications with minimal code changes.

## Quick Start

The easiest way to add caching to your HTTPX application is using the cache-enabled client classes:

=== "Sync"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()
    
    # First request - fetches from origin
    response = client.get("https://api.example.com/data")
    print(response.extensions["hishel_from_cache"])  # False
    
    # Second request - served from cache
    response = client.get("https://api.example.com/data")
    print(response.extensions["hishel_from_cache"])  # True
    ```

=== "Async"
    ```python
    from hishel.httpx import AsyncCacheClient

    async with AsyncCacheClient() as client:
        # First request - fetches from origin
        response = await client.get("https://api.example.com/data")
        print(response.extensions["hishel_from_cache"])  # False
        
        # Second request - served from cache
        response = await client.get("https://api.example.com/data")
        print(response.extensions["hishel_from_cache"])  # True
    ```

That's it! Hishel automatically caches responses according to RFC 9111 rules.

---

## Cache Clients

Hishel provides drop-in replacements for HTTPX's `Client` and `AsyncClient`:

- `SyncCacheClient` - Synchronous caching client
- `AsyncCacheClient` - Asynchronous caching client

These clients inherit from HTTPX clients and accept all the same parameters, plus additional caching configuration.

### Basic Usage

=== "Sync"
    ```python
    from hishel.httpx import SyncCacheClient

    # Create client with default settings
    client = SyncCacheClient()

    # Make requests as usual
    response = client.get("https://api.example.com/users")
    
    # All HTTPX methods work
    client.post("https://api.example.com/data", json={"key": "value"})
    client.put("https://api.example.com/resource/1", data="content")
    
    # Or use context manager
    with SyncCacheClient() as client:
        response = client.get("https://api.example.com/data")
    ```

=== "Async"
    ```python
    from hishel.httpx import AsyncCacheClient

    # Create client with default settings
    client = AsyncCacheClient()

    # Make requests as usual
    response = await client.get("https://api.example.com/users")
    
    # All HTTPX async methods work

    await client.post("https://api.example.com/data", json={"key": "value"})
    await client.put("https://api.example.com/resource/1", data="content")
    
    # Or use context manager (recommended)
    async with AsyncCacheClient() as client:
        response = await client.get("https://api.example.com/data")
    ```

### Force Caching (Ignoring RFC 9111)

By default, Hishel follows RFC 9111 caching rules. To force caching regardless of response headers:

=== "Sync"
    ```python
    from hishel import CacheOptions
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient(
        cache_options=CacheOptions(always_cache=True)
    )
    
    # This will be cached even without proper cache headers
    response = client.get("https://api.example.com/data")
    ```

=== "Async"
    ```python
    from hishel import CacheOptions
    from hishel.httpx import AsyncCacheClient

    async with AsyncCacheClient(
        cache_options=CacheOptions(always_cache=True)
    ) as client:
        response = await client.get("https://api.example.com/data")
    ```

### Setting TTL (Time To Live)

Specify how long responses should be cached:

=== "Sync"
    ```python
    from hishel import CacheOptions
    from hishel.httpx import SyncCacheClient

    # Cache for 1 hour (3600 seconds)
    client = SyncCacheClient(
        cache_options=CacheOptions(ttl=3600)
    )
    
    response = client.get("https://api.example.com/data")
    ```

=== "Async"
    ```python
    from hishel import CacheOptions
    from hishel.httpx import AsyncCacheClient

    # Cache for 1 hour (3600 seconds)
    async with AsyncCacheClient(
        cache_options=CacheOptions(ttl=3600)
    ) as client:
        response = await client.get("https://api.example.com/data")
    ```

### Refresh on Hit

Update cache metadata on every cache hit to extend freshness:

=== "Sync"
    ```python
    from hishel import CacheOptions
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient(
        cache_options=CacheOptions(refresh_on_hit=True)
    )
    
    response = client.get("https://api.example.com/data")
    ```

=== "Async"
    ```python
    from hishel import CacheOptions
    from hishel.httpx import AsyncCacheClient

    async with AsyncCacheClient(
        cache_options=CacheOptions(refresh_on_hit=True)
    ) as client:
        response = await client.get("https://api.example.com/data")
    ```



## Cache Transports

For more control or to integrate with existing HTTPX clients, use cache transports directly:

=== "Sync"
    ```python
    import httpx
    from hishel import SyncSqliteStorage, CacheOptions
    from hishel.httpx import SyncCacheTransport

    # Create transport with caching
    transport = SyncCacheTransport(
        next_transport=httpx.HTTPTransport(),
        storage=SyncSqliteStorage(),
        cache_options=CacheOptions()
    )

    # Use with standard HTTPX client
    client = httpx.Client(transport=transport)
    
    response = client.get("https://api.example.com/data")
    ```

=== "Async"
    ```python
    import httpx
    from hishel import AsyncSqliteStorage, CacheOptions
    from hishel.httpx import AsyncCacheTransport

    # Create transport with caching
    transport = AsyncCacheTransport(
        next_transport=httpx.AsyncHTTPTransport(),
        storage=AsyncSqliteStorage(),
        cache_options=CacheOptions()
    )

    # Use with standard HTTPX client
    client = httpx.AsyncClient(transport=transport)
    
    response = await client.get("https://api.example.com/data")
    ```

### When to Use Transports

Use transports when you need to:

- Combine with other custom transports
- Add caching to existing HTTPX clients
- Have fine-grained control over transport layer
- Build custom client classes

### Chaining Transports

=== "Sync"
    ```python
    import httpx
    from hishel.httpx import SyncCacheTransport
    from hishel import SyncSqliteStorage

    # Custom transport (e.g., for logging)
    class LoggingTransport(httpx.BaseTransport):
        def __init__(self, transport: httpx.BaseTransport):
            self.transport = transport
        
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            print(f"Request: {request.method} {request.url}")
            response = self.transport.handle_request(request)
            print(f"Response: {response.status_code}")
            return response

    # Chain: HTTP -> Cache -> Logging
    transport = LoggingTransport(
        transport=SyncCacheTransport(
            next_transport=httpx.HTTPTransport(),
            storage=SyncSqliteStorage()
        )
    )

    client = httpx.Client(transport=transport)
    ```

=== "Async"
    ```python
    import httpx
    from hishel.httpx import AsyncCacheTransport
    from hishel import AsyncSqliteStorage

    # Custom transport (e.g., for logging)
    class LoggingTransport(httpx.AsyncBaseTransport):
        def __init__(self, transport: httpx.AsyncBaseTransport):
            self.transport = transport
        
        async def handle_async_request(
            self, request: httpx.Request
        ) -> httpx.Response:
            print(f"Request: {request.method} {request.url}")
            response = await self.transport.handle_async_request(request)
            print(f"Response: {response.status_code}")
            return response

    # Chain: HTTP -> Cache -> Logging
    transport = LoggingTransport(
        transport=AsyncCacheTransport(
            next_transport=httpx.AsyncHTTPTransport(),
            storage=AsyncSqliteStorage()
        )
    )

    client = httpx.AsyncClient(transport=transport)
    ```

---

## Controlling Cache Behavior

### Using Extensions (Recommended)

Set caching metadata using HTTPX's `extensions` parameter:

=== "Sync"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    # Custom TTL for specific request
    response = client.get(
        "https://api.example.com/data",
        extensions={"hishel_ttl": 300}  # Cache for 5 minutes
    )

    # Ignore caching rules
    response = client.get(
        "https://api.example.com/private",
        extensions={"hishel_spec_ignore": True}
    )

    # Multiple options
    response = client.get(
        "https://api.example.com/search",
        extensions={
            "hishel_ttl": 600,
            "hishel_refresh_ttl_on_access": True,
            "hishel_body_key": True  # Include body in cache key
        }
    )
    ```

=== "Async"
    ```python
    from hishel.httpx import AsyncCacheClient

    async with AsyncCacheClient() as client:
        # Custom TTL for specific request
        response = await client.get(
            "https://api.example.com/data",
            extensions={"hishel_ttl": 300}  # Cache for 5 minutes
        )

        # Ignore caching rules
        response = await client.get(
            "https://api.example.com/private",
            extensions={"hishel_spec_ignore": True}
        )

        # Multiple options
        response = await client.get(
            "https://api.example.com/search",
            extensions={
                "hishel_ttl": 600,
                "hishel_refresh_ttl_on_access": True,
                "hishel_body_key": True  # Include body in cache key
            }
        )
    ```

### Using Headers (Alternative)

You can also use HTTP headers:

=== "Sync"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    response = client.get(
        "https://api.example.com/data",
        headers={"X-Hishel-Ttl": "300"}
    )
    ```

=== "Async"
    ```python
    from hishel.httpx import AsyncCacheClient

    async with AsyncCacheClient() as client:
        response = await client.get(
            "https://api.example.com/data",
            headers={"X-Hishel-Ttl": "300"}
        )
    ```

!!! tip "Extensions vs Headers"
    Use `extensions` for better type safety and to avoid sending cache control headers to the server.

### Available Metadata

See [Metadata Documentation](../metadata.md) for complete reference:

- `hishel_ttl` - Custom TTL in seconds
- `hishel_refresh_ttl_on_access` - Enable sliding expiration
- `hishel_spec_ignore` - Ignore RFC 9111 rules
- `hishel_body_key` - Include body in cache key (for POST/GraphQL)

---

## Inspecting Cache Status

Check if responses came from cache using metadata:

=== "Sync"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    response = client.get("https://api.example.com/data")

    # Check cache status
    from_cache = response.extensions.get("hishel_from_cache", False)
    revalidated = response.extensions.get("hishel_revalidated", False)
    stored = response.extensions.get("hishel_stored", False)

    if from_cache and not revalidated:
        print("✓ Fresh cache hit")
    elif from_cache and revalidated:
        print("↻ Revalidated (304)")
    else:
        print("✗ Cache miss")

    if stored:
        print("Response was cached for future requests")
    ```

=== "Async"
    ```python
    from hishel.httpx import AsyncCacheClient

    async with AsyncCacheClient() as client:
        response = await client.get("https://api.example.com/data")

        # Check cache status
        from_cache = response.extensions.get("hishel_from_cache", False)
        revalidated = response.extensions.get("hishel_revalidated", False)
        stored = response.extensions.get("hishel_stored", False)

        if from_cache and not revalidated:
            print("✓ Fresh cache hit")
        elif from_cache and revalidated:
            print("↻ Revalidated (304)")
        else:
            print("✗ Cache miss")

        if stored:
            print("Response was cached for future requests")
    ```

---

## Migration from Standard HTTPX

Migrating existing HTTPX code to use Hishel is straightforward:

**Before (Standard HTTPX):**
```python
import httpx

client = httpx.Client()
response = client.get("https://api.example.com/data")
```

**After (With Caching):**
```python
from hishel.httpx import SyncCacheClient

client = SyncCacheClient()  # Drop-in replacement
response = client.get("https://api.example.com/data")
```

All HTTPX features continue to work:

- ✓ Request parameters (`params`, `headers`, `json`, `data`)
- ✓ Authentication (`auth`)
- ✓ Timeouts (`timeout`)
- ✓ HTTP/2 support (`http2=True`)
- ✓ Proxies (`proxies`)
- ✓ Custom transports
- ✓ Event hooks
- ✓ Connection pooling

---

## See Also

- [Metadata Reference](../metadata.md) - Complete guide to caching metadata
- [Storage Documentation](../storages.md) - Storage backend configuration
- [Specification](../specification.md) - RFC 9111 state machine
- [HTTPX Documentation](https://www.python-httpx.org/) - Official HTTPX docs