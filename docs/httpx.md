# HTTPX/HTTPX2 Integration

Hishel provides seamless integration with:
- [HTTPX](https://www.python-httpx.org/)
- [HTTPX2](https://httpx2.pydantic.dev/)

adding RFC 9111-compliant HTTP caching to your HTTPX/HTTPX2 applications with minimal code changes.

## Note on httpx vs httpx2

`httpx2` is a fork of `httpx`, maintained by Pydantic.

**The documentation below is valid for both `httpx` and `httpx2`.**

All imports
```python
from hishel.httpx import ...
```
can be replaced by 
```python
from hishel.httpx2 import ...
```

## Quick Start

The easiest way to add caching to your HTTPX application is using the cache-enabled client classes:

::: code-group

```python [Sync]
from hishel.httpx import SyncCacheClient

client = SyncCacheClient()

# First request - fetches from origin
response = client.get("https://api.example.com/data")
print(response.extensions["hishel_from_cache"])  # False

# Second request - served from cache
response = client.get("https://api.example.com/data")
print(response.extensions["hishel_from_cache"])  # True
```

```python [Async]
from hishel.httpx import AsyncCacheClient

async with AsyncCacheClient() as client:
    # First request - fetches from origin
    response = await client.get("https://api.example.com/data")
    print(response.extensions["hishel_from_cache"])  # False

    # Second request - served from cache
    response = await client.get("https://api.example.com/data")
    print(response.extensions["hishel_from_cache"])  # True
```

:::

That's it! Hishel automatically caches responses according to RFC 9111 rules.

---

## Cache Clients

Hishel provides drop-in replacements for HTTPX's `Client` and `AsyncClient`:

- `SyncCacheClient` - Synchronous caching client
- `AsyncCacheClient` - Asynchronous caching client

These clients inherit from HTTPX clients and accept all the same parameters, plus additional caching configuration.

::: code-group

```python [Sync]
from hishel.httpx import SyncCacheClient

# Create client with default settings
client = SyncCacheClient()

# Make requests as usual
response = client.get("https://api.example.com/users")
```

```python [Async]
from hishel.httpx import AsyncCacheClient

# Create client with default settings
client = AsyncCacheClient()

# Make requests as usual
response = await client.get("https://api.example.com/users")
```

:::


## Cache Transports

For more control or to integrate with existing HTTPX clients, use cache transports directly:

::: code-group

```python [Sync]
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

```python [Async]
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

:::