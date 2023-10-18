`Hishel` provides powerful tools for improving your transports.

It analyzes your responses and saves them so they can be reused in the future.

It is very simple to integrate with your existing application; simply change the `Client` or `Transport` class that you are using.

## Clients and Transports

There are two ways to make the httpx library cacheable when working with it.

- Use the class provided by `Hishel` to completely replace `HTTPX's Client`.
- Simply use your existing httpx client along with `Hishel's transports`.

It is always advised to use the second option because it is more reliable and adaptable.


### Using the Clients

`Hishel` offers two classes for the first choice.

- `hishel.AsyncCacheClient` for `httpx.AsyncClient`
- `hishel.CacheClient` for `httpx.Client`

This implies that you can enable HTTP caching in your existing application by simply switching to the proper Client.

Examples:

```python
>>> import hishel
>>> 
>>> with hishel.CacheClient() as client:
>>>     client.get("https://example.com/cachable-endpoint")
>>>     response = client.get("https://example.com/cachable-endpoint") # from the cache!
```

Asynchronous Example:

```python
>>> with hishel.AsyncCacheClient() as client:
>>>     await client.get("https://example.com/cachable-endpoint")
>>>     response = await client.get("https://example.com/cachable-endpoint") # from the cache!
```

!!! warning
    The client classes that `Hishel` offers hide the constructor signature **in order to support all possible httpx versions.** This means that all httpx client fields are fully valid for those clients, but because they are hidden, **your IDE cannot suggest** which arguments you can pass. In other words, these classes merely use **\*args** and **\*\*kwargs** and add a few arguments for cache configuration.

This example also functions as long as the cache clients are fully compatible with the standard clients.

Example:

```python
client = hishel.CacheClient(
    proxies={
        "all://": "https://myproxy.com"
    },
    auth=("login", "password"),
    follow_redirects=True,
    http1=False,
    http2=True
)

client.get("https://example.com")
```

### Specifying the Client storage

Sometimes you may need to select storage rather than filesystem, and this is how you do it.

```python
import hishel

storage = hishel.RedisStorage()
with hishel.CacheClient(storage=storage) as client:
    client.get("https://example.com")
```

The responses are now saved in the [redis](https://redis.io/) database.

By default it will use...

- host: **localhost**
- port: **6379**.

Of course, you can explicitly set each configuration.

Example:

```python
import hishel
import redis

storage = hishel.RedisStorage(
    client=redis.Redis(
        host="192.168.0.85",
        port=8081,
    )
)

with hishel.CacheClient(storage=storage) as client:
    client.get("https://example.com")
```

!!! note
    Make sure `Hishel` has the redis extension installed if you want to use the Redis database.
    ``` shell
    $ pip install hishel[redis]
    ```

### Using the Transports

It is always preferable to use transports that `Hishel` offers for more dependable and predictable behavior.

We advise you to read the [transports documentation](https://www.python-httpx.org/advanced/#custom-transports) if you have never used `HTTPX's transports` before continuing.

We can divide the httpx library into two parts: the transports and the rest of the httpx library. Transports are the objects that are **actually making the request**.

For synchronous and asynchronous requests, `Hishel` offers two different transports.

- CacheTransport
- AsyncCacheTransport

`Hishel` always needs a transport to work on top of it, as long as he **respects the custom or third-party transports that are offered.**

Example:
```python
import hishel
import httpx

with httpx.HTTPTransport() as transport:
    with hishel.CacheTransport(transport=transport) as cache_transport:
        request = httpx.Request("GET", "https://example.com/cachable-endpoint")
        cache_transport.handle_request(request)
        response = cache_transport.handle_request(request) # from the cache!
```

#### Using the Transports with the Clients

If you have a transport, you can provide it to clients who will use it for underlying requests.

```python
import hishel
import httpx

cache_transport = hishel.CacheTransport(transport=httpx.HTTPTransport())
with httpx.Client(transport=cache_transport) as client:
    client.get("https://example.com/cachable-endpoint")
    response = client.get("https://example.com/cachable-endpoint")  # from the cache
```

#### Specifying the Transport storage

In the same way that we can choose the storage for our clients, we can do the same for our transport.

```python
import hishel

storage = hishel.RedisStorage()
with httpx.HTTPTransport() as transport:
    with hishel.CacheTransport(transport=transport, storage=storage) as cache_transport:
        request = httpx.Request("GET", "https://example.com/cachable-endpoint")
        cache_transport.handle_request(request)
```

#### Combining with the existing Transports

Assume you already have a custom transport adapted to your business logic that you use for all requests; this is how you can add the caching layer on top of it.

```python
import hishel
import httpx
from my_custom_transports import MyLovelyTransport

cache_transport = hishel.CacheTransport(transport=MyLovelyTransport())
with httpx.Client(transport=cache_transport) as client:
    client.get("https://example.com/cachable-endpoint")
    response = client.get("https://example.com/cachable-endpoint")  # from the cache
```

### Using the Connection Pool

`Hishel` also provides caching support for the httpcore library, which handles all of the low-level network staff for httpx.

You may skip this section if you do not use [HTTP Core](https://github.com/encode/httpcore).

Example:

```python
import hishel
import httpcore

with httpcore.ConnectionPool() as pool:
    with hishel.CacheConnectionPool(pool=pool) as cache_pool:
        cache_pool.get("https://example.com/cachable-endpoint")
        response = cache_pool.get("https://example.com/cachable-endpoint") # from the cache
```

#### Specifying the Connection Pool storage

In the same way that we can choose the storage for our clients and transports, we can do the same for our connection pools.

```python
import hishel
import httpcore

storage = hishel.RedisStorage()
with httpcore.ConnectionPool() as pool:
    with hishel.CacheConnectionPool(pool=pool, storage=storage) as cache_pool:
        cache_pool.get("https://example.com/cachable-endpoint")
        response = cache_pool.get("https://example.com/cachable-endpoint") # from the cache
```
