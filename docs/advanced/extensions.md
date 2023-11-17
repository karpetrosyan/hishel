---
icon: material/apps
---

`HTTPX` provides an extension mechanism to allow additional information 
to be added to requests and to be returned in responses. `hishel` makes use
of these extensions to expose some additional cache-related options and metadata.
These extensions are available from either the `hishel.CacheClient` / 
`hishel.AsyncCacheClient` or a `httpx.Client` / `httpx.AsyncCacheClient`
using a `hishel` transport.

## Request extensions

`hishel` currently provides only one extension on requests - `cache_disabled`. This
extension temporarily disables the cache by passing appropriate RFC911 headers to
ignore cached responses and to not store incoming responses. For example:

```python
>>> import hishel
>>> client = hishel.CacheClient()
>>> response = client.get("https://www.example.com/cacheable-endpoint", extensions={"cache_disabled": True})

```
This feature is more fully documented in the [User Guide](/userguide/#temporarily-disabling-the-cache)

## Response extensions

`hishel` provides two extensions on responses that provide additional information regarding whether a response was returned from the cache, and additional metadata about the cached response when a response is returned from the cache. 

Every response from a `hishel.CacheClient` / `hishel.AsyncCacheClient` will have
a `from_cache` extension value that will be `True` when the response was retrieved
from the cache, and `False` when the response was received over the network.

If `from_cache` is `True`, the extensions will also have a dictionary called
`cache_metadata` with three keys:
 - `cache_key` - The key used in the cache for the response
 - `created_at` - A `datetime.datetime` object indicating when the cached response was created
 - `number_of_uses` - a counter that indicates how many times this response was retrieved from the cache.

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

