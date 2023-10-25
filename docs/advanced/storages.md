---
icon: material/database
---


When using `Hishel`, you have complete control over the configuration of how the responses should be stored. You can select the [serializer](serializers.md) and storage on your own.

This section contains examples of how to use the storages.

### :file_folder: Filesystem storage

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

#### Storage directory

If the responses are saved in the filesystem, there should be a directory that contains our responses.

By default it's `.cache/hishel`.

If you want to change the directory, do so as follows.

```python
import hishel

storage = hishel.FileStorage(base_path="/home/test/my_cache_dir")
```

#### Responses ttl in FileStorage

You can explicitly specify the ttl for stored responses in this manner.

```python
import hishel

storage = hishel.FileStorage(ttl=3600)
```

If you do this, `Hishel` will delete any stored responses whose ttl has expired.
In this example, the stored responses were limited to 1 hour.

### :simple-redis: Redis storage

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

#### Custom redis client

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


#### Responses ttl in RedisStorage

You can explicitly specify the ttl for stored responses in this manner.

```python
import hishel

storage = hishel.RedisStorage(ttl=3600)
```

If you do this, `Hishel` will delete any stored responses whose ttl has expired.
In this example, the stored responses were limited to 1 hour.

### :simple-sqlite: SQLite storage

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

#### Sqlite custom connection

If you want more control over the underlying sqlite connection, you can explicitly pass it.

```python
import hishel
import sqlite3

client = hishel.CacheClient(
    storage=hishel.SQLiteStorage(connection=sqlite3.connect("my_db_path", timeout=5))
)
```

#### Responses ttl in SQLiteStorage

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
    Any [serializer](serializers.md) can be used with any storage because they are all fully compatible.

