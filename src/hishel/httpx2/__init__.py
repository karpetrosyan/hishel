try:
    import httpx2  # noqa: F401
except ImportError as e:
    raise ImportError(
        "httpx2 is required to use hishel.httpx2 module. "
        "Please install hishel with the 'httpx2' extra, "
        "e.g., 'pip install hishel[httpx2]'."
    ) from e


from ._async import (
    AsyncCacheClient as AsyncCacheClient,
    AsyncCacheConfig as AsyncCacheConfig,
    AsyncCacheTransport as AsyncCacheTransport,
)
from ._sync import CacheClient as CacheClient, CacheConfig as CacheConfig, CacheTransport as CacheTransport
