import typing as tp

import httpx

from hishel._sync._storages import BaseStorage
from hishel._sync._transports import CacheTransport
from hishel._controller import Controller

__all__ = ("CacheClient",)


class CacheClient(httpx.Client):
    def __init__(
        self,
        *args: tp.Any,
        storage: tp.Optional[BaseStorage] = None,
        controller: tp.Optional[Controller] = None,
        **kwargs: tp.Any,
    ):
        self._storage = storage
        self._controller = controller
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
