import pytest
from httpcore import Request, Response

from hishel import FileStorage
from hishel._utils import generate_key



def test_filestorage(use_temp_dir):

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

    storead_response = storage.retreive(key)
    assert storead_response is not None
    storead_response.read()
    assert isinstance(storead_response, Response)
    assert storead_response.status == 200
    assert storead_response.headers == []
    assert storead_response.content == b'test'


def test_filestorage_delete(use_temp_dir):

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

    stored_response = storage.retreive(key)
    assert stored_response

    storage.delete(key)
    assert not storage.retreive(key)
