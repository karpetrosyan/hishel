# Storages

A storage keeps cached responses. Hishel comes with SQLite and Redis storages, and you can [write your own](#custom-storages).

All of them stream response bodies instead of loading them fully into memory, and a response is only stored once its body has been read to the end. Request headers are stored with the response as plain text, including any credentials they contain.

A storage failing doesn't fail your requests. If Redis is down or the SQLite file is locked, the failure is logged and the request goes to the server as a cache miss. The exception is a cached body that is already being read, which raises rather than ending early.

## Expiring Entries

Every storage accepts two limits, in seconds. An entry expires at whichever comes first:

- `default_ttl` (time to live), counted from when the entry was created.
- `default_tti` (time to idle), counted from when the entry was last returned. Updates to this are batched, so an entry can expire up to half its TTI sooner.

::: code-group

```python [Sync]
from hishel import SyncSqliteStorage

# Expires after 1 day, or after 1 hour without being used
storage = SyncSqliteStorage(default_ttl=86400, default_tti=3600)
```

```python [Async]
from hishel import AsyncSqliteStorage

# Expires after 1 day, or after 1 hour without being used
storage = AsyncSqliteStorage(default_ttl=86400, default_tti=3600)
```

:::

To override these for a single response, see the [HTTPX](/httpx#per-request-configuration) and [Requests](/requests#per-request-expiry) integrations. If you are calling a storage directly, `create_entry` takes `ttl` and `tti`.

## SQLite Storage

The default storage puts all cached responses in a single SQLite database file.

::: code-group

```python [Sync]
from hishel import SyncSqliteStorage

storage = SyncSqliteStorage()
```

```python [Async]
from hishel import AsyncSqliteStorage

storage = AsyncSqliteStorage()
```

:::

`AsyncSqliteStorage` needs the `async` extra, which the `httpx` extra already includes:

```bash
pip install "hishel[async]"
```

The SQLite storages accept these options:

- `database_path` (default `"hishel_cache_v2.db"`): Where the database file goes.
- `connection` (default `None`): An existing connection to use instead of opening one.
- `default_ttl` (default `None`, no limit): See [Expiring Entries](#expiring-entries).
- `default_tti` (default `None`, no limit): See [Expiring Entries](#expiring-entries).
- `max_size` (default 1 GiB): The size of the database to aim for, in bytes. `None` means no limit.
- `max_stream_size` (default `None`, no limit): The largest response body to cache, in bytes.
- `soft_delete_ttl` (default `180`): How long a removed or expired entry is kept for readers still streaming it, in seconds.

### Custom Path

A path with a directory is used as it is. A bare file name goes in `.cache/hishel/` in the current working directory, which is also where the default database is created.

::: code-group

```python [Sync]
from hishel import SyncSqliteStorage

storage = SyncSqliteStorage(database_path="/path/to/cache.db")
```

```python [Async]
from hishel import AsyncSqliteStorage

storage = AsyncSqliteStorage(database_path="/path/to/cache.db")
```

:::

Hishel adds a `.gitignore` to the directory it creates the database in, which ignores everything in that directory.

### Max Size

When the database grows past `max_size`, Hishel removes the least recently used entries.

::: code-group

```python [Sync]
from hishel import SyncSqliteStorage

storage = SyncSqliteStorage(max_size=100 * 1024 * 1024)
```

```python [Async]
from hishel import AsyncSqliteStorage

storage = AsyncSqliteStorage(max_size=100 * 1024 * 1024)
```

:::

The limit is approximate:

- It is checked before writing, so the database can go past it by the size of the entries being written.
- Entries used within the last `soft_delete_ttl` seconds can't be removed yet. If they fill the database, new responses aren't cached until some can.

### Existing Connections

You can pass your own connection, which is also how you get an in-memory cache:

::: code-group

```python [Sync]
import sqlite3
from hishel import SyncSqliteStorage

# check_same_thread=False lets the storage be used from other threads
connection = sqlite3.connect(":memory:", check_same_thread=False)
storage = SyncSqliteStorage(connection=connection)
```

```python [Async]
import anysqlite
from hishel import AsyncSqliteStorage

connection = await anysqlite.connect(":memory:")
storage = AsyncSqliteStorage(connection=connection)
```

:::

::: warning
The storage creates tables named `entries` and `streams`, and turns on WAL mode. If the database already has tables with those names and other columns, including a cache file written by Hishel 1.x, the storage raises a `RuntimeError` on first use and leaves them as they are.
:::

## Redis Storage

Redis storage provides fast, in-memory (or persistent) caching backed by a Redis server. It needs Redis 7 or newer.

```bash
pip install "hishel[redis]"
```

::: code-group

```python [Sync]
from redis import Redis
from hishel import RedisStorage

client = Redis(host="localhost", port=6379)
storage = RedisStorage(client=client)
```

```python [Async]
from redis.asyncio import Redis
from hishel import AsyncRedisStorage

client = Redis(host="localhost", port=6379)
storage = AsyncRedisStorage(client=client)
```

:::

The Redis storages accept these options:

- `client` (required): The Redis client to use.
- `key_prefix` (default `"hishel"`): The prefix of all Redis keys.
- `default_ttl` (default `3600`): See [Expiring Entries](#expiring-entries). `None` means no limit.
- `default_tti` (default `None`, no limit): See [Expiring Entries](#expiring-entries).
- `max_stream_size` (default 10 MiB): The largest response body to cache, in bytes. `None` means no limit.
- `soft_delete_ttl` (default `180`): How long a removed or expired entry is kept for readers still streaming it, in seconds.

Unlike SQLite, Redis storage has no `max_size`. Use the server's `maxmemory` settings to limit its size and control eviction.

### Custom Key Prefix

You can set a custom prefix for all Redis keys. This is useful when sharing a Redis instance across multiple applications:

::: code-group

```python [Sync]
from redis import Redis
from hishel import RedisStorage

client = Redis(host="localhost", port=6379)
storage = RedisStorage(client=client, key_prefix="myapp")
```

```python [Async]
from redis.asyncio import Redis
from hishel import AsyncRedisStorage

client = Redis(host="localhost", port=6379)
storage = AsyncRedisStorage(client=client, key_prefix="myapp")
```

:::

## Common Behavior

### Soft Deletion

When an entry is removed or expires, new requests stop receiving it straight away, but its data stays for `soft_delete_ttl` seconds so that any reader already streaming it can finish. Active readers keep extending that window.

::: code-group

```python [Sync]
from hishel import SyncSqliteStorage

storage = SyncSqliteStorage(soft_delete_ttl=60)
```

```python [Async]
from hishel import AsyncSqliteStorage

storage = AsyncSqliteStorage(soft_delete_ttl=60)
```

:::

### Max Stream Size

Without a cap, a misbehaving upstream that keeps streaming bytes could fill your storage before anyone notices.

`max_stream_size` bounds how much of a single response body Hishel will store. Once a body goes past it, Hishel drops what it had written and stops caching that response. The remaining bytes still reach the client, so the request succeeds, but the response isn't cached.

::: code-group

```python [Sync]
from redis import Redis
from hishel import RedisStorage

client = Redis(host="localhost", port=6379)
storage = RedisStorage(client=client, max_stream_size=50 * 1024 * 1024)
```

```python [Async]
from redis.asyncio import Redis
from hishel import AsyncRedisStorage

client = Redis(host="localhost", port=6379)
storage = AsyncRedisStorage(client=client, max_stream_size=50 * 1024 * 1024)
```

:::

## Custom Storages

To use another backend, subclass `AsyncBaseStorage` or `SyncBaseStorage` and pass your storage to any integration. The interface is deliberately small: cleanup, eviction and size limits are private to each backend.

```python
import uuid

from hishel import AsyncBaseStorage, Entry, Headers, Request, Response


class MyStorage(AsyncBaseStorage):
    async def create_entry(
        self,
        request: Request,
        response: Response,
        key: str,
        *,
        ttl: float | None = None,
        tti: float | None = None,
    ) -> Entry:
        """Create an entry, returned with a stream that saves the body as it is read."""
        ...

    async def get_entries(self, key: str) -> list[Entry]:
        """Return the entries stored under the key."""
        ...

    async def update_headers(self, id: uuid.UUID, headers: Headers) -> None:
        """Replace the stored response headers of an entry."""
        ...

    async def remove_entry(self, id: uuid.UUID) -> None:
        """Remove an entry so that new lookups no longer return it."""
        ...

    async def close(self) -> None:
        """Optional: release any resources."""
```

Your storage needs to guarantee the following:

- **`create_entry`:**
    - `get_entries` doesn't return the entry until its stream has been fully read.
    - A failure, here or while saving, stops caching, but doesn't fail whoever is reading the stream.
    - A body larger than `max_stream_size` isn't cached, but the reader still receives all of it.
    - `ttl` and `tti` fall back to `default_ttl` and `default_tti`. The base class's `__init__` stores these for you.
- **`get_entries`:**
    - Only complete, unexpired, non-removed entries are returned.
    - Returning an entry restarts its TTI.
    - A returned stream delivers the whole body or raises. It never ends early without an error.
    - A failure returns no entries instead of raising, so that the request goes to the server.
- **`update_headers` and `remove_entry`:** entries can disappear at any time, so these do nothing if the entry no longer exists. A failure doesn't raise either.
