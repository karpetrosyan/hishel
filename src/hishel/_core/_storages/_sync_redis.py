from __future__ import annotations

import contextlib
from collections.abc import Iterator, Awaitable, Callable
from dataclasses import replace
from time import time
from typing import Any, cast
from uuid import UUID, uuid4

from hishel._core._storages._sync_base import SyncBaseStorage
from hishel._core._storages._packing import pack, unpack
from hishel._core.models import Entry, EntryMeta, Request, Response

try:
    from redis import RedisError
    from redis import Redis

    class RedisStorage(SyncBaseStorage):
        def __init__(
            self,
            client: Redis,
            ttl: int | float | None = None,
            key_prefix: str = "hishel",
            soft_delete_ttl: int = 180,
        ) -> None:
            self._client = client
            self._default_ttl = ttl
            self._key_prefix = key_prefix
            self._soft_delete_ttl = soft_delete_ttl

        def _effective_ttl(self, request: Request) -> int | float | None:
            return request.metadata.get("hishel_ttl", self._default_ttl)

        def create_entry(self, request: Request, response: Response, key: str, id_: UUID | None = None) -> Entry:
            pair_id = id_ or uuid4()
            key_bytes = key.encode()
            ttl = self._effective_ttl(request)

            response_with_stream = replace(
                response,
                stream=self._save_stream(cast(Iterator[bytes], response.stream), pair_id, ttl),
            )

            entry = Entry(
                id=pair_id,
                request=request,
                response=response_with_stream,
                meta=EntryMeta(created_at=time()),
                cache_key=key_bytes,
            )

            packed = pack(entry, kind="pair")
            entry_key = f"{self._key_prefix}:entry:{pair_id.hex}"
            idx_key = f"{self._key_prefix}:idx:{key}"

            if ttl is not None:
                self._client.set(entry_key, packed, px=int(ttl * 1000))
            else:
                self._client.set(entry_key, packed)

            cast(int, self._client.sadd(idx_key, pair_id.hex))
            if ttl is not None:
                cast(int, self._client.pexpire(idx_key, int(ttl * 1000)))

            return entry

        def _save_stream(
            self, stream: Iterator[bytes], pair_id: UUID, ttl: int | float | None
        ) -> Iterator[bytes]:
            stream_key = f"{self._key_prefix}:stream:{pair_id.hex}"
            done_key = f"{self._key_prefix}:stream_done:{pair_id.hex}"

            for chunk in stream:
                cast(int, self._client.rpush(stream_key, chunk))
                yield chunk

            # sentinel to mark end of stream
            cast(int, self._client.rpush(stream_key, b""))
            self._client.set(done_key, b"1")
            if ttl is not None:
                cast(int, self._client.pexpire(stream_key, int(ttl * 1000)))
                cast(int, self._client.pexpire(done_key, int(ttl * 1000)))

        def _is_stream_complete(self, entry_id: UUID) -> bool:
            result = self._client.exists(f"{self._key_prefix}:stream_done:{entry_id.hex}")
            return bool(result)

        def _is_pair_expired(self, pair: Entry) -> bool:
            ttl = self._effective_ttl(pair.request)
            return ttl is not None and pair.meta.created_at + ttl < time()

        def _stream_from_cache(self, entry_id: UUID) -> Iterator[bytes]:
            stream_key = f"{self._key_prefix}:stream:{entry_id.hex}"
            length = cast(int, self._client.llen(stream_key))
            for i in range(length - 1):  # -1 excludes the sentinel
                chunk = cast(bytes | None, self._client.lindex(stream_key, i))
                if chunk is not None:
                    yield chunk.encode() if isinstance(chunk, str) else chunk

        def get_entries(self, key: str) -> list[Entry]:
            idx_key = f"{self._key_prefix}:idx:{key}"
            members = cast(set[bytes], self._client.smembers(idx_key))

            result: list[Entry] = []
            for member in members:
                hex_str = member.decode() if isinstance(member, bytes) else member
                entry_key = f"{self._key_prefix}:entry:{hex_str}"

                data = self._client.get(entry_key)
                if data is None:
                    cast(int, self._client.srem(idx_key, member))
                    continue

                entry = unpack(cast(bytes, data), kind="pair")
                if entry is None:
                    continue

                if not self._is_stream_complete(entry.id):
                    continue

                if self._is_pair_expired(entry):
                    continue

                if self.is_soft_deleted(entry):
                    continue

                result.append(
                    replace(
                        entry,
                        response=replace(entry.response, stream=self._stream_from_cache(entry.id)),
                    )
                )

            return result

        def update_entry(
            self,
            id: UUID,  # noqa: A002
            new_entry: Entry | Callable[[Entry], Entry],
        ) -> Entry | None:
            entry_key = f"{self._key_prefix}:entry:{id.hex}"
            data = self._client.get(entry_key)
            if data is None:
                return None

            existing = unpack(cast(bytes, data), kind="pair")

            updated = new_entry(existing) if callable(new_entry) else new_entry

            if existing.id != updated.id:
                raise ValueError("Entry ID mismatch")

            packed = pack(updated, kind="pair")

            if updated.meta.created_at != existing.meta.created_at:
                # TTL refresh: reset all keys to the full original TTL
                ttl = self._effective_ttl(updated.request)
                if ttl is not None:
                    pttl_ms = int(ttl * 1000)
                    stream_key = f"{self._key_prefix}:stream:{id.hex}"
                    done_key = f"{self._key_prefix}:stream_done:{id.hex}"
                    self._client.set(entry_key, packed, px=pttl_ms)
                    cast(int, self._client.pexpire(stream_key, pttl_ms))
                    cast(int, self._client.pexpire(done_key, pttl_ms))
                else:
                    self._client.set(entry_key, packed)
            else:
                # Regular update: preserve remaining TTL
                pttl = cast(int, self._client.pttl(entry_key))
                if pttl > 0:
                    self._client.set(entry_key, packed, px=pttl)
                else:
                    self._client.set(entry_key, packed)

            if existing.cache_key != updated.cache_key:
                old_key = existing.cache_key.decode() if isinstance(existing.cache_key, bytes) else existing.cache_key
                new_key = updated.cache_key.decode() if isinstance(updated.cache_key, bytes) else updated.cache_key
                cast(int, self._client.srem(f"{self._key_prefix}:idx:{old_key}", id.hex))
                cast(int, self._client.sadd(f"{self._key_prefix}:idx:{new_key}", id.hex))

            return updated

        def remove_entry(self, id: UUID) -> None:  # noqa: A002
            entry_key = f"{self._key_prefix}:entry:{id.hex}"
            stream_key = f"{self._key_prefix}:stream:{id.hex}"
            done_key = f"{self._key_prefix}:stream_done:{id.hex}"
            with contextlib.suppress(RedisError):
                data = self._client.get(entry_key)
                if data is None:
                    return
                entry = unpack(cast(bytes, data), kind="pair")
                if entry is None:
                    return
                updated = self.mark_pair_as_deleted(entry)
                packed = pack(updated, kind="pair")
                self._client.set(entry_key, packed, ex=self._soft_delete_ttl)
                self._client.expire(stream_key, self._soft_delete_ttl)
                self._client.expire(done_key, self._soft_delete_ttl)

        def close(self) -> None:
            self._client.close()

except ImportError:

    class RedisStorage:  # type: ignore[no-redef]
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise ImportError(
                "The 'redis' library is required to use the `RedisStorage` integration. "
                "Install hishel with 'pip install hishel[redis]'."
            )
