import pytest
from httpcore import Request, Response

from hishel import AsyncFileStorage, AsyncRedisStorage
from hishel._utils import asleep, generate_key


@pytest.mark.anyio
async def test_filestorage(use_temp_dir):
    storage = AsyncFileStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(key, response=response, request=request)

    storead_response, _ = await storage.retreive(key)
    assert storead_response is not None
    storead_response.read()
    assert isinstance(storead_response, Response)
    assert storead_response.status == 200
    assert storead_response.headers == []
    assert storead_response.content == b"test"


@pytest.mark.asyncio
async def test_redisstorage():
    storage = AsyncRedisStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(key, response=response, request=request)

    storead_response, _ = await storage.retreive(key)
    assert storead_response is not None
    storead_response.read()
    assert isinstance(storead_response, Response)
    assert storead_response.status == 200
    assert storead_response.headers == []
    assert storead_response.content == b"test"


@pytest.mark.asyncio
async def test_filestorage_expired():
    storage = AsyncFileStorage(ttl=1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(first_key, response=response, request=first_request)

    await asleep(2)
    await storage.store(second_key, response=response, request=second_request)

    assert await storage.retreive(first_key) is None


@pytest.mark.asyncio
async def test_redisstorage_expired():
    storage = AsyncRedisStorage(ttl=1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(first_key, response=response, request=first_request)

    await asleep(2)
    await storage.store(second_key, response=response, request=second_request)

    assert await storage.retreive(first_key) is None
