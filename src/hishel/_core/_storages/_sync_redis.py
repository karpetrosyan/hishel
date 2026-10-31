from __future__ import annotations

import contextlib
import logging
import math
from collections.abc import Iterator
from dataclasses import replace
from time import time
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

import msgpack

from hishel._core._headers import Headers
from hishel._core._storages._sync_base import SyncBaseStorage
from hishel._core._storages._packing import pack, unpack
from hishel._core.models import Entry, Request, Response
from hishel._utils import make_sync_iterator

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

logger = logging.getLogger(__name__)

# Target size (bytes) of a stored stream chunk. Incoming chunks are
# re-chunked to this size before being written so the number of Redis
# round trips stays bounded regardless of how the transport chunks the
# response.
STORAGE_CHUNK_SIZE = 131072
# Active readers extend an entry's keys at most this often (seconds).
MAX_TOUCH_INTERVAL = 60


class RedisStorage(SyncBaseStorage):
    """
    An entry is visible while it is in its cache key's index, a sorted set
    scored by expires_at. It joins once its body is complete and leaves when it
    is removed. Its stream_done key holds its chunk count, TTL deadline, TTI and
    cache key.

    Its data keys outlive expires_at by soft_delete_ttl, so that readers already
    streaming it can finish, and Redis then reclaims them. Active readers keep
    that window open by extending the keys. Size limits and eviction are left to
    the server's maxmemory settings.

    Extending keys uses PEXPIRE GT, which needs Redis 7.
    """

    def __init__(
        self,
        client: Redis[bytes],
        *,
        default_ttl: float | None = 3600,
        default_tti: float | None = None,
        max_stream_size: int | None = 10 * 1024 * 1024,
        key_prefix: str = "hishel",
        soft_delete_ttl: float = 180,
    ) -> None:
        if Redis is None:
            raise ImportError(
                "The 'redis' library is required to use the `RedisStorage` integration. "
                "Install hishel with 'pip install hishel[redis]'."
            )

        super().__init__(default_ttl=default_ttl, default_tti=default_tti, max_stream_size=max_stream_size)
        self._client = client
        self._key_prefix = key_prefix
        self._soft_delete_ttl_ms = int(soft_delete_ttl * 1000)
        self._touch_interval = min(MAX_TOUCH_INTERVAL, soft_delete_ttl / 2)

    def _data_keys(self, id: UUID) -> tuple[str, str, str]:  # noqa: A002
        return (
            f"{self._key_prefix}:entry:{id.hex}",
            f"{self._key_prefix}:stream:{id.hex}",
            f"{self._key_prefix}:stream_done:{id.hex}",
        )

    def _idx_key(self, key: str) -> str:
        return f"{self._key_prefix}:idx:{key}"

    def _keys_ttl_ms(self, expires_at: float | None, now: float) -> int | None:
        """How long the keys of an entry expiring at ``expires_at`` must live, or None if they never expire."""
        if expires_at is None:
            return None
        return int(max(expires_at - now, 0) * 1000) + self._soft_delete_ttl_ms

    def create_entry(
        self,
        request: Request,
        response: Response,
        key: str,
        *,
        ttl: float | None = None,
        tti: float | None = None,
    ) -> Entry:
        body = response.stream if response.stream is not None else make_sync_iterator([])
        assert isinstance(body, Iterator), "Response stream must be an Iterator"

        ttl_deadline, tti = self._limits(ttl, tti, time())
        entry = Entry(
            id=uuid4(),
            request=request,
            response=response,
        )

        entry_key, _, _ = self._data_keys(entry.id)
        try:
            # Short-lived until the body is complete, so that nothing outlives a
            # writer that dies mid-stream (SIGKILL, OOM, host failure).
            self._client.set(entry_key, pack(request, response), px=self._soft_delete_ttl_ms)
        except RedisError:
            logger.exception("hishel: could not store entry, serving the response uncached")
            return entry

        stream = self._save_stream(body, entry.id, key, ttl_deadline, tti)
        return replace(entry, response=replace(response, stream=stream))

    def _save_stream(
        self,
        stream: Iterator[bytes],
        id_: UUID,
        key: str,
        ttl_deadline: float | None,
        tti: float | None,
    ) -> Iterator[bytes]:
        """
        Yield the stream unchanged while saving it, re-chunked to STORAGE_CHUNK_SIZE.

        Saving stops on the first failure, or when the response gets too big to
        cache, but the consumer keeps receiving the stream either way.
        """
        entry_key, stream_key, _ = self._data_keys(id_)
        chunk_count = 0
        total_size = 0
        buffer = bytearray()
        saving = True
        completed = False

        def write_chunk(data: bytes) -> bool:
            nonlocal chunk_count
            try:
                with self._client.pipeline(transaction=True) as pipe:
                    pipe.rpush(stream_key, data)
                    pipe.pexpire(stream_key, self._soft_delete_ttl_ms)
                    pipe.pexpire(entry_key, self._soft_delete_ttl_ms)
                    pipe.execute()
            except RedisError:
                logger.exception("hishel: cache write failed")
                return False
            chunk_count += 1
            return True

        try:
            for chunk in stream:
                if saving:
                    total_size += len(chunk)
                    if self.max_stream_size is not None and total_size > self.max_stream_size:
                        saving = False
                    else:
                        buffer += chunk
                        while saving and len(buffer) >= STORAGE_CHUNK_SIZE:
                            saving = write_chunk(bytes(buffer[:STORAGE_CHUNK_SIZE]))
                            del buffer[:STORAGE_CHUNK_SIZE]
                    if not saving:
                        buffer.clear()
                        self._delete_unfinished(id_)
                yield chunk

            if saving and buffer:
                saving = write_chunk(bytes(buffer))
            if saving:
                completed = self._publish(id_, key, chunk_count, ttl_deadline, tti)
        finally:
            # Upstream failed or the consumer stopped reading. If this gets
            # cancelled too, the short TTLs reclaim the keys later.
            if not completed:
                self._delete_unfinished(id_)

    def _delete_unfinished(self, id: UUID) -> None:  # noqa: A002
        entry_key, stream_key, _ = self._data_keys(id)
        with contextlib.suppress(RedisError):
            self._client.delete(entry_key, stream_key)

    def _publish(
        self,
        id_: UUID,
        key: str,
        chunk_count: int,
        ttl_deadline: float | None,
        tti: float | None,
    ) -> bool:
        """Make a fully written entry visible, unless it was removed or lost its data meanwhile."""
        now = time()
        expires_at = self._expires_at(ttl_deadline, tti, now)
        ttl_ms = self._keys_ttl_ms(expires_at, now)
        idx_key = self._idx_key(key)
        entry_key, stream_key, done_key = self._data_keys(id_)

        try:
            with self._client.pipeline(transaction=True) as pipe:
                # remove_entry deletes the entry key of an entry being written,
                # which aborts the transaction below if it happens after this.
                pipe.watch(entry_key)
                if not self._client.exists(entry_key) or self._client.llen(stream_key) != chunk_count:
                    return False
                idx_ttl_ms = self._client.pttl(idx_key)

                pipe.multi()
                pipe.set(done_key, msgpack.packb((chunk_count, ttl_deadline, tti, key.encode())))
                for data_key in (entry_key, stream_key, done_key):
                    if ttl_ms is None:
                        pipe.persist(data_key)
                    else:
                        pipe.pexpire(data_key, ttl_ms)
                pipe.zremrangebyscore(idx_key, "-inf", now)
                pipe.zadd(idx_key, {id_.hex: math.inf if expires_at is None else expires_at})
                # The index must live as long as its longest-living entry.
                if ttl_ms is None:
                    pipe.persist(idx_key)
                elif idx_ttl_ms == -2 or 0 <= idx_ttl_ms < ttl_ms:
                    pipe.pexpire(idx_key, ttl_ms)
                pipe.execute()
            return True
        except RedisError:
            logger.exception("hishel: could not store entry")
            return False

    def _stream_from_cache(self, id: UUID, chunk_count: int, last_touch: float) -> Iterator[bytes]:  # noqa: A002
        _, stream_key, _ = self._data_keys(id)
        for chunk_number in range(chunk_count):
            chunk = self._client.lindex(stream_key, chunk_number)
            if chunk is None:
                raise RuntimeError(
                    "Cached response was deleted while it was being read. "
                    "Increase soft_delete_ttl if consumers stall for longer than that."
                )

            now = time()
            if now - last_touch >= self._touch_interval:
                last_touch = now
                with contextlib.suppress(RedisError):
                    with self._client.pipeline(transaction=True) as pipe:
                        for data_key in self._data_keys(id):
                            pipe.pexpire(data_key, self._soft_delete_ttl_ms, gt=True)
                        pipe.execute()

            yield chunk

    def get_entries(self, key: str) -> list[Entry]:
        idx_key = self._idx_key(key)
        now = time()
        members = self._client.zrangebyscore(idx_key, f"({now}", "+inf", withscores=True)

        result: list[Entry] = []
        for member, expires_at in members:
            id_hex = member.decode() if isinstance(member, bytes) else member
            id_ = UUID(hex=id_hex)
            entry_key, stream_key, done_key = self._data_keys(id_)

            data = self._client.get(entry_key)
            done = self._client.get(done_key)
            # The server can evict any key at any time, not just whole entries.
            if data is None or done is None:
                self._client.zrem(idx_key, member)
                continue

            try:
                request, response = unpack(bytes(data))
                chunk_count, ttl_deadline, tti, _ = msgpack.unpackb(done)
            except Exception:
                logger.exception("hishel: dropping an entry that could not be decoded")
                self._client.zrem(idx_key, member)
                continue

            if self._client.llen(stream_key) != chunk_count:
                self._client.zrem(idx_key, member)
                continue

            # Most hits write nothing. Otherwise every read would be a write.
            new_expires_at = self._expires_at(ttl_deadline, tti, now)
            if tti is not None and new_expires_at is not None and new_expires_at - expires_at >= tti / 2:
                self._extend_expiry(idx_key, id_, new_expires_at, now)

            # Unexpired entries have at least soft_delete_ttl left, so this
            # lookup counts as the reader's first touch.
            result.append(
                Entry(
                    id=id_,
                    request=request,
                    response=replace(response, stream=self._stream_from_cache(id_, chunk_count, now)),
                )
            )

        return result

    def _extend_expiry(self, idx_key: str, id: UUID, expires_at: float, now: float) -> None:  # noqa: A002
        ttl_ms = self._keys_ttl_ms(expires_at, now)
        assert ttl_ms is not None
        with contextlib.suppress(RedisError):
            with self._client.pipeline(transaction=True) as pipe:
                # xx stops this from bringing back an entry that remove_entry
                # took out of the index after the lookup.
                pipe.zadd(idx_key, {id.hex: expires_at}, xx=True)
                for key in (*self._data_keys(id), idx_key):
                    pipe.pexpire(key, ttl_ms, gt=True)
                pipe.execute()

    def update_headers(self, id: UUID, headers: Headers) -> None:  # noqa: A002
        entry_key, _, _ = self._data_keys(id)
        data = self._client.get(entry_key)
        if data is None:
            return

        request, response = unpack(bytes(data))
        updated = pack(request, replace(response, headers=headers))
        # `xx=True` ensures we don't resurrect an entry that expired between the
        # GET above and this SET; `keepttl=True` preserves the existing expiry.
        self._client.set(entry_key, updated, xx=True, keepttl=True)

    def remove_entry(self, id: UUID) -> None:  # noqa: A002
        entry_key, stream_key, done_key = self._data_keys(id)
        with contextlib.suppress(RedisError):
            done = self._client.get(done_key)
            # An entry still being written has no readers to protect.
            if done is None:
                self._delete_unfinished(id)
                return

            # Remove from the index first so concurrent get_entries() calls
            # stop finding this entry immediately. The blob itself is left
            # behind with a short TTL so any in-flight stream reader can
            # finish; Redis reclaims the keys when soft_delete_ttl elapses.
            _, _, _, cache_key = msgpack.unpackb(done)
            self._client.zrem(self._idx_key(cache_key.decode()), id.hex)
            self._client.pexpire(entry_key, self._soft_delete_ttl_ms)
            self._client.pexpire(stream_key, self._soft_delete_ttl_ms)
            self._client.pexpire(done_key, self._soft_delete_ttl_ms)

    def close(self) -> None:
        self._client.close()  # type: ignore[attr-defined]
