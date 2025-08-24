import uuid
from dataclasses import field, dataclass
from typing import (
    Any,
    AsyncIterable,
    Iterable,
    Mapping,
    MutableMapping,
    Optional,
    Required,
    TypeAlias,
    TypedDict,
    Union,
    overload,
)

import httpx

from hishel._core._headers import Headers

AnyMapping: TypeAlias = Union[
    Mapping[str, Union[str, bytes]],
    MutableMapping[str, Union[str, bytes]],
]


@overload
def ensure_decoded(value: Union[str, bytes]) -> str: ...


@overload
def ensure_decoded(
    value: Union[MutableMapping[str, Union[str, bytes]]],
) -> MutableMapping[str, str]: ...


@overload
def ensure_decoded(
    value: Union[Mapping[str, Union[str, bytes]]],
) -> Mapping[str, str]: ...


def ensure_decoded(
    value: Union[
        Union[str, bytes],
        Mapping[str, Union[str, bytes]],
        MutableMapping[str, Union[str, bytes]],
    ],
) -> Union[str, Mapping[str, str], MutableMapping[str, str]]:
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8")
    elif isinstance(value, (Mapping, MutableMapping)):
        return {key: value.decode("iso-8859-1") if isinstance(value, bytes) else value for key, value in value.items()}

    return value


@dataclass
class Request:
    method: str
    url: str
    headers: Headers
    stream: Iterable[bytes] | AsyncIterable[bytes]
    extra: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class Response:
    status_code: int
    headers: Headers
    stream: Iterable[bytes] | AsyncIterable[bytes]
    extra: Mapping[str, Any] = field(default_factory=dict)


class PairMeta(TypedDict, total=False):
    created_at: Required[float]
    deleted_at: float
    ttl: float
    refresh_ttl_on_access: bool


@dataclass
class RequestPair:
    id: uuid.UUID
    request: Request
    meta: PairMeta
    cache_key: str
    extra: Mapping[str, Any] = field(default_factory=dict)
    """
    Cache key for the entry, if it is cached.
    """

    response: Optional[Response] = None
