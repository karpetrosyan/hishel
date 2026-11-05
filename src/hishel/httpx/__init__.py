try:
    import httpx  # noqa: F401
except ImportError as e:
    raise ImportError(
        "httpx is required to use hishel.httpx module. "
        "Please install hishel with the 'httpx' extra, "
        "e.g., 'pip install hishel[httpx]'."
    ) from e


from ._async import (
    AsyncCacheClient as AsyncCacheClient,
    AsyncCacheConfig as AsyncCacheConfig,
    AsyncCacheTransport as AsyncCacheTransport,
)
from ._sync import CacheClient as CacheClient, CacheConfig as CacheConfig, CacheTransport as CacheTransport
