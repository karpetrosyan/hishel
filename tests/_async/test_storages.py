import datetime

import anysqlite
import pytest
from httpcore import Request, Response

from hishel import AsyncFileStorage, AsyncRedisStorage, AsyncSQLiteStorage
from hishel._serializers import Metadata
from hishel._utils import asleep, generate_key

dummy_metadata = Metadata(cache_key="test", number_of_uses=0, created_at=datetime.datetime.utcnow())


def is_redis_down() -> bool:
    import redis

    connection = redis.Redis()
    try:
        return not connection.ping()
    except BaseException:  # pragma: no cover
        return True


@pytest.mark.anyio
async def test_filestorage(use_temp_dir):
    storage = AsyncFileStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(key, response=response, request=request, metadata=dummy_metadata)

    stored_data = await storage.retreive(key)
    assert stored_data is not None
    stored_response, stored_request, metadata = stored_data
    stored_response.read()
    assert isinstance(stored_response, Response)
    assert stored_response.status == 200
    assert stored_response.headers == []
    assert stored_response.content == b"test"


@pytest.mark.asyncio
async def test_redisstorage():
    if is_redis_down():  # pragma: no cover
        pytest.fail("Redis server was not found")
    storage = AsyncRedisStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(key, response=response, request=request, metadata=dummy_metadata)

    stored_data = await storage.retreive(key)
    assert stored_data is not None
    stored_response, stored_request, metadata = stored_data
    stored_response.read()
    assert isinstance(stored_response, Response)
    assert stored_response.status == 200
    assert stored_response.headers == []
    assert stored_response.content == b"test"


@pytest.mark.anyio
async def test_sqlitestorage():
    storage = AsyncSQLiteStorage(connection=await anysqlite.connect(":memory:"))

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(key, response=response, request=request, metadata=dummy_metadata)

    stored_data = await storage.retreive(key)
    assert stored_data is not None
    stored_response, stored_request, metadata = stored_data
    stored_response.read()
    assert isinstance(stored_response, Response)
    assert stored_response.status == 200
    assert stored_response.headers == []
    assert stored_response.content == b"test"


@pytest.mark.asyncio
async def test_filestorage_expired():
    storage = AsyncFileStorage(ttl=1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)

    await asleep(2)
    await storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert await storage.retreive(first_key) is None


@pytest.mark.asyncio
async def test_redisstorage_expired():
    if is_redis_down():  # pragma: no cover
        pytest.fail("Redis server was not found")
    storage = AsyncRedisStorage(ttl=1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)

    await asleep(2)
    await storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert await storage.retreive(first_key) is None


@pytest.mark.asyncio
async def test_sqlite_expired():
    storage = AsyncSQLiteStorage(ttl=1, connection=await anysqlite.connect(":memory:"))
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)

    await asleep(2)
    await storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert await storage.retreive(first_key) is None
