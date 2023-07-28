`Hishel's` storages are the classes responsible for implementing response store logic.

Each storage class implements at least three of these methods.

- **store(key, response) -> None**
- **retreive(key) -> None or response**
- **close() -> None**

One is for storing the response, another is for retrieving the response using the key, and the last simply closes the resources.

## Filesystem

Hishel comes with several storage options, but the default is always filesystem storage.

It simply stores responses in files, where the filename is the response identification and the file content is the response parts.

First, start by importing `FileStorage`:

```python
from hishel import FileStorage
from hishel import AsyncFileStorage

storage = FileStorage()
```

Now we can pass that storage to CacheClient, CacheTransport, or CacheConnectionPool to explicitly specify the storage backend.

```python
from hishel import CacheClient

client = CacheClient(storage=storage)

client.get("GET", "https://example.com")  # will use filesystem as a storage
```



## Redis
However, because the FileStorage class is already a default, there is no need to explicitly specify it; instead, we can select another backend, such as the popular in memory database redis!

```python
from hishel import RedisStorage
from hishel import AsyncRedisStorage
from hishel import CacheClient

client = CacheClient(storage=RedisStorage())

client.get("GET", "https://example.com")  # will use redis://localhost:6379 as a storage
```

You can also pass redis client explicitly to configure the underlying redis connection.

```python
import redis
import os

redis_client = redis.Redis(
    host='192.168.0.85',
    port=8081,
    db=1,
    password=os.getenv("REDISPASS"),
    socket_connect_timeout=0.5
)
client = CacheClient(storage=RedisStorage(client=redis_client))
```