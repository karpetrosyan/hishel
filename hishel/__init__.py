import httpx

from ._async import *
from ._controller import *
from ._exceptions import *
from ._headers import *
from ._serializers import *
from ._sync import *
from ._lfu_cache import *

__all__ = (
    # Old API
    "AsyncCacheClient",
    "MockAsyncConnectionPool",
    "MockAsyncTransport",
    "AsyncCacheConnectionPool",
    "AsyncBaseStorage",
    "AsyncFileStorage",
    "AsyncInMemoryStorage",
    "AsyncRedisStorage",
    "AsyncS3Storage",
    "AsyncSQLiteStorage",
    "AsyncCacheTransport",
    "HEURISTICALLY_CACHEABLE_STATUS_CODES",
    "Controller",
    "CacheControlError",
    "ParseError",
    "ValidationError",
    "CacheControl",
    "Vary",
    "BaseSerializer",
    "JSONSerializer",
    "Metadata",
    "PickleSerializer",
    "YAMLSerializer",
    "clone_model",
    "CacheClient",
    "MockConnectionPool",
    "MockTransport",
    "CacheConnectionPool",
    "BaseStorage",
    "FileStorage",
    "InMemoryStorage",
    "RedisStorage",
    "S3Storage",
    "SQLiteStorage",
    "CacheTransport",
    "LFUCache",
)

def install_cache() -> None:  # pragma: no cover
    httpx.AsyncClient = AsyncCacheClient  # type: ignore
    httpx.Client = CacheClient  # type: ignore


__version__ = "0.1.5"

