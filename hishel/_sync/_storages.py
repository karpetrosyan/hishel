import logging
import typing as tp
from pathlib import Path

import redis
from httpcore import Response

from hishel._serializers import BaseSerializer

from .._files import FileManager
from .._serializers import DictSerializer

logger = logging.getLogger('hishel.storages')

__all__ = (
    'FileStorage',
    'RedisStorage'
)

class BaseStorage:

    def __init__(self,
                 serializer: tp.Optional[BaseSerializer] = None) -> None:
        if serializer:  # pragma: no cover
            self._serializer = serializer
        else:
            self._serializer = DictSerializer()

    def store(self, key: str, response: Response) -> None:
        raise NotImplementedError()

    def retreive(self, key: str) -> tp.Optional[Response]:
        raise NotImplementedError()

    def aclose(self) -> None:
        raise NotImplementedError()


class FileStorage(BaseStorage):

    def __init__(self,
                 serializer: tp.Optional[BaseSerializer] = None,
                 base_path: tp.Optional[Path] = None) -> None:
        super().__init__(serializer)
        if base_path:  # pragma: no cover
            self._base_path = base_path
        else:
            self._base_path = Path('./.cache/hishel')

        if not self._base_path.is_dir():
            self._base_path.mkdir(parents=True)

        self._file_manager = FileManager(is_binary=self._serializer.is_binary)

    def store(self, key: str, response: Response) -> None:

        response_path = self._base_path / key
        self._file_manager.write_to(
            str(response_path),
            self._serializer.dumps(response)
        )

    def retreive(self, key: str) -> tp.Optional[Response]:

        response_path = self._base_path / key

        if response_path.exists():
            return self._serializer.loads(
                self._file_manager.read_from(str(response_path))
            )
        return None

    def aclose(self) -> None:
        return

    def delete(self, key: str) -> bool:
        response_path = self._base_path / key

        if response_path.exists():
            response_path.unlink()
            return True
        return False


class RedisStorage(BaseStorage):

    def __init__(self,
                 serializer: tp.Optional[BaseSerializer] = None,
                 client: tp.Optional[redis.Redis] = None) -> None:
        super().__init__(serializer)

        if client is None:
            self.client = redis.Redis()
        else:
            self.client = client

    def store(self, key: str, response: Response) -> None:

        self.client.set(key, self._serializer.dumps(response))

    def retreive(self, key: str) -> tp.Optional[Response]:

        cached_response = self.client.get(key)
        if cached_response is None:
            return None

        return self._serializer.loads(cached_response)

    def delete(self, key: str) -> bool:

        return self.client.delete(key) > 0
