from httpcore import Request, Response

from hishel import FileStorage
from hishel._utils import generate_key


def test_storage(use_temp_dir):

    storage = FileStorage()

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

    storage.store(key, response)

    response = storage.retreive(key)
    response.read()
    assert isinstance(response, Response)
    assert response.status == 200
    assert response.headers == []
    assert response.content == b'test'


def test_delete(use_temp_dir):

    storage = FileStorage()

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

    storage.store(key, response)

    response = storage.retreive(key)
    assert response

    storage.delete(key)
    assert not storage.retreive(key)
