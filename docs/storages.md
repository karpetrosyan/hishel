# Storages

Hishel comes with a default storage backend that uses SQLite for cached response CRUD operations.

If you want to use a different storage backend, you can implement the base storage interface and use it with `AsyncCacheProxy`, `SyncCacheProxy`, or any integration that accepts a storage.

## SQLite Storage

The default storage puts all cached responses in a single SQLite database file.
It handles streams without loading them fully into memory — instead, it stores them in chunks and reads them back on demand, also without loading them fully into memory.

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

### Custom Path

You can pass a path to the database file, or it will be created in the current working directory at `.cache/hishel/hishel_cache.db`:

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

### Default Entry TTL

You can set a default TTL for all entries stored in the cache. This value is used when the request does not specify its own TTL:

::: code-group

```python [Sync]
from hishel import SyncSqliteStorage

storage = SyncSqliteStorage(default_ttl=3600)
```

```python [Async]
from hishel import AsyncSqliteStorage

storage = AsyncSqliteStorage(default_ttl=3600)
```

:::

Storage also respects the `hishel_ttl` request metadata, which can be used to set a custom TTL for a specific request, overriding the storage default.

### Refreshing TTL on Access

In some cases you may want to refresh the TTL of a cached entry every time it is accessed, so that it stays in cache as long as it is frequently used.
You can enable this behavior by setting `refresh_ttl_on_access` to `True`:

::: code-group

```python [Sync]
from hishel import SyncSqliteStorage

storage = SyncSqliteStorage(refresh_ttl_on_access=True)
```

```python [Async]
from hishel import AsyncSqliteStorage

storage = AsyncSqliteStorage(refresh_ttl_on_access=True)
```

:::

You can also control this on a per-request basis by setting the `hishel_refresh_ttl_on_access` request metadata to `True` or `False`, which overrides the storage default.

## Redis Storage

Redis storage provides fast, in-memory (or persistent) caching backed by a Redis server.

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

### Default Entry TTL

You can set a default TTL for all entries stored in Redis. This value is used when the request does not specify its own TTL:

::: code-group

```python [Sync]
from redis import Redis
from hishel import RedisStorage

client = Redis(host="localhost", port=6379)
storage = RedisStorage(client=client, ttl=3600)
```

```python [Async]
from redis.asyncio import Redis
from hishel import AsyncRedisStorage

client = Redis(host="localhost", port=6379)
storage = AsyncRedisStorage(client=client, ttl=3600)
```

:::

Storage also respects the `hishel_ttl` request metadata, which can be used to set a custom TTL for a specific request, overriding the storage default.
