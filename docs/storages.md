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

### Soft-Delete Buffer TTL

When an entry is removed, hishel soft-deletes it (marks `deleted_at`) and sets a short TTL on the underlying Redis keys so that any concurrent request still reading that entry's stream can finish before the data disappears. After the buffer expires, Redis cleans up the keys automatically.

The default buffer is 180 seconds (3 minutes). You can tune it:

::: code-group

```python [Sync]
from redis import Redis
from hishel import RedisStorage

client = Redis(host="localhost", port=6379)
storage = RedisStorage(client=client, soft_delete_ttl=60)
```

```python [Async]
from redis.asyncio import Redis
from hishel import AsyncRedisStorage

client = Redis(host="localhost", port=6379)
storage = AsyncRedisStorage(client=client, soft_delete_ttl=60)
```

:::

Soft-deleted entries are invisible to `get_entries`, so new requests will never receive them even while the keys are still present in Redis.

### Max Stream Size

Hishel streams response bodies into Redis chunk by chunk as the client reads them. Without a cap, a misbehaving or malicious upstream that keeps streaming bytes could push gigabytes into your Redis server before anyone notices.

`max_stream_size` (in bytes) bounds how much of a single response body hishel will write to Redis. Once the limit is exceeded, hishel drops the partial chunks it had already written, stops caching that response, and silently passes the remaining bytes through to the client — the request still succeeds, it just won't be cached.

The default is 10 MiB, which comfortably covers typical JSON, HTML, and small media responses. Tune it for your workload, or set it to `None` to disable the cap entirely:

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
