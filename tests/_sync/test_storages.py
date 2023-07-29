import pytest
from httpcore import Request, Response

from hishel import FileStorage, RedisStorage
from hishel._utils import sleep, generate_key



def test_filestorage(use_temp_dir):
    storage = FileStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(key, response=response, request=request)

    stored_data = storage.retreive(key)
    assert stored_data is not None
    stored_response, stored_request = stored_data
    stored_response.read()
    assert isinstance(stored_response, Response)
    assert stored_response.status == 200
    assert stored_response.headers == []
    assert stored_response.content == b"test"



def test_redisstorage():
    storage = RedisStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(key, response=response, request=request)

    stored_data = storage.retreive(key)
    assert stored_data is not None
    stored_response, stored_request = stored_data
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

    storage.store(first_key, response=response, request=first_request)

    sleep(2)
    storage.store(second_key, response=response, request=second_request)

    assert storage.retreive(first_key) is None



def test_redisstorage_expired():
    storage = RedisStorage(ttl=1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(first_key, response=response, request=first_request)

    sleep(2)
    storage.store(second_key, response=response, request=second_request)

    assert storage.retreive(first_key) is None
