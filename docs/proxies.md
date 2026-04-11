# Proxies

Integrating with a new HTTP client mainly involves integrating the `AsyncCacheProxy` and `SyncCacheProxy` classes.
These classes intercept requests and responses, applying caching logic.

Proxies use the raw cache state machine with I/O implementations to fetch origin responses, store them in cache, and serve cached responses when possible.

Example:

```python
from hishel import AsyncCacheProxy, Request

async_cache_proxy = AsyncCacheProxy(lambda request: send_request(request))

response = async_cache_proxy.handle_request(Request(...))
```

When creating the proxy, we need to tell it how to fetch responses from the origin server, so as a first argument it accepts simple `Callable[Request, Response]` that will be used to fetch responses when needed.

You can pass policies to the proxy to customize its behavior, for example to tell explicitly what requests you want to cache instead of relaying on the HTTP caching specification:

```python
from hishel import AsyncCacheProxy, FilterPolicy

async_cache_proxy = AsyncCacheProxy(
    lambda request: send_request(request),
    policy=FilterPolicy(),
)

response = async_cache_proxy.handle_request(Request(...))
```

