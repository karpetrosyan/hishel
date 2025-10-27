from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncIterable,
    AsyncIterator,
    Iterable,
    Iterator,
    Mapping,
    Optional,
    TypedDict,
    cast,
)

from hishel._core._headers import Headers
from hishel._utils import make_async_iterator, make_sync_iterator


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

    hishel_body_key: bool | None
    """
    When True, the request body is included in the cache key generation.
    This is useful for caching POST or QUERY requests with different bodies.
    """


def extract_metadata_from_headers(
    headers: Mapping[str, str],
) -> RequestMetadata:
    metadata: RequestMetadata = {}
    if "X-Hishel-Ttl" in headers:
        try:
            metadata["hishel_ttl"] = float(headers["X-Hishel-Ttl"])
        except ValueError:
            pass
    if "X-Hishel-Refresh-Ttl-On-Access" in headers:
        value = headers["X-Hishel-Refresh-Ttl-On-Access"].lower()
        if value in ("1", "true", "yes", "on"):
            metadata["hishel_refresh_ttl_on_access"] = True
        elif value in ("0", "false", "no", "off"):
            metadata["hishel_refresh_ttl_on_access"] = False
    if "X-Hishel-Spec-Ignore" in headers:
        value = headers["X-Hishel-Spec-Ignore"].lower()
        if value in ("1", "true", "yes", "on"):
            metadata["hishel_spec_ignore"] = True
        elif value in ("0", "false", "no", "off"):
            metadata["hishel_spec_ignore"] = False
    return metadata


@dataclass
class Request:
    method: str
    url: str
    headers: Headers = field(default_factory=lambda: Headers({}))
    stream: Iterator[bytes] | AsyncIterator[bytes] = field(default_factory=lambda: iter(AnyIterable()))
    metadata: RequestMetadata | Mapping[str, Any] = field(default_factory=dict)

    def _iter_stream(self) -> Iterator[bytes]:
        if hasattr(self, "collected_body"):
            yield getattr(self, "collected_body")
            return
        if isinstance(self.stream, (Iterator, Iterable)):
            yield from self.stream
            return
        raise TypeError("Request stream is not an Iterator")

    async def _aiter_stream(self) -> AsyncIterator[bytes]:
        if hasattr(self, "collected_body"):
            yield getattr(self, "collected_body")
            return
        if isinstance(self.stream, (AsyncIterator, AsyncIterable)):
            async for chunk in self.stream:
                yield chunk
            return
        else:
            raise TypeError("Request stream is not an AsyncIterator")

    def read(self) -> bytes:
        """
        Synchronously reads the entire request body without consuming the stream.
        """
        if not isinstance(self.stream, Iterator):
            raise TypeError("Request stream is not an Iterator")

        if hasattr(self, "collected_body"):
            return cast(bytes, getattr(self, "collected_body"))

        collected = b"".join([chunk for chunk in self.stream])
        setattr(self, "collected_body", collected)
        self.stream = make_sync_iterator([collected])
        return collected

    async def aread(self) -> bytes:
        """
        Asynchronously reads the entire request body without consuming the stream.
        """
        if not isinstance(self.stream, AsyncIterator):
            raise TypeError("Request stream is not an AsyncIterator")

        if hasattr(self, "collected_body"):
            return cast(bytes, getattr(self, "collected_body"))

        collected = b"".join([chunk async for chunk in self.stream])
        setattr(self, "collected_body", collected)
        self.stream = make_async_iterator([collected])
        return collected


class ResponseMetadata(TypedDict, total=False):
    # All the names here should be prefixed with "hishel_" to avoid collisions with user data
    hishel_from_cache: bool
    """Indicates whether the response was served from cache."""

    hishel_revalidated: bool
    """Indicates whether the response was revalidated with the origin server."""

    hishel_stored: bool
    """Indicates whether the response was stored in cache."""

    hishel_created_at: float
    """Timestamp when the response was cached."""


@dataclass
class Response:
    status_code: int
    headers: Headers = field(default_factory=lambda: Headers({}))
    stream: Iterator[bytes] | AsyncIterator[bytes] = field(default_factory=lambda: iter(AnyIterable()))
    metadata: ResponseMetadata | Mapping[str, Any] = field(default_factory=dict)

    def _iter_stream(self) -> Iterator[bytes]:
        if hasattr(self, "collected_body"):
            yield getattr(self, "collected_body")
            return
        if isinstance(self.stream, Iterator):
            yield from self.stream
            return
        raise TypeError("Response stream is not an Iterator")

    async def _aiter_stream(self) -> AsyncIterator[bytes]:
        if hasattr(self, "collected_body"):
            yield getattr(self, "collected_body")
            return
        if isinstance(self.stream, AsyncIterator):
            async for chunk in self.stream:
                yield chunk
        else:
            raise TypeError("Response stream is not an AsyncIterator")

    def read(self) -> bytes:
        """
        Synchronously reads the entire request body without consuming the stream.
        """
        if not isinstance(self.stream, Iterator):
            raise TypeError("Request stream is not an Iterator")

        if hasattr(self, "collected_body"):
            return cast(bytes, getattr(self, "collected_body"))

        collected = b"".join([chunk for chunk in self.stream])
        setattr(self, "collected_body", collected)
        self.stream = make_sync_iterator([collected])
        return collected

    async def aread(self) -> bytes:
        """
        Asynchronously reads the entire request body without consuming the stream.
        """
        if not isinstance(self.stream, AsyncIterator):
            raise TypeError("Request stream is not an AsyncIterator")

        if hasattr(self, "collected_body"):
            return cast(bytes, getattr(self, "collected_body"))

        collected = b"".join([chunk async for chunk in self.stream])
        setattr(self, "collected_body", collected)
        self.stream = make_async_iterator([collected])
        return collected


@dataclass
class EntryMeta:
    created_at: float = field(default_factory=time.time)
    deleted_at: Optional[float] = None


@dataclass
class Entry:
    id: uuid.UUID
    request: Request
    meta: EntryMeta
    response: Response
    cache_key: bytes
    extra: Mapping[str, Any] = field(default_factory=dict)
