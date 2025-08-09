import uuid
from typing import Any, Literal, Mapping, Union, cast, overload

import msgpack

from .models import CacheEntry, ResponseLastUsageInfo, StampedeInfo


@overload
def pack(data: CacheEntry, kind: Literal["entry"]) -> bytes: ...


@overload
def pack(data: StampedeInfo, kind: Literal["stampede"]) -> bytes: ...


@overload
def pack(data: ResponseLastUsageInfo, kind: Literal["staleness_tracker"]) -> bytes: ...


@overload
def pack(
    data: Mapping[str, Any],
    kind: Literal[
        "response",
        "response_chunk",
        "request",
        "request_chunk",
    ],
) -> bytes: ...


def pack(
    data: Mapping[str, Any] | CacheEntry | StampedeInfo | ResponseLastUsageInfo,
    kind: Literal[
        "response",
        "response_chunk",
        "request",
        "request_chunk",
        "entry",
        "stampede",
        "staleness_tracker",
    ],
) -> bytes:
    prepared_data: Mapping[str, Any]
    if kind == "entry":
        data = cast(CacheEntry, data)
        prepared_data = {
            **data,
            "responses": [r.bytes for r in data["responses"]],
        }
    elif kind == "stampede":
        data = cast(StampedeInfo, data)
        prepared_data = {
            **data,
            "lock_id": data["lock_id"].bytes,
        }
    elif kind == "staleness_tracker":
        data = cast(ResponseLastUsageInfo, data)
        prepared_data = {
            **data,
            "response_id": data["response_id"].bytes,
        }
    else:
        prepared_data = data

    return cast(bytes, msgpack.packb(prepared_data))


@overload
def unpack(data: bytes, kind: Literal["entry"]) -> CacheEntry: ...


@overload
def unpack(data: bytes, kind: Literal["stampede"]) -> StampedeInfo: ...


@overload
def unpack(data: bytes, kind: Literal["staleness_tracker"]) -> ResponseLastUsageInfo: ...


@overload
def unpack(
    data: bytes,
    kind: Literal["response", "response_chunk", "request", "request_chunk", "staleness_tracker"],
) -> Mapping[str, Any]: ...


def unpack(
    data: bytes,
    kind: Literal[
        "response",
        "response_chunk",
        "request",
        "request_chunk",
        "entry",
        "stampede",
        "staleness_tracker",
    ],
) -> Union[Mapping[str, Any], CacheEntry, StampedeInfo, ResponseLastUsageInfo]:
    unpacked_data = msgpack.unpackb(data, raw=False)

    if kind == "entry":
        return {
            **unpacked_data,
            "responses": [uuid.UUID(bytes=r) for r in unpacked_data["responses"]],
        }
    elif kind == "stampede":
        return {
            **unpacked_data,
            "lock_id": uuid.UUID(bytes=unpacked_data["lock_id"]),
        }
    elif kind == "staleness_tracker":
        return {
            **unpacked_data,
            "response_id": uuid.UUID(bytes=unpacked_data["response_id"]),
        }
    else:
        return unpacked_data  # type: ignore
