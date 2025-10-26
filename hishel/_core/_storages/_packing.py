from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Mapping, Optional, Union, overload

import msgpack
from typing_extensions import Literal, cast

from hishel._core._headers import Headers
from hishel._core.models import EntryMeta, Request, Response


def filter_out_hishel_metadata(data: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in data.items() if not k.startswith("hishel_")}


if TYPE_CHECKING:
    from hishel import Entry


@overload
def pack(
    value: "Entry",
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
    value: Union["Entry", uuid.UUID],
    /,
    kind: Literal["pair", "entry_db_key_index"],
) -> bytes:
    from hishel import Entry

    if kind == "entry_db_key_index":
        assert isinstance(value, uuid.UUID)
        return value.bytes
    elif kind == "pair":
        assert isinstance(value, Entry)
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
                    "response": {
                        "status_code": value.response.status_code,
                        "headers": value.response.headers._headers,
                        "extra": filter_out_hishel_metadata(value.response.metadata),
                    },
                    "meta": {
                        "created_at": value.meta.created_at,
                        "deleted_at": value.meta.deleted_at,
                    },
                    "cache_key": value.cache_key,
                }
            ),
        )
    assert False, f"Unexpected kind: {kind}"


@overload
def unpack(
    value: bytes,
    /,
    kind: Literal["pair"],
) -> "Entry": ...


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
) -> Optional["Entry"]: ...


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
) -> Union["Entry", uuid.UUID, None]:
    from hishel import Entry

    if value is None:
        return None
    if kind == "entry_db_key_index":
        return uuid.UUID(bytes=value)
    elif kind == "pair":
        data = msgpack.unpackb(value)
        id = uuid.UUID(bytes=data["id"])
        return Entry(
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
            meta=EntryMeta(
                created_at=data["meta"]["created_at"],
                deleted_at=data["meta"]["deleted_at"],
            ),
            cache_key=data["cache_key"],
        )
