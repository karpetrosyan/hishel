---
icon: material/web
---

You can use the request `Cache-Control` directives defined in [RFC 9111](https://www.rfc-editor.org/rfc/rfc9111#name-request-directives) to make the cache behavior more explicit in some situations.

### only-if-cached

If this directive is present in the request headers, the cache should either use the cached response or return the 504 status code.

!!! note
    It is guaranteed that the client will not make any requests; instead, it will try to find a response from the cache that can be used for this request.

```python
>>> import hishel
>>> 
>>> client = hishel.CacheClient()
>>> response = client.get("https://example.com", headers=[("Cache-Control", "only-if-cached")])
>>> response
<Response [504 Gateway Timeout]>
```

or

```python
>>> import hishel
>>> 
>>> client = hishel.CacheClient()
>>> client.get("https://google.com")  # will cache
>>> response = client.get("https://google.com", headers=[("Cache-Control", "only-if-cached")])
>>> response
<Response [301 Moved Permanently]>
```

### max-age

If this directive is present in the request headers, the cache should ignore responses that are older than the specified number.

Example:

```python
import hishel

client = hishel.CacheClient()
client.get("https://example.com", headers=[("Cache-Control", "max-age=3600")])
```

### max-stale

If this directive is present in the request headers, the cache should ignore responses that have exceeded their freshness lifetime by more than the specified number of seconds.

```python
import hishel

client = hishel.CacheClient()
client.get("https://example.com", headers=[("Cache-Control", "max-stale=3600")])
```

### min-fresh

If this directive is present in the request headers, the cache should ignore responses that will not be fresh for at least the number of seconds specified.

```python
import hishel

client = hishel.CacheClient()
client.get("https://example.com", headers=[("Cache-Control", "min-fresh=3600")])
```

### no-cache

If this directive is present in the request headers, the cache should not use the response to this request unless it has been validated.

```python
import hishel

client = hishel.CacheClient()
client.get("https://example.com", headers=[("Cache-Control", "no-cache")])
```

### no-store

If this directive is present in the request headers, the cache should not save the response to this request.

```python
import hishel

client = hishel.CacheClient()
client.get("https://example.com", headers=[("Cache-Control", "no-store")])
```

