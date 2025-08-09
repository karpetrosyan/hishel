"""
Some CRUD abstractioin for entities
"""

import uuid
from typing import TYPE_CHECKING, Optional, Union, overload

from kavo.models import CacheEntry, Request, Response, StampedeInfo
from kavo.pack import pack, unpack

if TYPE_CHECKING:
    from kavo.types_ import Database, Transaction

### Response


def get_response(txn: "Transaction", response_id: uuid.UUID, response_db: "Database") -> Response | None:
    data = txn.get(response_id.bytes, db=response_db)
    if data is None:
        return None
    return unpack(data, "response")


def get_response_batch(txn: "Transaction", ids: list[uuid.UUID], response_db: "Database") -> dict[uuid.UUID, Response]:
    responses: dict[uuid.UUID, Response] = {}
    for response_id in ids:
        response = get_response(txn, response_id, response_db)
        if response is not None:
            responses[response_id] = response
    return responses


def put_response(
    txn: "Transaction",
    response_id: uuid.UUID,
    response: Response,
    response_db: "Database",
) -> None:
    txn.put(
        response_id.bytes,
        pack(response, "response"),
        db=response_db,
    )


def delete_response(
    txn: "Transaction",
    response_id: uuid.UUID,
    response_db: "Database",
) -> bool:
    return txn.delete(
        response_id.bytes,
        db=response_db,
    )


def get_entry(txn: "Transaction", entry_key: str, entries_db: "Database") -> CacheEntry | None:
    data = txn.get(entry_key.encode(), db=entries_db)
    if data is None:
        return None
    return unpack(data, "entry")


def put_entry(
    txn: "Transaction",
    key: str,
    entry: CacheEntry,
    db: "Database",
) -> None:
    txn.put(key.encode(), pack(entry, "entry"), db=db)


## Chunk


def put_chunk(txn: "Transaction", id: bytes, chunk: bytes, db: "Database") -> None:
    txn.put(id, chunk, db=db)


def get_chunk(txn: "Transaction", id: bytes, db: "Database") -> Optional[bytes]:
    return txn.get(id, db=db)


def delete_chunk(txn: "Transaction", id: bytes, db: "Database") -> bool:
    return txn.delete(id, db=db)


### Request


def put_request(request_id: uuid.UUID, txn: "Transaction", data: Request, db: "Database") -> None:
    txn.put(request_id.bytes, pack(data, "request"), db=db)


def delete_request(txn: "Transaction", id: uuid.UUID, db: "Database") -> bool:
    return txn.delete(id.bytes, db=db)


### Stampede


def get_stampede(txn: "Transaction", key: str, db: "Database") -> Union[StampedeInfo, None]:
    stampede = txn.get(key.encode(), db=db)

    if stampede is None:
        return stampede

    return unpack(stampede, "stampede")


def delete_stampede(txn: "Transaction", key: str, db: "Database") -> bool:
    return txn.delete(key.encode(), db=db)


def put_stampede(txn: "Transaction", key: str, stampede_info: StampedeInfo, db: "Database") -> None:
    return txn.put(key.encode(), pack(stampede_info, "stampede"), db=db)


### Staleness Tracker


def encode_staleness_tracker_key(timestamp: int, response_id: uuid.UUID) -> bytes:
    """
    Encodes the staleness tracker key.
    """
    return timestamp.to_bytes(8, "big") + response_id.bytes


def decode_staleness_tracker_key(key: bytes) -> tuple[int, uuid.UUID]:
    """
    Decodes the staleness tracker key.
    """
    timestamp = int.from_bytes(key[:8], byteorder="big")
    response_id = uuid.UUID(bytes=key[8:])
    return timestamp, response_id


@overload
def delete_staleness_tracker(
    txn: "Transaction",
    *,
    timestamp: int,
    response_id: uuid.UUID,
    db: "Database",
) -> bool: ...


@overload
def delete_staleness_tracker(
    txn: "Transaction",
    *,
    key: bytes,
    db: "Database",
) -> bool: ...


def delete_staleness_tracker(
    txn: "Transaction",
    *,
    timestamp: Optional[int] = None,
    response_id: Optional[uuid.UUID] = None,
    db: Optional["Database"] = None,
    key: Optional[bytes] = None,
) -> bool:
    """
    Deletes the staleness tracker for a response.
    """
    if key:
        return txn.delete(key, db=db)

    assert timestamp
    assert response_id
    return txn.delete(encode_staleness_tracker_key(timestamp, response_id), db=db)


@overload
def put_staleness_tracker(
    txn: "Transaction",
    *,
    key: Union[bytes, None],
    response_id: uuid.UUID,
    db: "Database",
) -> None: ...


@overload
def put_staleness_tracker(
    txn: "Transaction",
    *,
    timestamp: int,
    response_id: uuid.UUID,
    db: "Database",
) -> None: ...


def put_staleness_tracker(
    txn: "Transaction",
    *,
    db: "Database",
    response_id: uuid.UUID,
    timestamp: Optional[int] = None,
    key: Union[bytes, None] = None,
) -> None:
    if key is not None:
        txn.put(
            key,
            pack({"response_id": response_id}, "staleness_tracker"),
            db=db,
        )
        return

    assert timestamp
    assert response_id
    txn.put(
        encode_staleness_tracker_key(timestamp, response_id),
        pack({"response_id": response_id}, "staleness_tracker"),
        db=db,
    )
