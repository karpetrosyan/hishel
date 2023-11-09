import typing as tp
from contextlib import contextmanager

import httpx

from hishel._sync._transports import CacheTransport

__all__ = ("CacheClient",)


class CacheClient(httpx.Client):
    def __init__(self, *args: tp.Any, **kwargs: tp.Any):
        self._storage = kwargs.pop("storage") if "storage" in kwargs else None
        self._controller = kwargs.pop("controller") if "controller" in kwargs else None
        super().__init__(*args, **kwargs)

    def _init_transport(self, *args, **kwargs) -> CacheTransport:  # type: ignore
        _transport = super()._init_transport(*args, **kwargs)
        return CacheTransport(
            transport=_transport,
            storage=self._storage,
            controller=self._controller,
        )

    def _init_proxy_transport(self, *args, **kwargs) -> CacheTransport:  # type: ignore
        _transport = super()._init_proxy_transport(*args, **kwargs)  # pragma: no cover
        return CacheTransport(  # pragma: no cover
            transport=_transport,
            storage=self._storage,
            controller=self._controller,
        )
    
    @contextmanager
    def cache_disabled(self) -> "CacheClient":
        """Temporarily disable cache for this client."""
        cached_transport = self._transport
        cached_mounts = self._mounts
        self._transport = self._transport._transport
        self._mounts = {k: v._transport for k, v in self._mounts.items()}
        yield
        self._transport = cached_transport
        self._mounts = cached_mounts