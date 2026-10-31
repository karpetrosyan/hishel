from __future__ import annotations

import abc
import typing as tp
import uuid

from hishel._core._headers import Headers
from hishel._core.models import Entry, Request, Response


class AsyncBaseStorage(abc.ABC):
    """
    What the cache layer needs from a storage backend.

    Cleanup, eviction, size limits and protection of in-flight readers are
    private to each backend, as are their settings.
    """

    def __init__(
        self,
        *,
        default_ttl: float | None = None,
        default_tti: float | None = None,
        max_stream_size: int | None = None,
    ) -> None:
        self.default_ttl = default_ttl
        self.default_tti = default_tti
        self.max_stream_size = max_stream_size

    def _limits(self, ttl: float | None, tti: float | None, now: float) -> tuple[float | None, float | None]:
        """The TTL deadline and TTI of an entry stored at ``now``, which a backend keeps to call ``_expires_at``."""
        ttl = ttl if ttl is not None else self.default_ttl
        tti = tti if tti is not None else self.default_tti
        return (now + ttl if ttl is not None else None), tti

    def _expires_at(self, ttl_deadline: float | None, tti: float | None, now: float) -> float | None:
        """When an entry last returned at ``now`` expires, or None if it never does."""
        limits = []
        if ttl_deadline is not None:
            limits.append(ttl_deadline)
        if tti is not None:
            limits.append(now + tti)
        return min(limits, default=None)

    @abc.abstractmethod
    async def create_entry(
        self,
        request: Request,
        response: Response,
        key: str,
        *,
        ttl: float | None = None,
        tti: float | None = None,
    ) -> Entry:
        """
        Create an entry and return it with a stream that saves the body as it is read.

        - The entry is not returned by ``get_entries`` until that stream is fully read.
        - A storage failure while saving stops caching but does not fail the
          consumer reading that stream.
        - A response larger than ``max_stream_size`` is not cached, but its consumer
          still receives the whole body.
        - The entry expires at the earliest of its TTL, counted from this call, and
          its TTI, counted from when ``get_entries`` last returned it. ``ttl`` and
          ``tti`` fall back to the storage's defaults at this moment, and each is
          unlimited if neither is set.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def get_entries(self, key: str) -> tp.List[Entry]:
        """
        Return the entries stored under ``key``.

        - Only complete, unexpired, non-removed entries are returned.
        - Returning an entry restarts its TTI. Backends may batch these updates, so
          it can expire up to half its TTI sooner than that.
        - A returned response stream delivers the whole body or raises. It never
          ends early without an error.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def update_headers(self, id: uuid.UUID, headers: Headers) -> None:
        """
        Replace the stored response headers of an entry.

        Entries can disappear at any time, so this does nothing if the entry no
        longer exists.
        """
        raise NotImplementedError()

    @abc.abstractmethod
    async def remove_entry(self, id: uuid.UUID) -> None:
        """
        Remove an entry so that new lookups no longer return it.

        - When its space is reclaimed is up to the backend.
        - Entries can disappear at any time, so this does nothing if the entry no
          longer exists.
        """
        raise NotImplementedError()

    async def close(self) -> None:
        pass
