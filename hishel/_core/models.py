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
)

from hishel._core._headers import Headers


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


@dataclass
class Request:
    method: str
    url: str
    headers: Headers = field(default_factory=lambda: Headers({}))
    stream: Iterator[bytes] | AsyncIterator[bytes] = field(default_factory=lambda: iter(AnyIterable()))
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class Response:
    status_code: int
    headers: Headers = field(default_factory=lambda: Headers({}))
    stream: Iterator[bytes] | AsyncIterator[bytes] = field(default_factory=lambda: iter(AnyIterable()))
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class PairMeta:
    created_at: float = field(default_factory=time.time)
    deleted_at: Optional[float] = None
    ttl: Optional[float] = None
    refresh_ttl_on_access: Optional[bool] = None


@dataclass
class Pair:
    id: uuid.UUID
    request: Request
    meta: PairMeta
    cache_key: str


# class used by storage
@dataclass
class IncompletePair(Pair):
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class CompletePair(Pair):
    response: Response
    extra: Mapping[str, Any] = field(default_factory=dict)
    complete_stream: bool = True

    @classmethod
    def create(
        cls,
        response: Response,
        request: Request,
    ) -> "CompletePair":  # pragma: nocover
        return cls(id=uuid.uuid4(), request=request, response=response, meta=PairMeta(), cache_key="")
