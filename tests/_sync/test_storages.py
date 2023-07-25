import pytest
from httpcore import Request, Response

from hishel import FileStorage, RedisStorage
from hishel._utils import sleep, generate_key



def test_filestorage(use_temp_dir):
    storage = FileStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request.method, request.url, request.headers)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(key, response)

    storead_response = storage.retreive(key)
    assert storead_response is not None
    storead_response.read()
    assert isinstance(storead_response, Response)
    assert storead_response.status == 200
    assert storead_response.headers == []
    assert storead_response.content == b"test"



def test_redisstorage():
    storage = RedisStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request.method, request.url, request.headers)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(key, response)

    storead_response = storage.retreive(key)
    assert storead_response is not None
    storead_response.read()
    assert isinstance(storead_response, Response)
    assert storead_response.status == 200
    assert storead_response.headers == []
    assert storead_response.content == b"test"



def test_filestorage_expired():
    storage = FileStorage(max_cache_age=1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(
        first_request.method, first_request.url, first_request.headers
    )
    second_key = generate_key(
        second_request.method, second_request.url, second_request.headers
    )

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(first_key, response)

    sleep(2)
    storage.store(second_key, response)

    assert storage.retreive(first_key) is None



def test_redisstorage_expired():
    storage = RedisStorage(max_cache_age=1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(
        first_request.method, first_request.url, first_request.headers
    )
    second_key = generate_key(
        second_request.method, second_request.url, second_request.headers
    )

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(first_key, response)

    sleep(2)
    storage.store(second_key, response)

    assert storage.retreive(first_key) is None
