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
- `hishel.CacheClient` `for httpx.Client`

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


## Storages

When using `Hishel`, you have complete control over the configuration of how the responses should be stored. You can select the [serializer](#serializers) and storage on your own.

This section contains examples of how to use the storages.

### Using the Filesystem storage

To explicitly specify the storage, we should create it first and pass it to the HTTP caching class.

Example:
```python
import hishel

storage = hishel.FileStorage()
client = hishel.CacheClient(storage=storage)
```

Or if you are using Transports:

```python
import hishel
import httpx

storage = hishel.FileStorage()
transport = hishel.CacheTransport(transport=httpx.HTTPTransport())
```

#### Specifying the storage directory

If the responses are saved in the filesystem, there should be a directory that contains our responses.

By default it's `.cache/hishel`.

If you want to change the directory, do so as follows.

```python
import hishel

storage = hishel.FileStorage(base_path="/home/test/my_cache_dir")
```

#### Specifying the responses ttl in FileStorage

You can explicitly specify the ttl for stored responses in this manner.

```python
import hishel

storage = hishel.FileStorage(ttl=3600)
```

If you do this, `Hishel` will delete any stored responses whose ttl has expired.
In this example, the stored responses were limited to 1 hour.

### Using the Redis storage

`Hishel` includes built-in redis support, allowing you to store your responses in redis.

Example:

```python
import hishel

storage = hishel.RedisStorage()
client = hishel.CacheClient(storage=storage)
```

Or if you are using Transports:

```python
import hishel
import httpx

storage = hishel.RedisStorage()
client = hishel.CacheTransport(transport=httpx.HTTPTransport())
```

#### Specifying the host and port for redis.

If you need to connect somewhere other than localhost, this is how you can do it.

```python
import hishel
import redis

storage = hishel.RedisStorage(
    client=redis.Redis(
        host="192.168.0.85",
        port=8081,
    )
)
```


#### Specifying the responses ttl in RedisStorage

You can explicitly specify the ttl for stored responses in this manner.

```python
import hishel

storage = hishel.RedisStorage(ttl=3600)
```

If you do this, `Hishel` will delete any stored responses whose ttl has expired.
In this example, the stored responses were limited to 1 hour.

## Serializers

Serializers are a component of [storages](#storages) that simply serialize and de-serialize responses.
Hishel will use JSONSerializer by default, but you can explicitly specify a serializer or even write your own.

Example of the serialized responses:

=== "JSON"

    ``` json
    {
        "response": {
            "status": 301,
            "headers": [
                [
                    "Content-Length",
                    "0"
                ],
                [
                    "Location",
                    "https://github.com/"
                ]
            ],
            "content": "",
            "extensions": {
                "http_version": "HTTP/1.1",
                "reason_phrase": "Moved Permanently"
            }
        },
        "request": {
            "method": "GET",
            "url": "https://www.github.com/",
            "headers": [
                [
                    "Host",
                    "www.github.com"
                ],
                [
                    "Accept",
                    "*/*"
                ],
                [
                    "Accept-Encoding",
                    "gzip, deflate"
                ],
                [
                    "Connection",
                    "keep-alive"
                ],
                [
                    "User-Agent",
                    "python-httpx/0.24.1"
                ]
            ],
            "extensions": {
                "timeout": {
                    "connect": 5.0,
                    "read": 5.0,
                    "write": 5.0,
                    "pool": 5.0
                }
            }
        },
        "metadata": {
            "cache_key": "71b46af84732856e5c16d503b655fcd0",
            "number_of_uses": 0,
            "created_at": "Mon, 21 Aug 2023 05:22:20 GMT"
        }
    }
    ```

=== "Yaml"

    ``` yaml
    response:
      status: 301
      headers:
      - - Content-Length
        - '0'
      - - Location
        - https://github.com/
      content: ''
      extensions:
        http_version: HTTP/1.1
        reason_phrase: Moved Permanently
    request:
      method: GET
      url: https://www.github.com/
      headers:
      - - Host
        - www.github.com
      - - Accept
        - '*/*'
      - - Accept-Encoding
        - gzip, deflate
      - - Connection
        - keep-alive
      - - User-Agent
        - python-httpx/0.24.1
      extensions:
        timeout:
          connect: 5.0
          read: 5.0
          write: 5.0
          pool: 5.0
    metadata:
      cache_key: 71b46af84732856e5c16d503b655fcd0
      number_of_uses: 0
      created_at: Mon, 21 Aug 2023 05:22:20 GMT

    ```


### Using the JSONSerializer

Example:
```python
import hishel

serializer = hishel.JSONSerializer()
storage = hishel.FileStorage(serializer=serializer)
```

Because serializers are supported by all of the built-in `hishel` [storages](#storages), you can pass serializers to any of them.

Example:
```python
import hishel

serializer = hishel.JSONSerializer()
storage = hishel.RedisStorage(serializer=serializer)
```

### Using the YAMLSerizlier

Example:
```python
import hishel

serializer = hishel.YAMLSerializer()
storage = hishel.FileStorage(serializer=serializer)
```

!!! note
    Make sure `Hishel` has the yaml extension installed if you want to use the YAMLSerializer.
    ``` shell
    $ pip install hishel[yaml]
    ```

### Using the PickleSerializer

Example:
```python
import hishel

serializer = hishel.PickleSerializer()
storage = hishel.FileStorage(serializer=serializer)
```

## Controllers

`Hishel` provides the `Controllers`, which allow you to fully customize how the cache works at the specification level.

You can choose which parts of [RFC 9111](https://www.rfc-editor.org/rfc/rfc9111.html) to ignore. For example, this is useful when you want to ensure that your client does **not use stale responses** even if they are **acceptable from the server.**

### Specifying cachable HTTP methods

You can specify which HTTP methods `Hishel` should cache.

Example:

```python
import hishel

controller = hishel.Controller(cacheable_methods=["GET", "PUT"])
client = hishel.CacheClient(controller=controller)
```

!!! note
    `Hishel` will only cache GET methods if the cachable methods are not explicitly specified.

### Specifying cachable status codes

If you only want to cache specific status codes, do so.

Example:

```python
import hishel

controller = hishel.Controller(cacheable_status_codes=[301, 308])
client = hishel.CacheClient(controller=controller)
```

!!! note
    If the cachable status codes are not explicitly specified, `Hishel` will only cache status codes **200, 301, and 308**.


### Allowing heuristics.

You can enable heuristics calculations, which are disabled by default.

Example:

```python
import hishel

controller = hishel.Controller(allow_heuristics=True)
client = hishel.CacheClient(controller=controller)

```

!!! tip
    If you're not familiar with `Heuristics Caching`, you can [read about it in the specification](https://www.rfc-editor.org/rfc/rfc9111.html#name-calculating-heuristic-fresh).

### Allowing stale responses.

Some servers allow the use of stale responses if they cannot be re-validated or the client is disconnected from the server. Clients MAY use stale responses in such cases, but this behavior is disabled by default in `Hishel`.

Example:

```python
import hishel

controller = hishel.Controller(allow_stale=True)
client = hishel.CacheClient(controller=controller)
```

!!! tip
    `Hishel` will attempt to use stale response only if the client is unable to connect to the server to make a request. You can enable stale responses to receive responses even if your internet connection is lost.

### Specifying revalidation behavior.

Responses are revalidated by default when they become stale; however, you can always revalidate the responses if you wish.

Example:

```python
import hishel

controller = hishel.Controller(always_revalidate=True)
client = hishel.CacheClient(controller=controller)
```

!!! note
    Because we already have the response body in our cache, revalidation is very quick.


## Request Headers

In addition, you can use the request `Cache-Control` directives defined in [RFC 9111](https://www.rfc-editor.org/rfc/rfc9111#name-request-directives) to make the cache behavior more explicit in some situations.

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