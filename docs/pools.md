Hishel's Pools are yet another effective tool for making your httpcore application much faster and more efficient.

To begin, import them first.

``` python
>>> from hishel import CacheConnectionPool
>>> from hishel import AsyncCacheConnectionPool
```

Now, let’s try to make a request.

```python
>>> pool = CacheConnectionPool(pool=httpcore.ConnectionPool())
>>> response = pool.request("GET", "https://www.github.com")
>>> print(response)
<Response [301 Moved Permanently]>
```

As you can see, we also specified the **underlying pool**, which is required because hishel **respects your custom pools** and can work on top of them.

!!! note
    When the `CacheConnectionPool` knows that the response will be the same, it will avoid making the same request a second time.

If we make the same request again, it will give us the previous response that it remembered, if the response is [considered cacheable according to RFC 9111](https://www.rfc-editor.org/rfc/rfc9111.html#name-storing-responses-in-caches).

```python
>>> response = pool.request("GET", "https://www.github.com")  # without any network operation
>>> print(response)
```

!!! warning
    Hishel will load response data to **RAM** as long as it can take response from the cache and read the response content immediately.


## Chaining the connection pools

If you already have a custom connection pool, say one that logs your requests and responses, you can chain those two connection pools together as follows.

``` python
from mylibrary import LogConnectionPool
from hishel import CacheConnectionPool

chained_pools = CacheConnectionPool(pool=LogConnectionPool())

```

Now we have a connection pool that can use cached responses and also log them.

You can also fully configure which backend your client should use for storing responses (rather than the default **filesystem backend**), or choose another **Serializer**, as described here.