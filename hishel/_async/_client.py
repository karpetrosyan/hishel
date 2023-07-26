import typing as tp

import httpx

from hishel._async._transports import AsyncCacheTransport

__all__ = ("AsyncCacheClient",)


class AsyncCacheClient(httpx.AsyncClient):
    def __init__(self, *args: tp.Any, **kwargs: tp.Any):
        self._storage = kwargs.get("storage", None)
        self._controller = kwargs.get("controller", None)
        super().__init__(*args, **kwargs)

    def _init_transport(self, *args, **kwargs) -> AsyncCacheTransport:  # type: ignore
        _transport = super()._init_transport(*args, **kwargs)
        return AsyncCacheTransport(
            transport=_transport,
            storage=self._storage,
            controller=self._controller,
        )

    def _init_proxy_transport(self, *args, **kwargs) -> AsyncCacheTransport:  # type: ignore
        _transport = super()._init_proxy_transport(*args, **kwargs)  # pragma: no cover
        return AsyncCacheTransport(  # pragma: no cover
            transport=_transport,
            storage=self._storage,
            controller=self._controller,
        )
