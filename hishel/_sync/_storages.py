import json
import logging
import random
import string
import typing as tp
from pathlib import Path
from threading import Lock

from httpcore import Request, Response

from hishel._serializers import BaseSerializer

from .._serializers import PickleSerializer
from .._utils import load_path_map

logging.basicConfig(level=1)

__all__ = (
    'AsyncBaseStorage',
    'AsyncFileStorage'
)

class AsyncBaseStorage:

    def __init__(self,
                 serializer: tp.Optional[BaseSerializer] = None) -> None:
        if serializer:
            self._serializer = serializer
        else:
            self._serializer = PickleSerializer()

    def store(self, key: str, response: Response) -> None:
        raise NotImplementedError()

    def retreive(self, key: str, request: Request) -> tp.Optional[Response]:
        raise NotImplementedError()


class AsyncFileStorage(AsyncBaseStorage):
    RANDOM_FILENAME_LENGTH = 15

    def __init__(self,
                 serializer: tp.Optional[BaseSerializer] = None,
                 base_path: tp.Optional[Path] = None) -> None:
        super().__init__(serializer)
        if base_path:
            self._base_path = base_path
        else:
            self._base_path = Path('./cache/hishel')

        if not self._base_path.is_dir():
            self._base_path.mkdir(parents=True)
        self._path_map_file = self._base_path / 'maps'

        if self._path_map_file.is_file():
            self._path_map = load_path_map(self._path_map_file)
        else:
            self._path_map: tp.Dict[str, Path] = {}
            self._path_map_file.touch()

        self._path_map_lock = Lock()

    def _update_maps(self) -> None:
        self._path_map_file.write_text(
            json.dumps({
                key: str(value)
                for key, value in self._path_map.items()
            })
        )

    def store(self, key: str, response: Response) -> None:

        with self._path_map_lock:
            if key in self._path_map:
                logging.debug("Overriding an existing Response")
                response_path = self._path_map[key]
            else:
                while True:
                    filename = ''.join(random.choice(string.ascii_letters) for i in range(self.RANDOM_FILENAME_LENGTH))
                    if not (self._base_path / filename).exists():
                        break
                response_path = self._base_path / filename
                self._path_map[key] = response_path
                self._update_maps()

            if self._serializer.is_binary:
                response_path.write_bytes(self._serializer.dumps(response))
            else:
                response_path.write_text(self._serializer.dumps(response))

    def retreive(self, key: str) -> tp.Optional[Response]:

        with self._path_map_lock:
            if key in self._path_map:
                response_path = self._path_map[key]
                if self._serializer.is_binary:
                    return self._serializer.loads(response_path.read_bytes())
                else:
                    return self._serializer.loads(response_path.read_text())

    def delete(self, key: str) -> bool:

        with self._path_map_lock:
            if key in self._path_map:
                response_path = self._path_map[key]
                response_path.unlink()
                del self._path_map[key]
                self._update_maps()
                return True
        return False
