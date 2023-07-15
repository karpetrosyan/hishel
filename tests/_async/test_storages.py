from httpcore import Request, Response

from hishel import AsyncFileStorage
from hishel._utils import generate_key
import pytest

@pytest.mark.anyio
async def test_filestorage(use_temp_dir):

    storage = AsyncFileStorage()

    request = Request(
        b"GET",
        "https://example.com"
    )

    key = generate_key(
        request.method,
        request.url,
        request.headers
    )

    response = Response(
        200,
        headers=[],
        content=b'test'
    )

    await storage.store(key, response)

    response = await storage.retreive(key)
    response.read()
    assert isinstance(response, Response)
    assert response.status == 200
    assert response.headers == []
    assert response.content == b'test'

@pytest.mark.anyio
async def test_filestorage_delete(use_temp_dir):

    storage = AsyncFileStorage()

    request = Request(
        b"GET",
        "https://example.com"
    )

    key = generate_key(
        request.method,
        request.url,
        request.headers
    )

    response = Response(
        200,
        headers=[],
        content=b'test'
    )

    await storage.store(key, response)

    response = await storage.retreive(key)
    assert response

    await storage.delete(key)
    assert not await storage.retreive(key)
