import typing as tp

import httpx

from hishel._sync._transports import CacheTransport

__all__ = ("CacheClient",)


class CacheClient(httpx.Client):
    def __init__(self, *args: tp.Any, **kwargs: tp.Any):
        self._storage = kwargs.get("storage", None)
        self._controller = kwargs.get("controller", None)
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
