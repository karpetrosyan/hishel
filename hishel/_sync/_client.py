import typing as tp

import httpx
from httpx._config import DEFAULT_LIMITS, DEFAULT_MAX_REDIRECTS, DEFAULT_TIMEOUT_CONFIG
from httpx._types import (
    AuthTypes,
    CertTypes,
    CookieTypes,
    HeaderTypes,
    ProxiesTypes,
    QueryParamTypes,
    TimeoutTypes,
    URLTypes,
    VerifyTypes,
)

from hishel._sync._storages import BaseStorage
from hishel._sync._transports import CacheTransport
from hishel._controller import Controller

__all__ = (
    'CacheClient',
)

EventHook = tp.Callable[..., tp.Any]

class CacheClient(httpx.Client):

    def __init__(
        self,
        *,
        auth: tp.Optional[AuthTypes] = None,
        params: tp.Optional[QueryParamTypes] = None,
        headers: tp.Optional[HeaderTypes] = None,
        cookies: tp.Optional[CookieTypes] = None,
        verify: VerifyTypes = True,
        cert: tp.Optional[CertTypes] = None,
        http1: bool = True,
        http2: bool = False,
        proxies: tp.Optional[ProxiesTypes] = None,
        mounts: tp.Optional[tp.Mapping[str, httpx.BaseTransport]] = None,
        timeout: TimeoutTypes = DEFAULT_TIMEOUT_CONFIG,
        follow_redirects: bool = False,
        limits: httpx.Limits = DEFAULT_LIMITS,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        event_hooks: tp.Optional[
            tp.Mapping[str, tp.List[EventHook]]
        ] = None,
        base_url: URLTypes = "",
        transport: tp.Optional[httpx.BaseTransport] = None,
        app: tp.Optional[tp.Callable[..., tp.Any]] = None,
        trust_env: bool = True,
        default_encoding: tp.Union[str, tp.Callable[[bytes], str]] = "utf-8",
        cache_storage: tp.Optional[BaseStorage] = None,
        cache_controller: tp.Optional[Controller] = None
    ):

        self._storage = cache_storage
        self._controller = cache_controller
        super().__init__(
            auth=auth,
            params=params,
            headers=headers,
            cookies=cookies,
            verify=verify,
            cert=cert,
            http1=http1,
            http2=http2,
            proxies=proxies,
            mounts=mounts,
            timeout=timeout,
            follow_redirects=follow_redirects,
            limits=limits,
            max_redirects=max_redirects,
            event_hooks=event_hooks,
            base_url=base_url,
            transport=transport,
            app=app,
            trust_env=trust_env,
            default_encoding=default_encoding)


    def _init_transport(self, *args, **kwargs)-> CacheTransport:  # type: ignore
        _transport = super()._init_transport(*args, **kwargs)
        return CacheTransport(
            transport=_transport,
            storage=self._storage,
            cache_controller=self._controller
        )


    def _init_proxy_transport(self, *args, **kwargs) -> CacheTransport:  # type: ignore
        _transport = super()._init_proxy_transport(*args, **kwargs)  # pragma: no cover
        return CacheTransport(  # pragma: no cover
            transport=_transport,
            storage=self._storage,
            cache_controller=self._controller
        )
