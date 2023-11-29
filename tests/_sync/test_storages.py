import datetime

import sqlite3
import pytest
from httpcore import Request, Response

from hishel import FileStorage, RedisStorage, SQLiteStorage
from hishel._serializers import Metadata
from hishel._utils import sleep, generate_key

dummy_metadata = Metadata(cache_key="test", number_of_uses=0, created_at=datetime.datetime.now(datetime.timezone.utc))


def is_redis_down() -> bool:
    import redis

    connection = redis.Redis()
    try:
        return not connection.ping()
    except BaseException:  # pragma: no cover
        return True



def test_filestorage(use_temp_dir):
    storage = FileStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(key, response=response, request=request, metadata=dummy_metadata)

    stored_data = storage.retreive(key)
    assert stored_data is not None
    stored_response, stored_request, metadata = stored_data
    stored_response.read()
    assert isinstance(stored_response, Response)
    assert stored_response.status == 200
    assert stored_response.headers == []
    assert stored_response.content == b"test"



def test_redisstorage():
    if is_redis_down():  # pragma: no cover
        pytest.fail("Redis server was not found")
    storage = RedisStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(key, response=response, request=request, metadata=dummy_metadata)

    stored_data = storage.retreive(key)
    assert stored_data is not None
    stored_response, stored_request, metadata = stored_data
    stored_response.read()
    assert isinstance(stored_response, Response)
    assert stored_response.status == 200
    assert stored_response.headers == []
    assert stored_response.content == b"test"



def test_sqlitestorage():
    storage = SQLiteStorage(connection=sqlite3.connect(":memory:"))

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(key, response=response, request=request, metadata=dummy_metadata)

    stored_data = storage.retreive(key)
    assert stored_data is not None
    stored_response, stored_request, metadata = stored_data
    stored_response.read()
    assert isinstance(stored_response, Response)
    assert stored_response.status == 200
    assert stored_response.headers == []
    assert stored_response.content == b"test"



def test_filestorage_expired():
    storage = FileStorage(ttl=1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert storage.retreive(first_key) is not None

    sleep(2)
    storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert storage.retreive(first_key) is None



def test_redisstorage_expired():
    if is_redis_down():  # pragma: no cover
        pytest.fail("Redis server was not found")
    storage = RedisStorage(ttl=1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert storage.retreive(first_key) is not None

    sleep(2)
    storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert storage.retreive(first_key) is None



def test_sqlite_expired():
    storage = SQLiteStorage(ttl=1, connection=sqlite3.connect(":memory:"))
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert storage.retreive(first_key) is not None

    sleep(2)
    storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert storage.retreive(first_key) is None
