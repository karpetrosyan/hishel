# Getting Started

## Installation

```bash
pip install "hishel[httpx]"
```

## With HTTPX

::: code-group

```python [Sync]
from hishel.httpx import SyncCacheClient

with SyncCacheClient() as client:
    # First request - fetches from origin
    client.get("https://api.example.com/data")
    # Second request - served from cache
    response = client.get("https://api.example.com/data")
    print(response.text)
```

```python [Async]
from hishel.httpx import AsyncCacheClient

async with AsyncCacheClient() as client:
    # First request - fetches from origin
    await client.get("https://api.example.com/data")
    # Second request - served from cache
    response = await client.get("https://api.example.com/data")
    print(response.text)
```

:::

By default, Hishel ignores HTTP caching headers and keeps a response until you expire it, which the default SQLite storage never does on its own. You will usually want to set a lifetime:

```python
from hishel import SyncSqliteStorage
from hishel.httpx import SyncCacheClient

client = SyncCacheClient(storage=SyncSqliteStorage(default_ttl=3600))
```

To let servers decide what is cached and for how long, turn on RFC 9111 mode:

```python
from hishel.httpx import SyncCacheClient

client = SyncCacheClient(rfc=True)
```

See [HTTPX](/httpx) for how the two modes differ, and [Storages](/storages) for the storage options.

Hishel also works with [Requests](/requests), and on the server with [ASGI](/asgi) and [FastAPI](/fastapi).
