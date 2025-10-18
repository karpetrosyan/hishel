from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Mapping, Optional, Union, overload

import msgpack
from typing_extensions import Literal, cast

from hishel._core._headers import Headers
from hishel._core.models import PairMeta, Request, Response


def filter_out_hishel_metadata(data: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if not k.startswith("hishel_")}


if TYPE_CHECKING:
    from hishel import CompletePair, IncompletePair


@overload
def pack(
    value: "CompletePair" | "IncompletePair",
    /,
    kind: Literal["pair"],
) -> bytes: ...


@overload
def pack(
    value: uuid.UUID,
    /,
    kind: Literal["entry_db_key_index"],
) -> bytes: ...


def pack(
    value: Union["CompletePair", "IncompletePair", uuid.UUID],
    /,
    kind: Literal["pair", "entry_db_key_index"],
) -> bytes:
    from hishel import CompletePair, IncompletePair

    if kind == "entry_db_key_index":
        assert isinstance(value, uuid.UUID)
        return value.bytes
    elif kind == "pair":
        assert isinstance(value, (CompletePair, IncompletePair))
        cache_key_dict = {"cache_key": value.cache_key} if isinstance(value, CompletePair) else {}
        return cast(
            bytes,
            msgpack.packb(
                {
                    "id": value.id.bytes,
                    "request": {
                        "method": value.request.method,
                        "url": value.request.url,
                        "headers": value.request.headers._headers,
                        "extra": filter_out_hishel_metadata(value.request.metadata),
                    },
                    "response": (
                        {
                            "status_code": value.response.status_code,
                            "headers": value.response.headers._headers,
                            "extra": filter_out_hishel_metadata(value.response.metadata),
                        }
                    )
                    if isinstance(value, CompletePair)
                    else None,
                    "meta": {
                        "created_at": value.meta.created_at,
                        "deleted_at": value.meta.deleted_at,
                    },
                    **cache_key_dict,
                }
            ),
        )
    assert False, f"Unexpected kind: {kind}"


@overload
def unpack(
    value: bytes,
    /,
    kind: Literal["pair"],
) -> Union["CompletePair", "IncompletePair"]: ...


@overload
def unpack(
    value: bytes,
    /,
    kind: Literal["entry_db_key_index"],
) -> uuid.UUID: ...


@overload
def unpack(
    value: Optional[bytes],
    /,
    kind: Literal["pair"],
) -> Optional[Union["CompletePair", "IncompletePair"]]: ...


@overload
def unpack(
    value: Optional[bytes],
    /,
    kind: Literal["entry_db_key_index"],
) -> Optional[uuid.UUID]: ...


def unpack(
    value: Optional[bytes],
    /,
    kind: Literal["pair", "entry_db_key_index"],
) -> Union["CompletePair", "IncompletePair", uuid.UUID, None]:
    from hishel import CompletePair, IncompletePair

    if value is None:
        return None
    if kind == "entry_db_key_index":
        return uuid.UUID(bytes=value)
    elif kind == "pair":
        data = msgpack.unpackb(value)
        id = uuid.UUID(bytes=data["id"])
        if data.get("response"):
            return CompletePair(
                id=id,
                request=Request(
                    method=data["request"]["method"],
                    url=data["request"]["url"],
                    headers=Headers(data["request"]["headers"]),
                    metadata=data["request"]["extra"],
                    stream=iter([]),
                ),
                response=(
                    Response(
                        status_code=data["response"]["status_code"],
                        headers=Headers(data["response"]["headers"]),
                        metadata=data["response"]["extra"],
                        stream=iter([]),
                    )
                ),
                meta=PairMeta(
                    created_at=data["meta"]["created_at"],
                    deleted_at=data["meta"]["deleted_at"],
                ),
                cache_key=data["cache_key"],
            )
        else:
            return IncompletePair(
                id=id,
                request=Request(
                    method=data["request"]["method"],
                    url=data["request"]["url"],
                    headers=Headers(data["request"]["headers"]),
                    metadata=data["request"]["extra"],
                    stream=iter([]),
                ),
                meta=PairMeta(
                    created_at=data["meta"]["created_at"],
                    deleted_at=data["meta"]["deleted_at"],
                ),
            )
