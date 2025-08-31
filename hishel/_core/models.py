from __future__ import annotations

import time
import uuid
from dataclasses import InitVar, dataclass, field
from typing import (
    Any,
    AsyncIterable,
    Iterable,
    Iterator,
    Mapping,
    Optional,
    cast,
)

from hishel._core._headers import Headers


class EmptyIterable:
    def __iter__(self) -> Iterator[bytes]:
        yield from []  # pragma: nocover

    async def __aiter__(self) -> AsyncIterable[bytes]:
        for item in cast(list[bytes], []):  # pragma: nocover
            yield item

    def __eq__(self, value: Any) -> bool:
        return isinstance(value, EmptyIterable)


@dataclass
class Request:
    method: str
    url: str
    headers: Headers = field(init=False)
    stream: Iterable[bytes] | AsyncIterable[bytes] = field(default_factory=EmptyIterable)
    extra: Mapping[str, Any] = field(default_factory=dict)
    raw_headers: InitVar[Optional[Mapping[str, str | list[str]]]] = None

    def __post_init__(self, raw_headers: Optional[Mapping[str, str | list[str]]]) -> None:
        self.headers = Headers(raw_headers) if raw_headers is not None else Headers({})


@dataclass
class Response:
    status_code: int
    headers: Headers = field(init=False)
    stream: Iterable[bytes] | AsyncIterable[bytes] = field(default_factory=EmptyIterable)
    extra: Mapping[str, Any] = field(default_factory=dict)
    raw_headers: InitVar[Optional[Mapping[str, str | list[str]]]] = None

    def __post_init__(self, raw_headers: Optional[Mapping[str, str | list[str]]]) -> None:
        self.headers = Headers(raw_headers) if raw_headers is not None else Headers({})


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
        return cls(
            id=uuid.uuid4(),
            request=request,
            response=response,
            meta=PairMeta(),
        )
