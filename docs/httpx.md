# HTTPX and HTTPX2 Integration

Hishel adds HTTP caching to your [HTTPX](https://www.python-httpx.org/) applications with minimal code changes.

This page also applies to [HTTPX2](https://httpx2.pydantic.dev/), a fork of HTTPX maintained by Pydantic. Install the `httpx2` extra and import from `hishel.httpx2` instead:

```python
from hishel.httpx2 import AsyncCacheClient, AsyncCacheTransport, SyncCacheClient, SyncCacheTransport
```

## Installation

```bash
pip install "hishel[httpx]"
```

## Quick Start

The easiest way to add caching to your HTTPX application is using the cache-enabled client classes:

::: code-group

```python [Sync]
from hishel.httpx import SyncCacheClient

with SyncCacheClient() as client:
    # First request - fetches from origin
    client.get("https://api.example.com/data")

    # Second request - served from cache
    client.get("https://api.example.com/data")
```

```python [Async]
from hishel.httpx import AsyncCacheClient

async with AsyncCacheClient() as client:
    # First request - fetches from origin
    await client.get("https://api.example.com/data")

    # Second request - served from cache
    await client.get("https://api.example.com/data")
```

:::

---

## Caching Modes

### Default

Without any configuration, Hishel:

- caches successful `GET` and `HEAD` responses, except `206 Partial Content`
- uses the method and URL as the cache key
- ignores HTTP caching headers, including `no-store`, `private` and `Vary`
- serves an entry until the storage's [TTL or TTI](/storages#expiring-entries) expires it

The cache is global. Everyone using it gets the same entries, whatever their `Authorization` or `Cookie` headers are, which suits a private cache inside a backend. If responses differ per user, use RFC mode or a separate storage for each user.

### RFC 9111

With `rfc=True`, Hishel follows the HTTP caching specification instead, so caching headers decide what is stored, how long it stays fresh, and when it needs revalidating with the server:

::: code-group

```python [Sync]
from hishel.httpx import SyncCacheClient

client = SyncCacheClient(rfc=True)
```

```python [Async]
from hishel.httpx import AsyncCacheClient

client = AsyncCacheClient(rfc=True)
```

:::

To configure it, pass `CacheOptions` instead of `True`:

```python
from hishel import CacheOptions
from hishel.httpx import SyncCacheClient

client = SyncCacheClient(rfc=CacheOptions(shared=False))
```

`CacheOptions` accepts these options:

- `shared` (default `True`): `True` acts as a shared cache, serving many users. It respects `private` and doesn't store responses to requests with `Authorization`, unless the response allows it ([RFC 9111 Section 3.5](https://www.rfc-editor.org/rfc/rfc9111.html#section-3.5)). `False` acts as a private cache for a single user, which can store those responses.
- `allow_stale` (default `False`): Whether stale responses can be served without revalidating them, when caching directives allow it ([RFC 9111 Section 4.2.4](https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2.4)).
- `supported_methods` (default `["GET", "HEAD"]`): The methods whose responses can be stored. Only safe methods can be served from the cache, so listing `POST` stores responses that are never used.

---

## Choosing a Storage

Clients and transports use a [SQLite storage](/storages#sqlite-storage) unless you pass another one:

::: code-group

```python [Sync]
from hishel import SyncSqliteStorage
from hishel.httpx import SyncCacheClient

client = SyncCacheClient(storage=SyncSqliteStorage(default_ttl=3600))
```

```python [Async]
from hishel import AsyncSqliteStorage
from hishel.httpx import AsyncCacheClient

client = AsyncCacheClient(storage=AsyncSqliteStorage(default_ttl=3600))
```

:::

Closing a client or transport also closes its storage, including one you passed in, so don't close it while another client is using the same storage.

---

## Per-Request Configuration

Use the `caching` extension to override the mode, the storage, the expiry or the cache key for a single request:

```python
from hishel import CacheOptions, SyncSqliteStorage
from hishel.httpx import SyncCacheClient

client = SyncCacheClient()

# Follow RFC 9111 for this request only
client.get("https://api.example.com/data", extensions={"caching": {"rfc": True}})

# Or with options
client.get("https://api.example.com/data", extensions={"caching": {"rfc": CacheOptions(shared=False)}})

# Use a different storage for this request only
other_storage = SyncSqliteStorage(database_path="other.db")
client.get("https://api.example.com/data", extensions={"caching": {"storage": other_storage}})

# Expire this response after 1 hour, or after 5 minutes without being used
client.get("https://api.example.com/data", extensions={"caching": {"ttl": 3600, "tti": 300}})

# Use your own cache key instead of the method and URL
client.get("https://api.example.com/data", extensions={"caching": {"key": "user-42:data"}})
```

`ttl` and `tti` are in seconds and override the storage's `default_ttl` and `default_tti`. They apply when a response is stored, so a request answered by an existing entry doesn't change when that entry expires. They can't remove a limit set on the storage: `None` means the same as leaving them out.

`key` replaces the usual cache key, which is a hash of the method and URL in the default mode, and of the URL in RFC mode. For example, this keeps one user's entries apart from another's in the default mode.

- **Lookup and store:** the key is used as given, for finding entries and for storing a new one. A response stored under it isn't found by requests without it.
- **Shared keys:** in the default mode, requests with the same key and method get the same entry, whatever their URL. In RFC mode, an entry is only served to its own URL, so the other URLs store entries of their own under that key.
- **Methods:** `GET` and `HEAD` can share a key, but don't answer each other. A key doesn't make `POST` responses cacheable.
- **Invalidation:** in RFC mode, a request with an unsafe method, such as `POST`, removes the entries of its URL unless the response is an error. It only finds the entries under its own key, so it has to use the same key as the requests it should invalidate.
- **Redirects:** the key also applies to the requests that follow a redirect. In the default mode, the final response is stored under it, so the next request gets that response directly, without the redirect in its history.

---

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
    rfc=True,
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
    rfc=True,
)

# Use with standard HTTPX client
client = httpx.AsyncClient(transport=transport)

response = await client.get("https://api.example.com/data")
```

:::

::: warning
`SyncCacheClient(transport=...)` and `AsyncCacheClient(transport=...)` use the transport you pass as it is, without any caching. To cache on top of your own transport, wrap it in a cache transport as shown above.
:::

---

## Hits and Misses

Responses don't record whether they came from the cache. In RFC mode, a response served from the cache has an `Age` header, as the specification requires. In the default mode, nothing distinguishes the two.
