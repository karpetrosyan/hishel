---
icon: material/brain
---

`Hishel` provides the `Controllers`, which allow you to fully customize how the cache works at the specification level.

You can choose which parts of [RFC 9111](https://www.rfc-editor.org/rfc/rfc9111.html) to ignore. For example, this is useful when you want to ensure that your client does **not use stale responses** even if they are **acceptable from the server.**

### Force caching

If you only need to cache responses without validating the headers and following RFC9111 rules, simply set the `force_cache` property to true.

Example:

```python
import hishel

controller = hishel.Controller(force_cache=True)
client = hishel.CacheClient(controller=controller)
```

!!! note
    [force_cache](extensions.md#force_cache) extension will always overwrite the controller's force_cache property.

### Cachable HTTP methods

You can specify which HTTP methods `Hishel` should cache.

Example:

```python
import hishel

controller = hishel.Controller(cacheable_methods=["GET", "POST"])
client = hishel.CacheClient(controller=controller)
```

!!! note
    `Hishel` will only cache `GET` methods if the cachable methods are not explicitly specified.

### Cachable status codes

If you only want to cache specific status codes, do so.

Example:

```python
import hishel

controller = hishel.Controller(cacheable_status_codes=[301, 308])
client = hishel.CacheClient(controller=controller)
```

!!! note
    If the cachable status codes are not explicitly specified, `Hishel` will only cache status codes **200, 301, and 308**.


### Allowing heuristics

You can enable heuristics calculations, which are disabled by default.

Example:

```python
import hishel

controller = hishel.Controller(allow_heuristics=True)
client = hishel.CacheClient(controller=controller)

```

`Hishel` is very conservative about what status codes are permitted
to be heuristically cacheable. When `allow_heuristics` is enabled,
`Hishel` will only cache responses having status codes 200, 301, and 308. In contrast, RFC 9111 specifies that many more responses can be heuristically cacheable, specifically 200, 203, 204, 206, 300, 301, 308, 404, 405, 410, 414, and 501.

If you would prefer heuristic caching to the fullest extent permitted by
RFC 9111, then pass `HEURISTICALLY_CACHEABLE_STATUS_CODES` to `cacheable_status_codes`:

```python
import hishel

controller = hishel.Controller(
    allow_heuristics=True,
    cacheable_status_codes=hishel.HEURISTICALLY_CACHEABLE_STATUS_CODES
    )
client = hishel.CacheClient(controller=controller)

```

!!! tip
    If you're not familiar with `Heuristics Caching`, you can [read about it in the specification](https://www.rfc-editor.org/rfc/rfc9111.html#name-calculating-heuristic-fresh).

### Preventing caching of private responses

If you want `Hishel` to act as a _shared_ cache, you need to prevent it from caching responses with the `private` directive.

Example:

```python
import hishel

controller = hishel.Controller(cache_private=False)
client = hishel.CacheClient(controller=controller)
```

!!! note
    Servers may prohibit only some headers from being stored in a shared cache by sending a header such as `Cache-Control: private=set-cookie`. However, `Hishel` with `cache_private=False` will still not cache the response, at all.

### Allowing stale responses

Some servers allow the use of stale responses if they cannot be re-validated or the client is disconnected from the server. Clients MAY use stale responses in such cases, but this behavior is disabled by default in `Hishel`.

Example:

```python
import hishel

controller = hishel.Controller(allow_stale=True)
client = hishel.CacheClient(controller=controller)
```

!!! tip
    `Hishel` will attempt to use stale response only if the client is unable to connect to the server to make a request. You can enable stale responses to receive responses even if your internet connection is lost.

### Specifying revalidation behavior

Responses are revalidated by default when they become stale; however, you can always revalidate the responses if you wish.

Example:

```python
import hishel

controller = hishel.Controller(always_revalidate=True)
client = hishel.CacheClient(controller=controller)
```

!!! note
    Because we already have the response body in our cache, revalidation is very quick.

### Custom cache keys

By default, `Hishel` generates cache keys as a hash of the request method and url.
However, you can customize cache key creation by writing a function with the signature `Callable[[httpcore.Request], str]` and passing it to the controller.

Example:

```python
import hishel
import httpcore
from hishel._utils import generate_key

def custom_key_generator(request: httpcore.Request, body: bytes):
    key = generate_key(request, body)
    method = request.method.decode()
    host = request.url.host.decode()
    return f"{method}|{host}|{key}"

controller = hishel.Controller(key_generator=custom_key_generator)
client = hishel.CacheClient(controller=controller)

client.get("https://hishel.com")
```

Instead of just the `hashed_value`, the key now has the format `method|host|hashed_value`.

!!! note
    Cache keys are used to store responses in storages, such as filesystem storage, which will use the cache key to create a file with that value.
    You can write your own cache key implementation to have more meaningful file names and simplify cache monitoring.

=== "Before"

    ```
    📁 root
    └─╴📁 .cache
       └─╴📁 hishel
          └─╴📄 41ebb4dd16761e94e2ee36b71e0d916e
    ```

=== "After"

    ```
    📁 root
    └─╴📁 .cache
       └─╴📁 hishel
          └─╴📄 GET|hishel.com|41ebb4dd16761e94e2ee36b71e0d916e
    ```

   
