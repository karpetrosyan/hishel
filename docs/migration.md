# Migrating from 1.x

Hishel 2.0 is a redesign with a smaller API. Policies, proxies and metadata are gone, and the storages have changed. This page covers what to change in your code, and what happens to the data you have already cached.

::: warning
[Zapros](/zapros) currently integrates with Hishel 1.x. If you use it, stay on 1.x with `pip install "hishel<2"`.
:::

## Find What Needs Changing

Search your code for everything that was removed. This also finds the old default database name, `hishel_cache.db`. The default is now `hishel_cache_v2.db`, so this only matters if you pass that name yourself:

```bash
grep -rniE 'hishel_[a-z]+|x-hishel-|(Specification|Filter|Cache)Policy|BaseFilter|CacheProxy|refresh_ttl_on_access' --include='*.py' .
```

Most of the old API raises an error as soon as you use it, including `policy=`, the removed imports and the old storage options. Two things fail silently, so make sure you remove them:

- `hishel_*` extensions on HTTPX requests are ignored.
- `X-Hishel-*` request headers are no longer read, and are **sent to the server** along with the rest of your headers. The exceptions are `X-Hishel-Ttl` and `X-Hishel-Tti` on Requests, which still work.

## The Default Mode Changed

This is the change most likely to catch you out, because your code keeps running without it.

Hishel 1.x followed RFC 9111 by default. HTTPX and Requests now default to a simpler mode, which ignores HTTP caching headers and keeps every successful `GET` and `HEAD` response until the storage expires it. That includes `no-store` and `private` responses, and the default SQLite storage never expires them on its own.

To keep the behaviour of 1.x, turn on RFC mode:

::: code-group

```python [1.x]
from hishel.httpx import SyncCacheClient

client = SyncCacheClient()
```

```python [2.0]
from hishel.httpx import SyncCacheClient

client = SyncCacheClient(rfc=True)
```

:::

`rfc` is accepted in the same way by `AsyncCacheClient`, by the cache transports and by `CacheAdapter`. `ASGICacheMiddleware` still follows RFC 9111 by default. See [Caching Modes](/httpx#caching-modes) for how the two modes differ.

## Policies

The `policy` argument is replaced by `rfc`.

### `SpecificationPolicy`

Pass its `CacheOptions` directly. The options themselves haven't changed.

::: code-group

```python [1.x]
from hishel import CacheOptions, SpecificationPolicy
from hishel.httpx import SyncCacheClient

policy = SpecificationPolicy(cache_options=CacheOptions(shared=False))
client = SyncCacheClient(policy=policy)
```

```python [2.0]
from hishel import CacheOptions
from hishel.httpx import SyncCacheClient

client = SyncCacheClient(rfc=CacheOptions(shared=False))
```

:::

### `FilterPolicy`

A `FilterPolicy` without filters is closest to the new default mode, but that mode caches less. `FilterPolicy` also stored other methods and statuses, such as `POST` responses and 404s. The default mode only stores successful `GET` and `HEAD` responses, other than 206.

::: code-group

```python [1.x]
from hishel import FilterPolicy
from hishel.httpx import SyncCacheClient

client = SyncCacheClient(policy=FilterPolicy())
```

```python [2.0]
from hishel.httpx import SyncCacheClient

client = SyncCacheClient()
```

:::

There are no filters in 2.0. To choose which requests are cached, send them through different transports:

```python
import httpx
from hishel.httpx import SyncCacheTransport


class CacheReportsOnly(httpx.BaseTransport):
    def __init__(self):
        self.plain = httpx.HTTPTransport()
        self.cached = SyncCacheTransport(next_transport=self.plain)

    def handle_request(self, request):
        transport = self.cached if request.url.path.startswith("/reports/") else self.plain
        return transport.handle_request(request)

    def close(self):
        self.cached.close()


client = httpx.Client(transport=CacheReportsOnly())
```

Response filters have no direct replacement. In RFC mode, the server's headers decide what is stored.

## Metadata

The `hishel_*` extensions and `X-Hishel-*` headers are gone, on both requests and responses, other than the two expiry headers on Requests.

### Request Metadata

- `hishel_ttl`: With HTTPX, use `extensions={"caching": {"ttl": 3600}}`. With Requests, `X-Hishel-Ttl` still works. To set it for everything, use `default_ttl` on the storage.
- `hishel_spec_ignore`: Use `extensions={"caching": {"rfc": False}}` with HTTPX, or `CacheAdapter(rfc=False)` with Requests.
- `hishel_refresh_ttl_on_access`: Use a TTI, as an entry then expires when it hasn't been used for that long, so using it keeps it alive. With HTTPX, that is `extensions={"caching": {"tti": 3600}}`. With Requests, send `X-Hishel-Tti`. To set it for everything, use `default_tti` on the storage.
- `hishel_body_key`: Removed. You can set your own cache key, with the `key` in the [`caching` extension](/httpx#per-request-configuration) or the [`X-Hishel-Key` header](/requests#per-request-cache-key), but responses to `POST` and other unsafe methods are still never served from the cache. So GraphQL and search requests sent with `POST` can't be cached, and you should stay on 1.x if you rely on this.

### Response Metadata

`hishel_from_cache`, `hishel_revalidated`, `hishel_stored` and `hishel_created_at` have no replacement, so responses no longer say what the cache did.

In RFC mode, a response served from the cache has an `Age` header, as the specification requires. In the default mode, nothing distinguishes a hit from a miss. To measure your hit rate, wrap the `next_transport` of a cache transport and count the requests that reach it.

## Storages

The storages are still `SyncSqliteStorage`, `AsyncSqliteStorage`, `RedisStorage` and `AsyncRedisStorage`, but some options have changed:

- `refresh_ttl_on_access` is removed from the SQLite storages. It already had no effect in 1.x, so you can delete it.
- `ttl` on the Redis storages is now `default_ttl`.
- Everything after `client` on the Redis storages is now keyword-only, so `RedisStorage(client, 3600)` becomes `RedisStorage(client, default_ttl=3600)`.

Some behaviour is new too:

- **SQLite has a size limit:** `max_size` defaults to 1 GiB, and the least recently used entries are removed beyond that. Pass `max_size=None` for no limit, as in 1.x.
- **SQLite can limit body size:** `max_stream_size` is now available, as it already was on Redis.
- **Every storage can expire idle entries:** `default_tti` is new. See [Expiring Entries](/storages#expiring-entries).
- **Redis needs version 7 or newer.**

### Your Existing Cache

Nothing already cached carries over, so expect more requests to reach the server just after you upgrade. No manual steps are needed:

- **SQLite:** 2.0 uses a new default file, `hishel_cache_v2.db`, and doesn't touch `hishel_cache.db`. So both versions can run side by side during a rolling deployment, and rolling back needs no cleanup. Once you're done with 1.x, you can delete the old file.
- **Redis:** 1.x entries can no longer be found, because cache keys have changed. They stay in Redis until their own TTL runs out.

::: warning
This only covers the default path. If you pass a `database_path` or `connection=` that holds a 1.x cache, the storage raises a `RuntimeError` on first use and leaves it as it is, so give 2.0 a new one.
:::

## Integrations

The module paths are unchanged: `hishel.httpx`, `hishel.httpx2`, `hishel.requests`, `hishel.asgi` and `hishel.fastapi`.

- **HTTPX and HTTPX2:** use `rfc` instead of `policy`, as above.
- **Requests:** `CacheAdapter` also takes `rfc` instead of `policy`. The only per-request settings are the [expiry](/requests#per-request-expiry) and [cache key](/requests#per-request-cache-key) headers. For the rest, [mount another adapter](/requests#different-settings-for-different-urls) on a more specific prefix.
- **ASGI:** `ASGICacheMiddleware` takes `rfc` instead of `policy`. It still follows RFC 9111 by default.
- **FastAPI:** the `cache()` dependency hasn't changed.

## Custom Integrations and Storages

`AsyncCacheProxy` and `SyncCacheProxy` are removed. Drive the state machine yourself, as shown in [Writing an Integration](/sans-io#writing-an-integration).

`Request` and `Response` no longer have `metadata`, and `Request` no longer has `stream`. The models `RequestMetadata`, `ResponseMetadata` and `EntryMeta` are removed, and `Entry` now only has `id`, `request` and `response`.

If you wrote your own storage, the interface is smaller:

- `create_entry` now takes `ttl` and `tti` instead of `id_`.
- `update_entry` is replaced by `update_headers(id, headers)`.
- `refresh_entry_ttl`, `mark_pair_as_deleted`, `is_soft_deleted` and `is_safe_to_hard_delete` are removed from the base class. Expiry and cleanup are now private to each storage.

See [Custom Storages](/storages#custom-storages) for the full interface.
