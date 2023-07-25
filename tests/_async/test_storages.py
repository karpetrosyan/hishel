import pytest
from httpcore import Request, Response

from hishel import AsyncFileStorage, AsyncRedisStorage
from hishel._utils import asleep, generate_key


@pytest.mark.anyio
async def test_filestorage(use_temp_dir):
    storage = AsyncFileStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request.method, request.url, request.headers)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(key, response)

    storead_response = await storage.retreive(key)
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

    key = generate_key(request.method, request.url, request.headers)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(key, response)

    storead_response = await storage.retreive(key)
    assert storead_response is not None
    storead_response.read()
    assert isinstance(storead_response, Response)
    assert storead_response.status == 200
    assert storead_response.headers == []
    assert storead_response.content == b"test"


@pytest.mark.asyncio
async def test_filestorage_expired():
    storage = AsyncFileStorage(max_cache_age=1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(
        first_request.method, first_request.url, first_request.headers
    )
    second_key = generate_key(
        second_request.method, second_request.url, second_request.headers
    )

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(first_key, response)

    await asleep(2)
    await storage.store(second_key, response)

    assert await storage.retreive(first_key) is None


@pytest.mark.asyncio
async def test_redisstorage_expired():
    storage = AsyncRedisStorage(max_cache_age=1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(
        first_request.method, first_request.url, first_request.headers
    )
    second_key = generate_key(
        second_request.method, second_request.url, second_request.headers
    )

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(first_key, response)

    await asleep(2)
    await storage.store(second_key, response)

    assert await storage.retreive(first_key) is None
