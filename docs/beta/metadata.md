---
icon: material/apps
---

Request and response metadata are attributes that hold data and can sometimes control caching behavior, attached to both request and response instances.

## Request

### hishel_ttl

When specified, hishel will remove the cached response after the given number of seconds.

Example:

=== "httpx"
    ```python
    from hishel.beta.httpx import SyncHishelClient

    client = SyncHishelClient()

    client.get("https://httpbin.org/get", extensions={"hishel_ttl": 3600})
    ```
=== "requests"
    ```python
    import requests

    from hishel.beta.requests import CacheAdapter

    session = requests.Session()
    adapter = CacheAdapter()

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    session.get("https://httpbin.org/get", headers={"x-hishel-ttl": 3600})
    ``` 

### hishel_refresh_ttl_on_access

When `True`, accessing this entry refreshes its TTL. When `False`, the TTL remains fixed (default).

=== "httpx"
    ```python
    from hishel.beta.httpx import SyncHishelClient

    client = SyncHishelClient()

    client.get("https://httpbin.org/get", extensions={"hishel_refresh_ttl_on_access": True})
    ```
=== "requests"
    ```python
    import requests

    from hishel.beta.requests import CacheAdapter

    session = requests.Session()
    adapter = CacheAdapter()

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    session.get("https://httpbin.org/get", headers={"x-hishel-refresh-ttl-on-access": "true"})
    ```

### hishel_spec_ignore

When `True`, hishel will ignore the caching specification for this request.

=== "httpx"
    ```python
    from hishel.beta.httpx import SyncHishelClient

    client = SyncHishelClient()

    client.get("https://httpbin.org/get", extensions={"hishel_spec_ignore": True})
    ```
=== "requests"
    ```python
    import requests

    from hishel.beta.requests import CacheAdapter

    session = requests.Session()
    adapter = CacheAdapter()

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    session.get("https://httpbin.org/get", headers={"x-hishel-spec-ignore": "true"})
    ```

### hishel_body_key

When enabled, the request body is included in the cache key generation. This is useful for caching POST or QUERY requests with different bodies.

## Response

### hishel_from_cache

Indicates whether the response was served from cache.

=== "httpx"
    ```python
    from hishel.beta.httpx import SyncHishelClient

    client = SyncHishelClient()

    response = client.get("https://httpbin.org/get")

    response.extesions["hishel_from_cache"]
    ```
=== "requests"
    ```python
    import requests

    from hishel.beta.requests import CacheAdapter

    session = requests.Session()
    adapter = CacheAdapter()

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    response = session.get("https://httpbin.org/get")

    response.headers["x-hishel-from-cache"]
    ```

### hishel_revalidated

Indicates whether the response was revalidated with the origin server.

=== "httpx"
    ```python
    from hishel.beta.httpx import SyncHishelClient

    client = SyncHishelClient()

    response = client.get("https://httpbin.org/get")

    response.extensions["hishel_revalidated"]
    ```
=== "requests"
    ```python
    import requests

    from hishel.beta.requests import CacheAdapter

    session = requests.Session()
    adapter = CacheAdapter()

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    response = session.get("https://httpbin.org/get")

    response.headers["x-hishel-revalidated"]
    ```

### hishel_spec_ignored

Indicates whether the caching specification was ignored for this response.

=== "httpx"
    ```python
    from hishel.beta.httpx import SyncHishelClient

    client = SyncHishelClient()

    response = client.get("https://httpbin.org/get", extensions={"hishel_spec_ignore": True})

    response.extensions["hishel_spec_ignored"]
    ```
=== "requests"
    ```python
    import requests

    from hishel.beta.requests import CacheAdapter

    session = requests.Session()
    adapter = CacheAdapter()

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    response = session.get("https://httpbin.org/get", headers={"x-hishel-spec-ignore": "true"})

    response.headers["x-hishel-spec-ignored"]
    ```

### hishel_stored

Indicates whether the response was stored in cache.

=== "httpx"
    ```python
    from hishel.beta.httpx import SyncHishelClient

    client = SyncHishelClient()

    response = client.get("https://httpbin.org/get")

    response.extensions["hishel_stored"]
    ```
=== "requests"
    ```python
    import requests

    from hishel.beta.requests import CacheAdapter

    session = requests.Session()
    adapter = CacheAdapter()

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    response = session.get("https://httpbin.org/get")

    response.extensions["x-hishel-stored"]
    ```
