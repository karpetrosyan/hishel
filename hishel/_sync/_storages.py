import logging
import time
import typing as tp
from pathlib import Path

try:
    import sqlite3
except ImportError:  # pragma: no cover
    sqlite3 = None  # type: ignore

from httpcore import Request, Response

from hishel._serializers import BaseSerializer

from .._files import FileManager
from .._serializers import JSONSerializer, Metadata
from .._synchronization import Lock

logger = logging.getLogger("hishel.storages")

__all__ = ("FileStorage", "RedisStorage", "SQLiteStorage")

try:
    import redis
except ImportError:  # pragma: no cover
    redis = None  # type: ignore


class BaseStorage:
    def __init__(
        self,
        serializer: tp.Optional[BaseSerializer] = None,
        ttl: tp.Optional[int] = None,
    ) -> None:
        self._serializer = serializer or JSONSerializer()
        self._ttl = ttl

    def store(self, key: str, response: Response, request: Request, metadata: Metadata) -> None:
        raise NotImplementedError()

    def retreive(self, key: str) -> tp.Optional[tp.Tuple[Response, Request, Metadata]]:
        raise NotImplementedError()

    def close(self) -> None:
        raise NotImplementedError()


class FileStorage(BaseStorage):
    """
    A simple file storage.

    :param serializer: Serializer capable of serializing and de-serializing http responses, defaults to None
    :type serializer: tp.Optional[BaseSerializer], optional
    :param base_path: A storage base path where the responses should be saved, defaults to None
    :type base_path: tp.Optional[Path], optional
    :param ttl: Specifies the maximum number of seconds that the response can be cached, defaults to None
    :type ttl: tp.Optional[int], optional
    """

    def __init__(
        self,
        serializer: tp.Optional[BaseSerializer] = None,
        base_path: tp.Optional[Path] = None,
        ttl: tp.Optional[int] = None,
    ) -> None:
        super().__init__(serializer, ttl)

        self._base_path = Path(base_path) if base_path is not None else Path(".cache/hishel")

        if not self._base_path.is_dir():
            self._base_path.mkdir(parents=True)

        self._file_manager = FileManager(is_binary=self._serializer.is_binary)
        self._lock = Lock()

    def store(self, key: str, response: Response, request: Request, metadata: Metadata) -> None:
        """
        Stores the response in the cache.

        :param key: Hashed value of concatenated HTTP method and URI
        :type key: str
        :param response: An HTTP response
        :type response: httpcore.Response
        :param request: An HTTP request
        :type request: httpcore.Request
        :param metadata: Additional information about the stored response
        :type metadata: Metadata
        """
        response_path = self._base_path / key

        with self._lock:
            self._file_manager.write_to(
                str(response_path),
                self._serializer.dumps(response=response, request=request, metadata=metadata),
            )
        self._remove_expired_caches()

    def retreive(self, key: str) -> tp.Optional[tp.Tuple[Response, Request, Metadata]]:
        """
        Retreives the response from the cache using his key.

        :param key: Hashed value of concatenated HTTP method and URI
        :type key: str
        :return: An HTTP response and his HTTP request.
        :rtype: tp.Optional[tp.Tuple[Response, Request, Metadata]]
        """

        response_path = self._base_path / key

        self._remove_expired_caches()
        with self._lock:
            if response_path.exists():
                return self._serializer.loads(self._file_manager.read_from(str(response_path)))
        return None

    def close(self) -> None:
        return

    def _remove_expired_caches(self) -> None:
        if self._ttl is None:
            return

        with self._lock:
            for file in self._base_path.iterdir():
                if file.is_file():
                    age = time.time() - file.stat().st_mtime
                    if age > self._ttl:
                        file.unlink()


class SQLiteStorage(BaseStorage):
    """
    A simple sqlite3 storage.

    :param serializer: Serializer capable of serializing and de-serializing http responses, defaults to None
    :type serializer: tp.Optional[BaseSerializer], optional
    :param connection: A connection for sqlite, defaults to None
    :type connection: tp.Optional[sqlite3.Connection], optional
    :param ttl: Specifies the maximum number of seconds that the response can be cached, defaults to None
    :type ttl: tp.Optional[int], optional
    """

    def __init__(
        self,
        serializer: tp.Optional[BaseSerializer] = None,
        connection: tp.Optional["sqlite3.Connection"] = None,
        ttl: tp.Optional[int] = None,
    ) -> None:
        if sqlite3 is None:  # pragma: no cover
            raise RuntimeError(
                (
                    f"The `{type(self).__name__}` was used, but the required packages were not found. "
                    "Check that you have `Hishel` installed with the `sqlite` extension as shown.\n"
                    "```pip install hishel[sqlite]```"
                )
            )
        super().__init__(serializer, ttl)

        self._connection: tp.Optional[sqlite3.Connection] = connection or None
        self._setup_lock = Lock()
        self._setup_completed: bool = False
        self._lock = Lock()

    def _setup(self) -> None:
        with self._setup_lock:
            if not self._setup_completed:
                if not self._connection:  # pragma: no cover
                    self._connection = sqlite3.connect(".hishel.sqlite", check_same_thread=False)
                self._connection.execute(
                    (
                        "CREATE TABLE IF NOT EXISTS cache(key TEXT, data BLOB, "
                        "date_created datetime DEFAULT CURRENT_TIMESTAMP)"
                    )
                )
                self._connection.commit()
                self._setup_completed = True

    def store(self, key: str, response: Response, request: Request, metadata: Metadata) -> None:
        """
        Stores the response in the cache.

        :param key: Hashed value of concatenated HTTP method and URI
        :type key: str
        :param response: An HTTP response
        :type response: httpcore.Response
        :param request: An HTTP request
        :type request: httpcore.Request
        :param metadata: Additioal information about the stored response
        :type metadata: Metadata
        """

        self._setup()
        assert self._connection

        with self._lock:
            self._connection.execute("DELETE FROM cache WHERE key = ?", [key])
            serialized_response = self._serializer.dumps(response=response, request=request, metadata=metadata)
            self._connection.execute("INSERT INTO cache(key, data) VALUES(?, ?)", [key, serialized_response])
            self._connection.commit()
        self._remove_expired_caches()

    def retreive(self, key: str) -> tp.Optional[tp.Tuple[Response, Request, Metadata]]:
        """
        Retreives the response from the cache using his key.

        :param key: Hashed value of concatenated HTTP method and URI
        :type key: str
        :return: An HTTP response and its HTTP request.
        :rtype: tp.Optional[tp.Tuple[Response, Request, Metadata]]
        """

        self._setup()
        assert self._connection

        self._remove_expired_caches()
        with self._lock:
            cursor = self._connection.execute("SELECT data FROM cache WHERE key = ?", [key])
            row = cursor.fetchone()
            if row is None:
                return None

            cached_response = row[0]
            return self._serializer.loads(cached_response)

    def close(self) -> None:  # pragma: no cover
        assert self._connection
        self._connection.close()

    def _remove_expired_caches(self) -> None:
        assert self._connection
        if self._ttl is None:
            return

        with self._lock:
            self._connection.execute(
                f"DELETE FROM cache WHERE datetime(date_created, '+{self._ttl} seconds') > datetime()"
            )
            self._connection.commit()


class RedisStorage(BaseStorage):
    """
    A simple redis storage.

    :param serializer: Serializer capable of serializing and de-serializing http responses, defaults to None
    :type serializer: tp.Optional[BaseSerializer], optional
    :param client: A client for redis, defaults to None
    :type client: tp.Optional["redis.Redis"], optional
    :param ttl: Specifies the maximum number of seconds that the response can be cached, defaults to None
    :type ttl: tp.Optional[int], optional
    """

    def __init__(
        self,
        serializer: tp.Optional[BaseSerializer] = None,
        client: tp.Optional["redis.Redis"] = None,  # type: ignore
        ttl: tp.Optional[int] = None,
    ) -> None:
        if redis is None:  # pragma: no cover
            raise RuntimeError(
                (
                    f"The `{type(self).__name__}` was used, but the required packages were not found. "
                    "Check that you have `Hishel` installed with the `redis` extension as shown.\n"
                    "```pip install hishel[redis]```"
                )
            )
        super().__init__(serializer, ttl)

        if client is None:
            self._client = redis.Redis()  # type: ignore
        else:  # pragma: no cover
            self._client = client

    def store(self, key: str, response: Response, request: Request, metadata: Metadata) -> None:
        """
        Stores the response in the cache.

        :param key: Hashed value of concatenated HTTP method and URI
        :type key: str
        :param response: An HTTP response
        :type response: httpcore.Response
        :param request: An HTTP request
        :type request: httpcore.Request
        :param metadata: Additioal information about the stored response
        :type metadata: Metadata
        """
        self._client.set(
            key,
            self._serializer.dumps(response=response, request=request, metadata=metadata),
            ex=self._ttl,
        )

    def retreive(self, key: str) -> tp.Optional[tp.Tuple[Response, Request, Metadata]]:
        """
        Retreives the response from the cache using his key.

        :param key: Hashed value of concatenated HTTP method and URI
        :type key: str
        :return: An HTTP response and its HTTP request.
        :rtype: tp.Optional[tp.Tuple[Response, Request, Metadata]]
        """

        cached_response = self._client.get(key)
        if cached_response is None:
            return None

        return self._serializer.loads(cached_response)

    def close(self) -> None:  # pragma: no cover
        self._client.close()
