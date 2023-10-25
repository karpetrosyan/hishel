---
icon: material/database
---


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


