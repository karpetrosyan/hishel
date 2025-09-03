from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Optional, Union, overload

import msgpack
from typing_extensions import Literal, cast

from hishel import CompletePair, IncompletePair
from hishel._core._headers import Headers
from hishel._core.models import PairMeta, Request, Response

if TYPE_CHECKING:
    from hishel._core._sync._storages._lmdb import SyncLmdbStorage


@overload
def pack(
    value: CompletePair | IncompletePair,
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
    value: Union[CompletePair, IncompletePair, uuid.UUID],
    /,
    kind: Literal["pair", "entry_db_key_index"],
) -> bytes:
    if kind == "entry_db_key_index":
        assert isinstance(value, uuid.UUID)
        return value.bytes
    elif kind == "pair":
        assert isinstance(value, (CompletePair, IncompletePair))
        return cast(
            bytes,
            msgpack.packb(
                {
                    "id": value.id.bytes,
                    "request": {
                        "method": value.request.method,
                        "url": value.request.url,
                        "headers": value.request.headers._headers,
                        "extra": value.request.extra,
                    },
                    "response": (
                        {
                            "status_code": value.response.status_code,
                            "headers": value.response.headers._headers,
                            "extra": value.response.extra,
                        }
                    )
                    if isinstance(value, CompletePair)
                    else None,
                    "meta": {
                        "created_at": value.meta.created_at,
                        "deleted_at": value.meta.deleted_at,
                        "refresh_ttl_on_access": value.meta.refresh_ttl_on_access,
                        "ttl": value.meta.ttl,
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
    client: "SyncLmdbStorage",
) -> Union[CompletePair, IncompletePair]: ...


@overload
def unpack(
    value: bytes,
    /,
    kind: Literal["entry_db_key_index"],
    client: Optional["SyncLmdbStorage"] = None,
) -> uuid.UUID: ...


@overload
def unpack(
    value: Optional[bytes],
    /,
    kind: Literal["pair"],
    client: "SyncLmdbStorage",
) -> Optional[Union[CompletePair, IncompletePair]]: ...


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
    client: Optional["SyncLmdbStorage"] = None,
) -> Union[CompletePair, IncompletePair, uuid.UUID, None]:
    if value is None:
        return None
    if kind == "entry_db_key_index":
        return uuid.UUID(bytes=value)
    elif kind == "pair":
        assert client is not None
        data = msgpack.unpackb(value)
        id = uuid.UUID(bytes=data["id"])
        if data.get("response"):
            return CompletePair(
                id=id,
                request=Request(
                    method=data["request"]["method"],
                    url=data["request"]["url"],
                    headers=Headers(data["request"]["headers"]),
                    extra=data["request"]["extra"],
                    stream=client._stream_data_from_cache(id.bytes, client.stream_db, "request"),
                ),
                response=(
                    Response(
                        status_code=data["response"]["status_code"],
                        headers=Headers(data["response"]["headers"]),
                        extra=data["response"]["extra"],
                        stream=client._stream_data_from_cache(id.bytes, client.stream_db, "response"),
                    )
                ),
                meta=PairMeta(
                    created_at=data["meta"]["created_at"],
                    deleted_at=data["meta"]["deleted_at"],
                    ttl=data["meta"]["ttl"],
                    refresh_ttl_on_access=data["meta"]["refresh_ttl_on_access"],
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
                    extra=data["request"]["extra"],
                    stream=client._stream_data_from_cache(id.bytes, client.stream_db, "request"),
                ),
                meta=PairMeta(
                    created_at=data["meta"]["created_at"],
                    deleted_at=data["meta"]["deleted_at"],
                    ttl=data["meta"]["ttl"],
                    refresh_ttl_on_access=data["meta"]["refresh_ttl_on_access"],
                ),
                cache_key=data["cache_key"],
            )
