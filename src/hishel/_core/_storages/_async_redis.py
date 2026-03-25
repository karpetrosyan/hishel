from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from time import time
from typing import cast
from uuid import UUID, uuid4

from redis import RedisError
from redis.asyncio import Redis

from hishel._core._storages._async_base import AsyncBaseStorage
from hishel._core._storages._packing import pack, unpack
from hishel._core.models import Entry, EntryMeta, Request, Response


class AsyncRedisStorage(AsyncBaseStorage):
    def __init__(self, client: Redis, ttl: int | float | None = None, key_prefix: str = "hishel") -> None:
        self._client = client
        self._default_ttl = ttl
        self._key_prefix = key_prefix

    async def create_entry(self, request: Request, response: Response, key: str, id_: UUID | None = None) -> Entry:
        pair_id = id_ or uuid4()
        key_bytes = key.encode()

        response_with_stream = replace(
            response,
            stream=self._save_stream(cast(AsyncIterator[bytes], response.stream), pair_id),
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

        if self._default_ttl is not None:
            await self._client.set(entry_key, packed, ex=int(self._default_ttl))
        else:
            await self._client.set(entry_key, packed)

        await self._client.sadd(idx_key, pair_id.hex)  # type: ignore[misc]
        if self._default_ttl is not None:
            await self._client.expire(idx_key, int(self._default_ttl))

        return entry

    async def _save_stream(self, stream: AsyncIterator[bytes], pair_id: UUID) -> AsyncIterator[bytes]:
        stream_key = f"{self._key_prefix}:stream:{pair_id.hex}"
        done_key = f"{self._key_prefix}:stream_done:{pair_id.hex}"

        async for chunk in stream:
            await self._client.rpush(stream_key, chunk)  # type: ignore[misc]
            yield chunk

        # sentinel to mark end of stream
        await self._client.rpush(stream_key, b"")  # type: ignore[misc]
        await self._client.set(done_key, b"1")
        if self._default_ttl is not None:
            await self._client.expire(stream_key, int(self._default_ttl))
            await self._client.expire(done_key, int(self._default_ttl))

    async def _is_stream_complete(self, entry_id: UUID) -> bool:
        result = await self._client.exists(f"{self._key_prefix}:stream_done:{entry_id.hex}")
        return bool(result)

    def _is_pair_expired(self, pair: Entry) -> bool:
        ttl = pair.request.metadata.get("hishel_ttl", self._default_ttl)
        return ttl is not None and pair.meta.created_at + ttl < time()

    async def _stream_from_cache(self, entry_id: UUID) -> AsyncIterator[bytes]:
        stream_key = f"{self._key_prefix}:stream:{entry_id.hex}"
        length = cast(int, await self._client.llen(stream_key))  # type: ignore[misc]
        for i in range(length - 1):  # -1 excludes the sentinel
            chunk = cast(bytes | None, await self._client.lindex(stream_key, i))  # type: ignore[misc]
            if chunk is not None:
                yield chunk.encode() if isinstance(chunk, str) else chunk

    async def get_entries(self, key: str) -> list[Entry]:
        idx_key = f"{self._key_prefix}:idx:{key}"
        members = cast(set[bytes], await self._client.smembers(idx_key))  # type: ignore[misc]

        result: list[Entry] = []
        for member in members:
            hex_str = member.decode() if isinstance(member, bytes) else member
            entry_key = f"{self._key_prefix}:entry:{hex_str}"

            data = await self._client.get(entry_key)
            if data is None:
                await self._client.srem(idx_key, member)  # type: ignore[misc]
                continue

            entry = unpack(cast(bytes, data), kind="pair")
            if entry is None:
                continue

            if not await self._is_stream_complete(entry.id):
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

    async def update_entry(
        self,
        id: UUID,  # noqa: A002
        new_entry: Entry | Callable[[Entry], Entry],
    ) -> Entry | None:
        entry_key = f"{self._key_prefix}:entry:{id.hex}"
        data = await self._client.get(entry_key)
        if data is None:
            return None

        existing = unpack(cast(bytes, data), kind="pair")

        updated = new_entry(existing) if callable(new_entry) else new_entry

        if existing.id != updated.id:
            raise ValueError("Entry ID mismatch")

        pttl = cast(int, await self._client.pttl(entry_key))
        packed = pack(updated, kind="pair")
        if pttl > 0:
            await self._client.set(entry_key, packed, px=pttl)
        else:
            await self._client.set(entry_key, packed)

        if existing.cache_key != updated.cache_key:
            old_key = existing.cache_key.decode() if isinstance(existing.cache_key, bytes) else existing.cache_key
            new_key = updated.cache_key.decode() if isinstance(updated.cache_key, bytes) else updated.cache_key
            await self._client.srem(f"{self._key_prefix}:idx:{old_key}", id.hex)  # type: ignore[misc]
            await self._client.sadd(f"{self._key_prefix}:idx:{new_key}", id.hex)  # type: ignore[misc]

        return updated

    async def remove_entry(self, id: UUID) -> None:  # noqa: A002
        entry_key = f"{self._key_prefix}:entry:{id.hex}"
        stream_key = f"{self._key_prefix}:stream:{id.hex}"
        done_key = f"{self._key_prefix}:stream_done:{id.hex}"
        with contextlib.suppress(RedisError):
            # don't let deletes prevent reads; failures are non-fatal
            await self._client.delete(entry_key, stream_key, done_key)

    async def close(self) -> None:
        await self._client.aclose()
