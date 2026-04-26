from __future__ import annotations

import contextlib
from collections.abc import Iterator, Callable
from dataclasses import replace
from time import time
from typing import TYPE_CHECKING, cast
from uuid import UUID, uuid4

from hishel._core._storages._sync_base import SyncBaseStorage
from hishel._core._storages._packing import pack, unpack
from hishel._core.models import Entry, EntryMeta, Request, Response

if TYPE_CHECKING:
    from redis import RedisError
    from redis import Redis
else:
    try:
        from redis import RedisError
        from redis import Redis
    except ImportError:
        RedisError = None
        Redis = None


class RedisStorage(SyncBaseStorage):
    def __init__(
        self,
        client: Redis[bytes],
        ttl: int | float = 3600,
        key_prefix: str = "hishel",
        soft_delete_ttl: int = 180,
        max_stream_size: int | None = 10 * 1024 * 1024,
    ) -> None:
        if Redis is None:
            raise ImportError(
                "The 'redis' library is required to use the `RedisStorage` integration. "
                "Install hishel with 'pip install hishel[redis]'."
            )

        self._client = client
        self._default_ttl = ttl
        self._key_prefix = key_prefix
        self._soft_delete_ttl = soft_delete_ttl
        self._max_stream_size = max_stream_size

    def _effective_ttl(self, request: Request) -> int | float:
        """Determine the effective TTL for a request, prioritizing request-specific metadata over the default TTL."""
        return cast(int | float, request.metadata.get("hishel_ttl", self._default_ttl))

    def _safe_ttl_ms(self, request: Request) -> int:
        """
        Returns the Redis-level TTL in milliseconds: effective TTL + soft_delete_ttl.

        This ensures Redis doesn't physically delete the entry the moment it logically
        expires; instead, the entry survives long enough to be soft-deleted by
        get_entries, and Redis only reclaims it as a safety net afterward.
        """
        return int((self._effective_ttl(request) + self._soft_delete_ttl) * 1000)

    def create_entry(self, request: Request, response: Response, key: str, id_: UUID | None = None) -> Entry:
        pair_id = id_ or uuid4()
        key_bytes = key.encode()
        safe_ttl_ms = self._safe_ttl_ms(request)

        assert isinstance(response.stream, Iterator), "Response stream must be an Iterator"
        response_with_stream = replace(
            response,
            stream=self._save_stream(response.stream, pair_id, safe_ttl_ms),
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

        with self._client.pipeline(transaction=True) as pipe:
            pipe.set(entry_key, packed, px=safe_ttl_ms)
            pipe.sadd(idx_key, pair_id.hex)
            pipe.pexpire(idx_key, safe_ttl_ms)
            pipe.execute()

        return entry

    def _save_stream(self, stream: Iterator[bytes], pair_id: UUID, safe_ttl_ms: int) -> Iterator[bytes]:
        stream_key = f"{self._key_prefix}:stream:{pair_id.hex}"
        done_key = f"{self._key_prefix}:stream_done:{pair_id.hex}"
        completed = False
        aborted = False
        ttl_set = False
        total_size = 0

        try:
            for chunk in stream:
                if not aborted:
                    total_size += len(chunk)
                    if self._max_stream_size is not None and total_size > self._max_stream_size:
                        aborted = True
                        with contextlib.suppress(RedisError):
                            self._client.delete(stream_key, done_key)
                    else:
                        self._client.rpush(stream_key, chunk)
                        if not ttl_set:
                            # Set a TTL immediately after the first write so the key
                            # can't outlive the process if we die mid-stream (SIGKILL,
                            # OOM, host failure) before reaching the cleanup block.
                            self._client.pexpire(stream_key, safe_ttl_ms)
                            ttl_set = True
                yield chunk

            if not aborted:
                # sentinel to mark end of stream
                self._client.rpush(stream_key, b"")
                self._client.set(done_key, b"1")
                self._client.pexpire(stream_key, safe_ttl_ms)
                self._client.pexpire(done_key, safe_ttl_ms)
            completed = True
        finally:
            if not completed:
                # Upstream errored, or the consumer aborted (e.g. GeneratorExit
                # from an `close()`). Drop whatever partial data we wrote so
                # we don't leave an orphan stream key without a TTL. Suppress
                # Redis errors here — we're already on an error path and don't
                # want to mask the original exception.
                with contextlib.suppress(RedisError):
                    self._client.delete(stream_key, done_key)

    def _is_stream_complete(self, entry_id: UUID) -> bool:
        result = self._client.exists(f"{self._key_prefix}:stream_done:{entry_id.hex}")
        return bool(result)

    def _is_pair_expired(self, pair: Entry) -> bool:
        return pair.meta.created_at + self._effective_ttl(pair.request) < time()

    def _stream_from_cache(self, entry_id: UUID) -> Iterator[bytes]:
        stream_key = f"{self._key_prefix}:stream:{entry_id.hex}"
        length = self._client.llen(stream_key)
        for i in range(length - 1):  # -1 excludes the sentinel
            chunk = self._client.lindex(stream_key, i)
            if chunk is not None:
                yield chunk.encode() if isinstance(chunk, str) else chunk

    def get_entries(self, key: str) -> list[Entry]:
        idx_key = f"{self._key_prefix}:idx:{key}"
        members = self._client.smembers(idx_key)

        result: list[Entry] = []
        for member in members:
            hex_str = member.decode() if isinstance(member, bytes) else member
            entry_key = f"{self._key_prefix}:entry:{hex_str}"

            data = self._client.get(entry_key)
            if data is None:
                self._client.srem(idx_key, member)
                continue

            entry = unpack(data, kind="pair")
            if entry is None:
                continue

            if not self._is_stream_complete(entry.id):
                continue

            if self._is_pair_expired(entry):
                # Logically expired but still present in Redis: soft-delete it now.
                if not self.is_soft_deleted(entry):
                    self.remove_entry(entry.id)
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

        existing = unpack(data, kind="pair")

        updated = new_entry(existing) if callable(new_entry) else new_entry

        if existing.id != updated.id:
            raise ValueError("Entry ID mismatch")

        packed = pack(updated, kind="pair")

        # Preserve the remaining TTL atomically. `xx=True` ensures we don't
        # resurrect an entry that expired between the GET above and this SET;
        # `keepttl=True` preserves the existing expiry without an extra PTTL
        # round trip (and without the TOCTOU it would introduce).
        result = self._client.set(entry_key, packed, xx=True, keepttl=True)
        if result is None:
            # Entry expired between GET and SET; nothing to update.
            return None

        if existing.cache_key != updated.cache_key:
            old_key = existing.cache_key.decode() if isinstance(existing.cache_key, bytes) else existing.cache_key
            new_key = updated.cache_key.decode() if isinstance(updated.cache_key, bytes) else updated.cache_key
            self._client.srem(f"{self._key_prefix}:idx:{old_key}", id.hex)
            self._client.sadd(f"{self._key_prefix}:idx:{new_key}", id.hex)

        return updated

    def refresh_entry_ttl(self, id: UUID) -> None:  # noqa: A002
        """Reset all keys associated with the entry to the full safe TTL."""
        entry_key = f"{self._key_prefix}:entry:{id.hex}"
        data = self._client.get(entry_key)
        if data is None:
            return

        entry = unpack(data, kind="pair")
        if entry is None:
            return

        safe_ttl_ms = self._safe_ttl_ms(entry.request)
        stream_key = f"{self._key_prefix}:stream:{id.hex}"
        done_key = f"{self._key_prefix}:stream_done:{id.hex}"
        idx_key = f"{self._key_prefix}:idx:{entry.cache_key.decode()}"

        self._client.pexpire(entry_key, safe_ttl_ms)
        self._client.pexpire(stream_key, safe_ttl_ms)
        self._client.pexpire(done_key, safe_ttl_ms)
        self._client.pexpire(idx_key, safe_ttl_ms)

    def remove_entry(self, id: UUID) -> None:  # noqa: A002
        entry_key = f"{self._key_prefix}:entry:{id.hex}"
        stream_key = f"{self._key_prefix}:stream:{id.hex}"
        done_key = f"{self._key_prefix}:stream_done:{id.hex}"
        with contextlib.suppress(RedisError):
            data = self._client.get(entry_key)
            if data is None:
                return
            entry = unpack(data, kind="pair")
            if entry is None:
                return

            # Remove from the index first so concurrent get_entries() calls
            # stop finding this entry immediately. The blob itself is left
            # behind with a short TTL so any in-flight stream reader can
            # finish; Redis reclaims the keys when soft_delete_ttl elapses.
            idx_key = f"{self._key_prefix}:idx:{entry.cache_key.decode()}"
            self._client.srem(idx_key, id.hex)
            self._client.expire(entry_key, self._soft_delete_ttl)
            self._client.expire(stream_key, self._soft_delete_ttl)
            self._client.expire(done_key, self._soft_delete_ttl)

    def close(self) -> None:
        self._client.close()  # type: ignore[attr-defined]
