import httpx

from ._async import *
from ._controller import *
from ._exceptions import *
from ._headers import *
from ._serializers import *
from ._sync import *
from ._lfu_cache import *

from ._core._spec import IdleClient as IdleClient, CacheMiss as CacheMiss, FromCache as FromCache, NeedRevalidation as NeedRevalidation, AnyState as AnyState, CacheOptions as CacheOptions, NeedToBeUpdated as NeedToBeUpdated, State as State, StoreAndUse as StoreAndUse, CouldNotBeStored as CouldNotBeStored, create_idle_state as create_idle_state, UpdatePartials as UpdatePartials
from ._core.models import Request as Request, Response as Response, Pair as Pair, IncompletePair as IncompletePair, CompletePair as CompletePair, PairMeta as PairMeta 
from ._core._headers import Headers as Headers

def install_cache() -> None:  # pragma: no cover
    httpx.AsyncClient = AsyncCacheClient  # type: ignore
    httpx.Client = CacheClient  # type: ignore


__version__ = "0.1.3"

