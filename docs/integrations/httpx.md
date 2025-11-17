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


## Cache Transports

For more control or to integrate with existing HTTPX clients, use cache transports directly:

=== "Sync"
    ```python
    import httpx
    from hishel import SyncSqliteStorage
    from hishel.httpx import SyncCacheTransport

    # Create transport with caching
    transport = SyncCacheTransport(
        next_transport=httpx.HTTPTransport(),
        storage=SyncSqliteStorage(),
    )

    # Use with standard HTTPX client
    client = httpx.Client(transport=transport)
    
    response = client.get("https://api.example.com/data")
    ```

=== "Async"
    ```python
    import httpx
    from hishel import AsyncSqliteStorage
    from hishel.httpx import AsyncCacheTransport

    # Create transport with caching
    transport = AsyncCacheTransport(
        next_transport=httpx.AsyncHTTPTransport(),
        storage=AsyncSqliteStorage(),
    )

    # Use with standard HTTPX client
    client = httpx.AsyncClient(transport=transport)
    
    response = await client.get("https://api.example.com/data")
    ```

## See Also

- [Metadata Reference](../metadata.md) - Complete guide to caching metadata
- [Storage Documentation](../storages.md) - Storage backend configuration
- [Specification](../specification.md) - RFC 9111 state machine
- [HTTPX Documentation](https://www.python-httpx.org/) - Official HTTPX docs