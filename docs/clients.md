


Hishel provides **Clients** that can be used in place of the `HTTPX's Client` to add a caching layer on top of the default ones.

To begin, import them first.

``` python
>>> from hishel import CacheClient
>>> from hishel import AsyncCacheClient
```

Now, let’s try to make a request.

```python
>>> client = CacheClient()
>>> response = client.get("https://www.github.com")
>>> print(response)
<Response [301 Moved Permanently]>
```

!!! note
    When the `CacheClient` knows that the response will be the same, it will avoid making the same request a second time.

If we make the same request again, it will give us the previous response that it remembered, if the response is [considered cacheable according to RFC 9111](https://www.rfc-editor.org/rfc/rfc9111.html#name-storing-responses-in-caches).

```python
>>> response = client.get("https://www.github.com")  # without any network operation
>>> print(response)
```

!!! warning
    Hishel will load response data to **RAM** as long as it can take response from the cache and read the response content immediately.

Because the `CacheClient` is a subclass of `httpx.Client`, all of the methods that you used with `httpx.Client` will be available to this client.

You can also fully configure which backend your client should use for storing responses (rather than the default **filesystem backend**), or choose another **Serializer**, as described here.