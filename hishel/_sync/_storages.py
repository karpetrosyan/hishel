import json
import logging
import random
import string
import typing as tp
from pathlib import Path
from threading import Lock

from httpcore import Response

from hishel._serializers import BaseSerializer

from .._files import FileManager
from .._serializers import PickleSerializer
from .._utils import load_path_map

logging.basicConfig(level=1)

__all__ = (
    'BaseStorage',
    'FileStorage'
)

class BaseStorage:

    def __init__(self,
                 serializer: tp.Optional[BaseSerializer] = None) -> None:
        if serializer:  # pragma: no cover
            self._serializer = serializer
        else:
            self._serializer = PickleSerializer()

    def store(self, key: str, response: Response) -> None:
        raise NotImplementedError()

    def retreive(self, key: str) -> tp.Optional[Response]:
        raise NotImplementedError()


class FileStorage(BaseStorage):
    RANDOM_FILENAME_LENGTH = 15

    def __init__(self,
                 serializer: tp.Optional[BaseSerializer] = None,
                 base_path: tp.Optional[Path] = None) -> None:
        super().__init__(serializer)
        if base_path:  # pragma: no cover
            self._base_path = base_path
        else:
            self._base_path = Path('./cache/hishel')

        if not self._base_path.is_dir():
            self._base_path.mkdir(parents=True)
        self._path_map_file = self._base_path / 'maps'

        if self._path_map_file.is_file():  # pragma: no cover
            self._path_map = load_path_map(self._path_map_file)
        else:
            self._path_map: tp.Dict[str, Path] = {}  # type: ignore[no-redef]
            self._path_map_file.touch()

        self._path_map_lock = Lock()
        self._file_manager = FileManager(is_binary=self._serializer.is_binary)

    def _update_maps(self) -> None:
        self._file_manager.write_to(
            str(self._path_map_file),
            json.dumps({
                key: str(value)
                for key, value in self._path_map.items()
            }),
            is_binary=False
        )

    def store(self, key: str, response: Response) -> None:

        with self._path_map_lock:
            if key in self._path_map:  # pragma: no cover
                response_path = self._path_map[key]
            else:
                while True:
                    filename = ''.join(random.choice(string.ascii_letters) for i in range(self.RANDOM_FILENAME_LENGTH))
                    if not (self._base_path / filename).exists():
                        break
                response_path = self._base_path / filename
                self._path_map[key] = response_path
                self._update_maps()

            self._file_manager.write_to(
                str(response_path),
                self._serializer.dumps(response)
            )

    def retreive(self, key: str) -> tp.Optional[Response]:

        with self._path_map_lock:
            if key in self._path_map:
                response_path = self._path_map[key]
                return self._serializer.loads(
                    self._file_manager.read_from(str(response_path))
                )
        return None

    def delete(self, key: str) -> bool:

        with self._path_map_lock:
            if key in self._path_map:
                response_path = self._path_map[key]
                response_path.unlink()
                del self._path_map[key]
                self._update_maps()
                return True
        return False
