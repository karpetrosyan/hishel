from __future__ import annotations

from dataclasses import replace
import threading
import time
import uuid
from logging import warning
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Iterable,
    Iterator,
    List,
    Literal,
    Mapping,
    Optional,
    Union,
    assert_never,
    cast,
    overload,
)

from more_itertools import callback_iter
import msgpack

from hishel._core._sync._storages._base import SyncBaseStorage
from hishel._core.models import (
    CompletePair,
    IncompletePair,
    Pair,
    PairMeta,
    Request,
    RequestPair,
    Response,
)

if TYPE_CHECKING:
    from ...._lmdb_types_ import Database, Environment, Transaction


@overload
def pack(
    value: CompletePair,
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
                    "response": {
                        "status_code": value.response.status_code,
                        "headers": value.response.headers._headers,
                        "extra": value.response.extra,
                    }
                    if value.response
                    else None,
                    "meta": value.meta,
                }
            ),
        )
    assert_never(kind)


@overload
def unpack(
    value: bytes,
    /,
    kind: Literal["pair"],
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
        if "response" in data:
            return CompletePair(
                id=id,
                request=Request(
                    method=data["request"]["method"],
                    url=data["request"]["url"],
                    headers=data["request"]["headers"],
                    extra=data["request"]["extra"],
                    stream=client._stream_data_from_cache(id.bytes, client.stream_db, "request"),
                ),
                response=(
                    Response(
                        status_code=data["response"]["status_code"],
                        headers=data["response"]["headers"],
                        extra=data["response"]["extra"],
                        stream=client._stream_data_from_cache(id.bytes, client.stream_db, "response"),
                    )
                ),
                meta=data["meta"],
            )
        else:
            return IncompletePair(
                id=id,
                request=Request(
                    method=data["request"]["method"],
                    url=data["request"]["url"],
                    headers=data["request"]["headers"],
                    extra=data["request"]["extra"],
                    stream=client._stream_data_from_cache(id.bytes, client.stream_db, "request"),
                ),
                meta=data["meta"],
            )
    
class SyncLmdbStorage(SyncBaseStorage):
    _CHUNK_SUFFIX = {
        "request": "request_chunk_{id}",
        "response": "response_chunk_{id}"
    }
    _COMPLETE_CHUNK_SUFFIX = {
        "request": b"request_complete",
        "response": b"response_complete"
    }

    def __init__(
        self,
        env: "Environment",
        *,
        entry_db_name: str = "hishel_entries",
        stream_db_name: str = "hishel_streams",
        entry_db_key_index_db_name: str = "hishel_entry_key_index",
        default_ttl: Optional[float] = None,
        refresh_ttl_on_access: bool = True,
        complete_only: bool = True,
    ) -> None:
        self.env = env

        self.entry_db = env.open_db(entry_db_name.encode("utf-8"))
        self.stream_db = env.open_db(stream_db_name.encode("utf-8"))
        self.entry_key_index_db = env.open_db(
            entry_db_key_index_db_name.encode("utf-8"),
            dupsort=True,
        )
        self.default_ttl = default_ttl
        self.refresh_ttl_on_access = refresh_ttl_on_access
        self.complete_only = complete_only
        self.last_cleanup = float("-inf")

    def create_pair(
        self,
        key: str,
        request: Request,
        /,
        ttl: Optional[float] = None,
        refresh_ttl_on_access: Optional[bool] = None,
    ) -> IncompletePair:
        pair_id = uuid.uuid4()
        pair_meta = PairMeta(created_at=time.time())

        ttl = self.default_ttl if ttl is None else ttl
        if ttl is not None:
            pair_meta["ttl"] = ttl

        pair_meta["refresh_ttl_on_access"] = self.refresh_ttl_on_access if refresh_ttl_on_access is None else refresh_ttl_on_access

        pair = IncompletePair(
            id=pair_id,
            request=request,
            meta=pair_meta,
            cache_key=key
        )
        with self.env.begin(write=True) as txn:
            txn.put(
                key.encode("utf-8"),
                pack(pair_id, kind="entry_db_key_index"),
                db=self.entry_key_index_db,
                dupdata=True,
            )
            txn.put(pair_id.bytes, pack(pair, kind="pair"), db=self.entry_db)

        assert isinstance(request.stream, Iterable)

        request = Request(
            method=request.method,
            url=request.url,
            headers=request.headers,
            extra=request.extra,
            stream=self._stream_data_to_cache(
                request.stream, pair_id.bytes, "request"
            ))
        
        return replace(pair, request=request)

    def add_response(
        self,
        pair_id: uuid.UUID,
        response: Response,
    ) -> CompletePair:
        with self.env.begin(write=True) as txn:
            pair = unpack(txn.get(pair_id.bytes, db=self.entry_db), kind="pair", client=self)

            if pair is None:
                raise ValueError(f"Entry with ID {pair_id} not found.")

            response = replace(response, stream=self._stream_data_to_cache(response.stream, pair_id.bytes, "response"))

            complete_pair = CompletePair(
                id=pair.id,
                request=pair.request,
                response=response,
                meta=pair.meta,
            )
            txn.put(pair_id.bytes, pack(complete_pair, kind="pair"), db=self.entry_db)

        return complete_pair

    def get_pairs(self, key: str) -> List[CompletePair]:
        if self.last_cleanup + 1800 < time.time():
            self.last_cleanup = time.time()
            threading.Thread(target=self._batch_cleanup, daemon=True).start()

        final_pairs: List[CompletePair] = []
        with self.env.begin(write=True) as txn:
            pair_ids = self._get_pair_ids_by_key(key, txn)

            for pair_id in pair_ids:
                pair_data = unpack(txn.get(pair_id.bytes, db=self.entry_db), kind="pair", client=self)
                
                if pair_data is None:
                    warning(f"Pair key index pointing to non-existing pair ID {pair_id}.")
                    continue
                
                if isinstance(pair_data, IncompletePair):
                    continue

                if self._is_soft_deleted(pair_data, txn):
                    continue

                if self._is_corrupted(pair=pair_data, txn=txn):
                    continue

                if self._is_soft_deleted(pair_data):
                    continue

                if self._is_pair_expired(pair_data, txn):
                    self._mark_pair_as_deleted(pair_data, txn)
                elif not self._is_stream_complete("response", pair_data.id, txn):
                    final_pairs.append(
                        replace(pair_data, complete_stream=False)
                    )
                else:
                    final_pairs.append(pair_data)
        return final_pairs

    def update_pair(
        self,
        id: uuid.UUID,
        new_pair: Union[CompletePair,Callable[[CompletePair], CompletePair]],
    ) -> Optional[CompletePair]:
        with self.env.begin(write=True) as txn:
            pair = unpack(txn.get(id.bytes, db=self.entry_db), kind="pair")

            if pair is None:
                return None
            
            if isinstance(pair, IncompletePair):
                return None

            if isinstance(new_pair, CompletePair):
                complete_pair = new_pair
            else:
                complete_pair = new_pair(pair)

            if pair.id != complete_pair.id:
                raise ValueError("Pair ID mismatch")

            txn.put(id.bytes, pack(complete_pair, kind="pair"), db=self.entry_db)

            if pair.cache_key != complete_pair.cache_key:
                self._delete_key_index(pair, txn)
                txn.put(
                    complete_pair.cache_key.encode("utf-8"),
                    pack(complete_pair.id, kind="entry_db_key_index"),
                    db=self.entry_key_index_db,
                    dupdata=True,
                )

        return complete_pair

    def _is_stream_complete(self, kind: Literal["request", "response"], pair_id: uuid.UUID, txn: "Transaction") -> bool:
        return txn.get(b":".join([pair_id.bytes, self._COMPLETE_CHUNK_SUFFIX[kind]]), db=self.stream_db) is not None

    def _check_pair_complete(self, pair: RequestPair, txn: "Transaction") -> bool:
        """
        Check if the pair is complete.
        """
        is_response_complete = txn.get(b":".join([pair.id.bytes, b"response_complete"]), db=self.stream_db) is not None
        is_request_complete = txn.get(b":".join([pair.id.bytes, b"request_complete"]), db=self.stream_db) is not None
        return is_response_complete and is_request_complete

    def _mark_pair_as_deleted(self, pair: RequestPair, txn: "Transaction") -> None:
        """
        Mark the pair as deleted by setting the deleted_at timestamp.
        """
        pair.meta["deleted_at"] = time.time()
        txn.put(
            pair.id.bytes,
            pack(pair, kind="pair"),
            db=self.entry_db,
        )

    def _is_pair_expired(self, pair: Pair, txn: "Transaction") -> bool:
        """
        Check if the pair is expired.
        """
        if pair.meta.ttl is None:
            return False

        created_at = pair.meta.created_at
        ttl = pair.meta.ttl
        return created_at + ttl < time.time()

    def _batch_cleanup(
        self,
    ) -> None:
        """
        Cleanup expired pairs in the database.
        """

        should_mark_as_deleted: List[RequestPair] = []
        should_hard_delete: List[RequestPair] = []
        with self.env.begin(write=True) as txn:
            cursor = txn.cursor(self.entry_db)

            for key, value in cursor:
                assert isinstance(value, bytes)
                pair = unpack(value, kind="pair", client=self)
                if pair is None:
                    continue
                if self._is_pair_expired(pair, txn) and not self._is_soft_deleted(pair):
                    should_mark_as_deleted.append(pair)

                if (self._is_soft_deleted(pair) and self._is_safe_to_hard_delete(pair)) or self._is_corrupted(
                    pair, txn
                ):
                    should_hard_delete.append(pair)

        with self.env.begin(write=True) as txn:
            for pair in should_mark_as_deleted:
                self._mark_pair_as_deleted(pair, txn)

            for pair in should_hard_delete:
                self._hard_delete_pair(pair, txn)

    def _is_soft_deleted(self, pair: Pair) -> bool:
        """
        Check if the pair is soft deleted.
        """
        return pair.meta.deleted_at is not None and pair.meta.deleted_at > 0

    def _is_safe_to_hard_delete(self, pair: Pair) -> bool:
        # if pair was deleted more than one hour ago we assume it's sage to remove
        return bool(pair.meta.deleted_at is not None and (pair.meta.deleted_at + 3600 < time.time()))

    def _is_corrupted(self, pair: IncompletePair | CompletePair, txn: "Transaction") -> bool:
        # if pair was created more than 1 hour ago and still not completed
        if pair.meta.created_at + 3600 < time.time() and isinstance(pair, IncompletePair):
            return True
        
        if isinstance(pair, CompletePair) and not self._is_stream_complete("request", pair.id, txn):
            return True
        return False

    def _delete_key_index(self, pair: Pair, txn: "Transaction") -> None:

        cursor = txn.cursor(self.entry_key_index_db)
        if cursor.set_key(pair.cache_key.encode("utf-8")):
            for value in cursor.iternext_dup():
                if unpack(value, kind="entry_db_key_index") == pair.id:
                    cursor.delete()
                    break
        return None

    def _hard_delete_pair(self, pair: CompletePair | IncompletePair, txn: "Transaction") -> None:
        """
        Permanently delete the pair from the database.
        """

        txn.delete(pair.id.bytes, db=self.entry_db)

        self._delete_key_index(pair, txn)

        self._delete_stream(pair.id.bytes, txn, kind="request")
        self._delete_stream(pair.id.bytes, txn, kind="response")

    def _get_pair_ids_by_key(self, key: str, txn: "Transaction") -> List[uuid.UUID]:
        """
        Get all pair IDs associated with the given key.
        """
        cursor = txn.cursor(self.entry_key_index_db)

        pairs = []

        if cursor.set_key(key.encode("utf-8")):
            for value in cursor.iternext_dup():
                pairs.append(unpack(value, kind="entry_db_key_index"))

        return pairs

    def _delete_single_pair_from_key_index(
        self,
        key: str,
        value: uuid.UUID,
        txn: "Transaction",
    ) -> None:
        """Delete a single key index entry."""

        cursor = txn.cursor(self.entry_key_index_db)
        if cursor.set_key(key.encode("utf-8")):
            for value in cursor.iternext_dup():
                if value == pack(value, kind="entry_db_key_index"):
                    cursor.delete()

    def _delete_stream(
        self,
        entry_id: bytes,
        txn: "Transaction",
        kind: Literal["response", "request"],
    ) -> None:
        """
        Delete the stream associated with the given entry ID.
        """
        suffix = f"{kind}_chunk_{{id}}" if kind in ["response", "request"] else "chunk_{{id}}"
        complete_suffix = b"response_complete" if kind == "response" else b"request_complete"
        # delete all chunks
        i = 0
        while True:
            key = b":".join([entry_id, suffix.format(id=i).encode("utf-8")])
            if not txn.delete(key, db=self.stream_db):
                break
            i += 1

        # delete the complete flag
        txn.delete(b":".join([entry_id, complete_suffix]), db=self.stream_db)

    def _stream_data_to_cache(
        self,
        stream: Iterable[bytes],
        entry_id: bytes,
        kind: Literal["response", "request"],
    ) -> Iterator[bytes]:
        """
        Wrapper around an iterator that also saves the data to the cache in chunks.
        """

        suffix = self._CHUNK_SUFFIX[kind]
        complete_suffix = self._COMPLETE_CHUNK_SUFFIX[kind]
        i = 0
        for chunk in stream:
            with self.env.begin(write=True) as txn:
                txn.put(
                    b":".join([entry_id, suffix.format(id=i).encode("utf-8")]),
                    chunk,
                    db=self.stream_db,
                )
                i += 1
            yield chunk

        with self.env.begin(write=True) as txn:
            # add empty chunk to indicate end of stream
            txn.put(
                b":".join([entry_id, suffix.format(id=i).encode("utf-8")]),
                b"",
                db=self.stream_db,
            )

            # add flag to indicate that the request is complete
            txn.put(b":".join([entry_id, complete_suffix]), b"", db=self.stream_db)

    def _stream_data_from_cache(
        self,
        entry_id: bytes,
        db: "Database",
        kind: Literal["response", "request"],
    ) -> Iterator[bytes]:
        """
        Get an iterator that yields the stream data from the cache.
        """

        suffix = self._CHUNK_SUFFIX[kind]
        i = 0

        with self.env.begin(write=False) as txn:
            while True:
                chunk = txn.get(
                    b":".join([entry_id, suffix.format(id=i).encode("utf-8")]),
                    db=db,
                )
                if chunk is None:
                    break
                if chunk == b"":
                    break
                yield chunk
                i += 1


def print_env_state(client: SyncLmdbStorage) -> str:
    known_dbs = [client.entry_db, client.stream_db]

    state = ""

    with client.env.begin() as txn:
        for db in known_dbs:
            if db is client.entry_db:
                for key, value in txn.cursor(db):
                    state += f"Entry DB - Key: {uuid.UUID(bytes=key)}, Value: ...\n"
            elif db is client.stream_db:
                for key, value in txn.cursor(db):
                    id, rest = key.split(b":")
                    state += f"Stream DB - Key: {uuid.UUID(bytes=id)} - {rest.decode('utf-8')}, Value: ...\n"
    return state
