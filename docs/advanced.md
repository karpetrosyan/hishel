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

!!! note
    Make sure `Hishel` has the redis extension installed if you want to use the `RedisStorage`.
    ``` shell
    $ pip install hishel[redis]
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

### Using the SQLite storage

`Hishel` includes built-in [sqlite](https://www.sqlite.org/index.html) support, allowing you to store your responses in sqlite database.

Example:

```python
import hishel

storage = hishel.SQLiteStorage()
client = hishel.CacheClient(storage=storage)
```

Or if you are using Transports:

```python
import hishel
import httpx

storage = hishel.SQLiteStorage()
client = hishel.CacheTransport(transport=httpx.HTTPTransport())
```

!!! note
    Make sure `Hishel` has the sqlite extension installed if you want to use the `AsyncSQLiteStorage`.
    ``` shell
    $ pip install hishel[sqlite]
    ```

#### Specifying the sqlite connection to use.

If you want more control over the underlying sqlite connection, you can explicitly pass it.

```python
import hishel
import sqlite3

client = hishel.CacheClient(
    storage=hishel.SQLiteStorage(connection=sqlite3.connect("my_db_path", timeout=5))
)
```

#### Specifying the responses ttl in SQLiteStorage.

You can explicitly specify the ttl for stored responses in this manner.

```python
import hishel

storage = hishel.SQLiteStorage(ttl=3600)
```

If you do this, `Hishel` will delete any stored responses whose ttl has expired.
In this example, the stored responses were limited to 1 hour.


## Which storage is the best?

Let's start with some basic benchmarks to see which one is the fastest.

So there are the results of the benchmarks, where we simply sent 1000 synchronous requests to [hishel.com](https://hishel.com).

| Storage           | Time                          |
| -----------       | ---- |
| `FileStorage`     | 0.4s |
| `SQLiteStorage`   | 2s   |
| `RedisStorage`    | 0.5s |


!!! note
    It is important to note that the results may differ for your environment due to a variety of factors that we ignore.

In most cases, `FileStorage` and `RedisStorage` are significantly faster than `SQLiteStorage`, but `SQLiteStorage` can be used if you already have a well-configured sqlite database and want to keep cached responses close to your application data. 

For each storage option, there are some benefits.

FileStorage

1. **0 configuration**
2. **very fast**
3. **easy access**

RedisStorage

1. **can be shared**
2. **very fast**
3. **redis features**

SQLiteStorage

1. **can be shared**
2. **sqlite features**

!!! tip
    Any [serializer](#serializers) can be used with any storage because they are all fully compatible.

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
    Make sure `Hishel` has the yaml extension installed if you want to use the `YAMLSerializer`.
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
