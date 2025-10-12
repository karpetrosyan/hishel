from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncIterator,
    Iterator,
    Mapping,
    Optional,
    TypedDict,
)

from hishel.beta._core._headers import Headers


class AnyIterable:
    def __init__(self, content: bytes | None = None) -> None:
        self.consumed = False
        self.content = content

    def __next__(self) -> bytes:
        if self.content is not None and not self.consumed:
            self.consumed = True
            return self.content
        raise StopIteration()

    def __iter__(self) -> Iterator[bytes]:
        return self

    async def __anext__(self) -> bytes:
        if self.content is not None and not self.consumed:
            self.consumed = True
            return self.content
        raise StopAsyncIteration()

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self

    def __eq__(self, value: Any) -> bool:
        return isinstance(value, AnyIterable)


class RequestMetadata(TypedDict, total=False):
    # All the names here should be prefixed with "hishel_" to avoid collisions with user data
    hishel_ttl: float | None
    """When specified, hishel will remove the cached response after specified number of seconds."""

    hishel_refresh_ttl_on_access: bool | None
    """
    When True, accessing this entry refreshes its TTL. When False, the TTL remains fixed (default).
    """

    hishel_spec_ignore: bool | None
    """
    When True, hishel will ignore the caching specification for this request.
    """


@dataclass
class Request:
    method: str
    url: str
    headers: Headers = field(default_factory=lambda: Headers({}))
    stream: Iterator[bytes] | AsyncIterator[bytes] = field(default_factory=lambda: iter(AnyIterable()))
    metadata: RequestMetadata | Mapping[str, Any] = field(default_factory=dict)

    def iter_stream(self) -> Iterator[bytes]:
        if isinstance(self.stream, Iterator):
            return self.stream
        raise TypeError("Request stream is not an Iterator")

    async def aiter_stream(self) -> AsyncIterator[bytes]:
        if isinstance(self.stream, AsyncIterator):
            async for chunk in self.stream:
                yield chunk
        else:
            raise TypeError("Request stream is not an AsyncIterator")


class ResponseMetadata(TypedDict, total=False):
    # All the names here should be prefixed with "hishel_" to avoid collisions with user data
    hishel_from_cache: bool | None
    """Indicates whether the response was served from cache."""

    hishel_revalidated: bool | None
    """Indicates whether the response was revalidated with the origin server."""

    hishel_spec_ignored: bool | None
    """Indicates whether the caching specification was ignored for this response."""

    hishel_stored: bool | None
    """Indicates whether the response was stored in cache."""


@dataclass
class Response:
    status_code: int
    headers: Headers = field(default_factory=lambda: Headers({}))
    stream: Iterator[bytes] | AsyncIterator[bytes] = field(default_factory=lambda: iter(AnyIterable()))
    metadata: ResponseMetadata | Mapping[str, Any] = field(default_factory=dict)

    def iter_stream(self) -> Iterator[bytes]:
        if isinstance(self.stream, Iterator):
            return self.stream
        raise TypeError("Response stream is not an Iterator")

    async def aiter_stream(self) -> AsyncIterator[bytes]:
        if isinstance(self.stream, AsyncIterator):
            async for chunk in self.stream:
                yield chunk
        else:
            raise TypeError("Response stream is not an AsyncIterator")


@dataclass
class PairMeta:
    created_at: float = field(default_factory=time.time)
    deleted_at: Optional[float] = None


@dataclass
class Pair:
    id: uuid.UUID
    request: Request
    meta: PairMeta


# class used by storage
@dataclass
class IncompletePair(Pair):
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class CompletePair(Pair):
    response: Response
    cache_key: bytes
    extra: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def create(
        cls,
        response: Response,
        request: Request,
    ) -> "CompletePair":  # pragma: nocover
        return cls(id=uuid.uuid4(), request=request, response=response, meta=PairMeta(), cache_key=b"")
