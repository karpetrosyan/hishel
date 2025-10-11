---
icon: material/apps
---

Request and response metadata are attributes that hold data and can sometimes control caching behavior, attached to both request and response instances.

## Request

### hishel_ttl

When specified, hishel will remove the cached response after the given number of seconds.

Example:

```python
from hishel.beta.integrations.clients.httpx import SyncHishelClient

client = SyncHishelClient()

client.get("https://httpbin.org/get", extensions={"hishel_ttl": 3600})
```

### hishel_refresh_ttl_on_access

When `True`, accessing this entry refreshes its TTL. When `False`, the TTL remains fixed (default).

```python
from hishel.beta.integrations.clients.httpx import SyncHishelClient

client = SyncHishelClient()

client.get("https://httpbin.org/get", extensions={"hishel_refresh_ttl_on_access": True})
```

### hishel_spec_ignore

When `True`, hishel will ignore the caching specification for this request.

```python
from hishel.beta.integrations.clients.httpx import SyncHishelClient

client = SyncHishelClient()

client.get("https://httpbin.org/get", extensions={"hishel_spec_ignore": True})
```

## Response

### hishel_from_cache

Indicates whether the response was served from cache.

```python
from hishel.beta.integrations.clients.httpx import SyncHishelClient

client = SyncHishelClient()

response = client.get("https://httpbin.org/get")

response.extensions["hishel_from_cache"]
```

### hishel_revalidated

Indicates whether the response was revalidated with the origin server.

```python
from hishel.beta.integrations.clients.httpx import SyncHishelClient

client = SyncHishelClient()

response = client.get("https://httpbin.org/get")

response.extensions["hishel_revalidated"]
```

### hishel_spec_ignored

Indicates whether the caching specification was ignored for this response.

```python
from hishel.beta.integrations.clients.httpx import SyncHishelClient

client = SyncHishelClient()

response = client.get("https://httpbin.org/get", extensions={"hishel_spec_ignore": True})

response.extensions["hishel_spec_ignored"]
```

### hishel_stored

Indicates whether the response was stored in cache.

```python
from hishel.beta.integrations.clients.httpx import SyncHishelClient

client = SyncHishelClient()

response = client.get("https://httpbin.org/get")

response.extensions["hishel_stored"]
```
