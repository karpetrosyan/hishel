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
transport = hishel.CacheTransport(transport=httpx.HTTPTransport(), storage=storage)
```

Here's how the filesystem storage looks:

```
📁 root
└─╴📁 .cache
   └─╴📁 hishel
      ├─╴📄 GET|github.com|a9022e44881123781045f6fadf37a8b1
      ├─╴📄 GET|www.google.com|8bfc7fffcfd5f2b8e3485d0cc7450c98
      ├─╴📄 GET|www.python-httpx.org|5f004f4f08bd774c4bc4b270a0ca542e
      └─╴📄 GET|hishel.com|41ebb4dd16761e94e2ee36b71e0d916e
```

!!! note
    Note that by default, file names are just the hashed value, without the http method or hostname; to have meaningful names, see [custom cache keys](controllers.md#custom-cache-keys).

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

#### Check ttl every

In order to avoid excessive memory utilization, `Hishel` must periodically clean the old responses, or responses that are not being used and should be deleted from the cache.
It clears the cache by default every minute, but you may change the interval directly with the `check_ttl_every` argument.

Example:

```python
import hishel

storage = hishel.FileStorage(check_ttl_every=600) # check every 600s (10m) 
```

### :material-memory: In-memory storage

`Hishel` has an in-memory cache that can be used when you don't need the cache to be persistent.

You should understand that in memory cache means that **all cached responses are stored in RAM**, so you should be cautious and possibly **configure the cache's maximum size** to avoid wasting RAM.

Example:

```python
import hishel

storage = hishel.InMemoryStorage()
client = hishel.CacheClient(storage=storage)
```

Or if you are using Transports:

```python
import hishel
import httpx

storage = hishel.InMemoryStorage()
client = hishel.CacheTransport(transport=httpx.HTTPTransport(), storage=storage)
```

#### Set the maximum capacity

You can also specify the maximum number of requests that the storage can cache. 

Example:

```python
import hishel

storage = hishel.InMemoryStorage(capacity=64)
client = hishel.CacheClient(storage=storage)
```

!!! note
    When the number of responses exceeds the cache's capacity, Hishel employs the [LFU algorithm](https://en.wikipedia.org/wiki/Least_frequently_used) to remove some of the responses. 

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
client = hishel.CacheTransport(transport=httpx.HTTPTransport(), storage=storage)
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


### :material-aws: AWS S3 storage

`Hishel` has built-in [AWS S3](https://aws.amazon.com/s3/) support, allowing users to store responses in the cloud.

Example:

```python
import hishel

storage = hishel.S3Storage(bucket_name="cached_responses")
client = hishel.CacheClient(storage=storage)
```

Or if you are using Transports
```python

import httpx
import hishel

storage = hishel.S3Storage(bucket_name="cached_responses")
transport = hishel.CacheTransport(httpx.HTTPTransport(), storage=storage)
```

#### Custom AWS S3 client

If you want to manually configure the client instance, pass it to Hishel.

```python
import hishel
import boto3

s3_client = boto3.client('s3')

storage = hishel.S3Storage(bucket_name="cached_responses", client=s3_client)
client = hishel.CacheClient(storage=storage)
```

#### Responses ttl in S3Storage

You can explicitly specify the ttl for stored responses in this manner.

```python
import hishel

storage = hishel.S3Storage(ttl=3600)
```

If you do this, `Hishel` will delete any stored responses whose ttl has expired.
In this example, the stored responses were limited to 1 hour.

#### Check ttl every

In order to avoid excessive memory utilization, `Hishel` must periodically clean the old responses, or responses that are not being used and should be deleted from the cache.
It clears the cache by default every minute, but you may change the interval directly with the `check_ttl_every` argument.

Example:

```python
import hishel

storage = hishel.S3Storage(check_ttl_every=600) # check every 600s (10m) 
```
