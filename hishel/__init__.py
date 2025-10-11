import httpx

from ._async import *
from ._controller import *
from ._exceptions import *
from ._headers import *
from ._serializers import *
from ._sync import *
from ._lfu_cache import *

from hishel.beta._core._spec import IdleClient as IdleClient, CacheMiss as CacheMiss, FromCache as FromCache, NeedRevalidation as NeedRevalidation, AnyState as AnyState, CacheOptions as CacheOptions, NeedToBeUpdated as NeedToBeUpdated, State as State, StoreAndUse as StoreAndUse, CouldNotBeStored as CouldNotBeStored, create_idle_state as create_idle_state
from hishel.beta._core.models import Request as Request, Response as Response, Pair as Pair, IncompletePair as IncompletePair, CompletePair as CompletePair, PairMeta as PairMeta 
from hishel.beta._core._headers import Headers as Headers
from hishel.beta._core._base._storages._base import SyncBaseStorage as SyncBaseStorage
from hishel.beta._core._sync._storages._sqlite import SyncSqliteStorage as SyncSqliteStorage
from hishel.beta._core._async._storages._sqlite import AsyncSqliteStorage as AsyncSqliteStorage
from hishel.beta._core._keygen import KeyGen as KeyGen, HashKeyGen as HashKeyGen


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

    # New API

    ## States
    "IdleClient",
    "CacheMiss",
    "FromCache",
    "NeedRevalidation",
    "AnyState",
    "CacheOptions",
    "NeedToBeUpdated",
    "State",
    "StoreAndUse",
    "CouldNotBeStored",
    "create_idle_state",
    ## Models
    "Request",
    "Response",
    "Pair",
    "IncompletePair",
    "CompletePair",
    "PairMeta",
    ## Headers
    "Headers",
    ## Storages
    "SyncBaseStorage",
    "SyncSqliteStorage",
    "AsyncBaseStorage",
    "AsyncSqliteStorage",
    ## Keygens
    "KeyGen",
    "HashKeyGen",
)

def install_cache() -> None:  # pragma: no cover
    httpx.AsyncClient = AsyncCacheClient  # type: ignore
    httpx.Client = CacheClient  # type: ignore


__version__ = "0.1.3"

