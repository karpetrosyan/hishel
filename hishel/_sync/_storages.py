import logging
import time
import typing as tp
from pathlib import Path

import redis
from httpcore import Response

from hishel._serializers import BaseSerializer

from .._files import FileManager
from .._serializers import JSONSerializer
from .._synchronization import Lock

logger = logging.getLogger("hishel.storages")

__all__ = ("FileStorage", "RedisStorage")


class BaseStorage:
    def __init__(self, serializer: tp.Optional[BaseSerializer] = None) -> None:
        if serializer:  # pragma: no cover
            self._serializer = serializer
        else:
            self._serializer = JSONSerializer()

    def store(self, key: str, response: Response) -> None:
        raise NotImplementedError()

    def retreive(self, key: str) -> tp.Optional[Response]:
        raise NotImplementedError()

    def close(self) -> None:
        raise NotImplementedError()


class FileStorage(BaseStorage):
    def __init__(
        self,
        serializer: tp.Optional[BaseSerializer] = None,
        base_path: tp.Optional[Path] = None,
        max_cache_age: tp.Optional[int] = None,
    ) -> None:
        super().__init__(serializer)
        if base_path:  # pragma: no cover
            self._base_path = base_path
        else:
            self._base_path = Path("./.cache/hishel")

        if not self._base_path.is_dir():
            self._base_path.mkdir(parents=True)

        self._file_manager = FileManager(is_binary=self._serializer.is_binary)
        self._max_cache_age = max_cache_age
        self._lock = Lock()

    def store(self, key: str, response: Response) -> None:
        response_path = self._base_path / key

        with self._lock:
            self._file_manager.write_to(
                str(response_path), self._serializer.dumps(response)
            )
        self._remove_expired_caches()

    def retreive(self, key: str) -> tp.Optional[Response]:
        response_path = self._base_path / key

        with self._lock:
            if response_path.exists():
                return self._serializer.loads(
                    self._file_manager.read_from(str(response_path))
                )
        self._remove_expired_caches()
        return None

    def close(self) -> None:
        return

    def _remove_expired_caches(self) -> None:
        if self._max_cache_age is None:
            return

        with self._lock:
            for file in self._base_path.iterdir():
                if file.is_file():
                    age = time.time() - file.stat().st_mtime
                    if age > self._max_cache_age:
                        file.unlink()


class RedisStorage(BaseStorage):
    def __init__(
        self,
        serializer: tp.Optional[BaseSerializer] = None,
        client: tp.Optional[redis.Redis] = None,  # type: ignore
        max_cache_age: tp.Optional[int] = None,
    ) -> None:
        super().__init__(serializer)

        if client is None:
            self._client = redis.Redis()  # type: ignore
        else:  # pragma: no cover
            self._client = client
        self._max_cache_age = max_cache_age

    def store(self, key: str, response: Response) -> None:
        self._client.set(
            key, self._serializer.dumps(response), ex=self._max_cache_age
        )

    def retreive(self, key: str) -> tp.Optional[Response]:
        cached_response = self._client.get(key)
        if cached_response is None:
            return None

        return self._serializer.loads(cached_response)

    def close(self) -> None:  # pragma: no cover
        self._client.close()
