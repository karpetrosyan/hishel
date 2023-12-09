---
icon: material/apps
---

# Extensions

`HTTPX` provides an extension mechanism to allow additional information 
to be added to requests and to be returned in responses. `hishel` makes use
of these extensions to expose some additional cache-related options and metadata.
These extensions are available from either the `hishel.CacheClient` / 
`hishel.AsyncCacheClient` or a `httpx.Client` / `httpx.AsyncCacheClient`
using a `hishel` transport.

## Request extensions

### force_cache

If this extension is set to true, `Hishel` will cache the response even if response headers
would otherwise prevent caching the response.

For example, if the response has a `Cache-Control` header that contains a `no-store` directive, it will not cache the response unless the `force_cache` extension is set to true.

```python
>>> import hishel
>>> client = hishel.CacheClient()
>>> response = client.get("https://www.example.com/uncachable-endpoint", extensions={"force_cache": True})
```

### cache_disabled 

This extension temporarily disables the cache by passing appropriate RFC9111 headers to
ignore cached responses and to not store incoming responses. For example:

```python
>>> import hishel
>>> client = hishel.CacheClient()
>>> response = client.get("https://www.example.com/cacheable-endpoint", extensions={"cache_disabled": True})

```
This feature is more fully documented in the [User Guide](../userguide.md#temporarily-disabling-the-cache)

## Response extensions

### from_cache 

Every response from  will have a `from_cache` extension value that will be `True` when the response was retrieved
from the cache, and `False` when the response was received over the network.

```python
>>> import hishel
>>> client = hishel.CacheClient()
>>> response = client.get("https://www.example.com")
>>> response.extensions["from_cache"]
False
>>> response = client.get("https://www.example.com")
>>> response.extensions["from_cache"]
True
```

### cache_metadata

If `from_cache` is `True`, the response will also include a `cache_metadata` extension with additional information about 
the response retrieved from the cache. If `from_cache` is `False`, then `cache_metadata` will not
be present in the response extensions.

Example:

```python
>>> import hishel
>>> client = hishel.CacheClient()
>>> response = client.get("https://www.example.com/cacheable-endpoint")
>>> response.extensions
{
    ... # other extensions
    "from_cache": False
}
>>> response = client.get("https://www.example.com/cacheable-endpoint")
>>> response.extensions
{
    ... # other extensions
    "from_cache": True
    "cache_metadata" : {
        "cache_key': '1a4c648c9a61adf939eef934a73e0cbe',
        'created_at': datetime.datetime(2020, 1, 1, 0, 0, 0),
        'number_of_uses': 1,
    }
}
```

