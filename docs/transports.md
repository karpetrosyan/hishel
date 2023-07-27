Hishel provides **Transports** that can be used in place of the default httpx Transports to add a caching layer on top of them.

To begin, import them first.

``` python
>>> from hishel import CacheTransport
>>> from hishel import AsyncCacheTransport
```

Now, let’s try to make a request.

```python
>>> transport = CacheTransport(transport=httpx.HTTPTransport())
>>> request = httpx.Request("GET", "https://www.github.com")
>>> response = transport.handle_request(request)
>>> print(response)
<Response [301 Moved Permanently]>
```

As you can see, we also specified the **underlying transport**, which is required because hishel **respects your custom transports** and can work on top of them.

!!! note
    When the `CacheTransport` knows that the response will be the same, it will avoid making the same request a second time.

If we make the same request again, it will give us the previous response that it remembered, if the response is [considered cacheable according to RFC 9111](https://www.rfc-editor.org/rfc/rfc9111.html#name-storing-responses-in-caches).

```python
>>> response = transport.handle_request(request)  # without any network operation
>>> print(response)
```

!!! warning
    Hishel will load response data to **RAM** as long as it can take response from the cache and read the response content immediately.


## Create an HTTPX client using powerful transports.

When the transport is created, you will most likely need to create a client that will use it; this is how we can do that.

``` python
import httpx
import hishel

cache_transport = hishel.CacheTransport(transport=httpx.HTTPTransport())
client = httpx.Client(transport=cache_transport)
```

!!! tip
    If you've never used HTTPX's transports before, we recommend reading the [custom-transports](https://www.python-httpx.org/advanced/#custom-transports) first to fully understand what's going on here.

Our client will now make requests using the transport that we provided.

```python
client.get("https://www.github.com")  # cached
```

In most cases, `Hishel's CacheClient` would suffice for the end user; it actually uses `Hishel's CacheTransport` under the hood, so understanding this part will aid us in determining what the CacheClient does.

## Chaining the transports

If you already have a custom transport, say one that logs your requests and responses, you can chain those two transports together as follows.

``` python
from mylibrary import LogTransport
from hishel import CacheTransport
from httpx import Client

chained_transports = CacheTransport(transport=LogTransport())

client = Client(transport=chained_transports)
```

Now we have a client that can use cached responses and also log them.

You can also fully configure which backend your client should use for storing responses (rather than the default **filesystem backend**), or choose another **Serializer**, as described here.