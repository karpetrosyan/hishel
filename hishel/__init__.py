import httpx

from ._async import *
from ._controller import *
from ._exceptions import *
from ._headers import *
from ._serializers import *
from ._sync import *
from ._lfu_cache import *

from ._core._spec import IdleClient, CacheMiss, FromCache, NeedRevalidation, AnyState, CacheOptions,  NeedToBeUpdated, State, StoreAndUse, CouldNotBeStored
from ._core.models import Request, Response, Pair, IncompletePair, CompletePair
from ._core._headers import Headers

def install_cache() -> None:  # pragma: no cover
    httpx.AsyncClient = AsyncCacheClient  # type: ignore
    httpx.Client = CacheClient  # type: ignore


__version__ = "0.1.3"

__all__ = [
    "AnyState",
    "State",
    "IdleClient",
    "CacheMiss",
    "FromCache",
    "NeedRevalidation",
    "CacheOptions",
    "NeedToBeUpdated",
    "StoreAndUse",
    "CouldNotBeStored",

    # from _core.models
    "Request",
    "Response",
    "Pair",
    "IncompletePair",
    "CompletePair",

    # from _core._headers
    "Headers",
]
