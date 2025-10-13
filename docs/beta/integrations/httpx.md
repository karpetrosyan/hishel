---
icon: material/butterfly
---

Hishel provides an integration with httpx, making it easy to enable flexible caching in only a few seconds.

To get started, you can use `SyncHishelClient`(or `AsyncHishelClient` for async) as a drop-in replacement for an httpx client, like so:

```python
from hishel.beta.httpx import SyncHishelClient

client = SyncHishelClient()
client.get("https://hishel.com")
client.get("https://hishel.com")  # from cache
```

You can configure the client's storage and cache options like so:

```python
from hishel.beta import CacheOptions, SyncSqliteStorage
from hishel.beta.httpx import SyncHishelClient

client = SyncHishelClient(
    storage=SyncSqliteStorage(default_ttl=60 * 60 * 24), # 1 day
    cache_options=CacheOptions(supported_methods=["GET", "HEAD"]
)
```

As lower-level building blocks, Hishel also provides caching httpx transports that you can use to build your own clients or combine with existing transports.

```python
import httpx

from hishel.beta import CacheOptions, SyncSqliteStorage
from hishel.beta.httpx import SyncCacheTransport

client = httpx.Client(
    transport=SyncCacheTransport(
        transport=httpx.HTTPTransport(),
        storage=SyncSqliteStorage(default_ttl=60 * 60 * 24),  # 1 day
        cache_options=CacheOptions(supported_methods=["GET", "HEAD"]),
    )
)
```

## Metadata

Request and response metadata are attributes that hold data and can sometimes control caching behavior, attached to both request and response instances.

=== "extensions"
    ```python
    from hishel.beta.httpx import SyncHishelClient

    client = SyncHishelClient()

    client.get("https://httpbin.org/get", extensions={"hishel_ttl": 3600})
    ```
=== "headers"
    ```python
    from hishel.beta.httpx import SyncHishelClient

    client = SyncHishelClient()

    client.get("https://httpbin.org/get", headers={"x-hishel-ttl": "3600"})
    ```

You can find the full list of supported metadata attributes in the [metadata reference](../metadata.md) section.