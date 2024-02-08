import datetime
import os
from pathlib import Path

import sqlite3
import boto3
import pytest
from httpcore import Request, Response
from moto import mock_s3

from hishel import FileStorage, InMemoryStorage, RedisStorage, S3Storage, SQLiteStorage
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


@pytest.fixture(scope="function")
def aws_credentials():
    """Mocked AWS Credentials for moto."""

    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="function")
def s3(aws_credentials):
    with mock_s3():
        yield boto3.client("s3", region_name="us-east-1")



def test_filestorage(use_temp_dir):
    storage = FileStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(key, response=response, request=request, metadata=dummy_metadata)

    stored_data = storage.retrieve(key)
    assert stored_data is not None
    stored_response, stored_request, metadata = stored_data
    stored_response.read()
    assert isinstance(stored_response, Response)
    assert stored_response.status == 200
    assert stored_response.headers == []
    assert stored_response.content == b"test"



def test_s3storage(use_temp_dir, s3):
    boto3.client("s3").create_bucket(Bucket="testBucket")
    storage = S3Storage(bucket_name="testBucket")

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(key, response=response, request=request, metadata=dummy_metadata)

    stored_data = storage.retrieve(key)
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

    stored_data = storage.retrieve(key)
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

    stored_data = storage.retrieve(key)
    assert stored_data is not None
    stored_response, stored_request, metadata = stored_data
    stored_response.read()
    assert isinstance(stored_response, Response)
    assert stored_response.status == 200
    assert stored_response.headers == []
    assert stored_response.content == b"test"



def test_inmemorystorage():
    storage = InMemoryStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(key, response=response, request=request, metadata=dummy_metadata)

    stored_data = storage.retrieve(key)
    assert stored_data is not None
    stored_response, stored_request, metadata = stored_data
    stored_response.read()
    assert isinstance(stored_response, Response)
    assert stored_response.status == 200
    assert stored_response.headers == []
    assert stored_response.content == b"test"



def test_filestorage_expired(use_temp_dir):
    storage = FileStorage(ttl=0.2, check_ttl_every=0.1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert storage.retrieve(first_key) is not None

    sleep(0.3)
    storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert storage.retrieve(first_key) is None



def test_s3storage_expired(use_temp_dir, s3):
    boto3.client("s3").create_bucket(Bucket="testBucket")
    storage = S3Storage(bucket_name="testBucket", ttl=1)

    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert storage.retrieve(first_key) is not None

    sleep(1)
    storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert storage.retrieve(first_key) is None



def test_filestorage_timer(use_temp_dir):
    storage = FileStorage(ttl=0.2, check_ttl_every=0.2)

    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert storage.retrieve(first_key) is not None
    sleep(0.1)
    assert storage.retrieve(first_key) is not None
    storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)
    assert storage.retrieve(second_key) is not None
    sleep(0.1)
    assert storage.retrieve(first_key) is None
    assert storage.retrieve(second_key) is not None
    sleep(0.1)
    assert storage.retrieve(second_key) is None



def test_redisstorage_expired():
    if is_redis_down():  # pragma: no cover
        pytest.fail("Redis server was not found")
    storage = RedisStorage(ttl=0.1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert storage.retrieve(first_key) is not None

    sleep(0.3)
    storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert storage.retrieve(first_key) is None



def test_sqlite_expired():
    storage = SQLiteStorage(ttl=0.1, connection=sqlite3.connect(":memory:"))
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert storage.retrieve(first_key) is not None

    sleep(0.3)
    storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert storage.retrieve(first_key) is None



def test_inmemory_expired():
    storage = InMemoryStorage(ttl=0.1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert storage.retrieve(first_key) is not None

    sleep(0.3)
    storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert storage.retrieve(first_key) is None



def test_filestorage_empty_file_exception(use_temp_dir):
    """When working with concurrency sometimes Hishel
    may leave a cache file empty. In this case this should not
    cause a `JSONDecodeError`, but treat this situation as
    no cache file was created. Issue #180"""

    storage = FileStorage()
    request = Request(b"GET", "https://example.com")
    key = generate_key(request)
    response = Response(200, headers=[], content=b"test")
    response.read()
    storage.store(key, response=response, request=request, metadata=dummy_metadata)
    stored_data = storage.retrieve(key)

    assert stored_data is not None
    filedir = Path(os.getcwd() + "/.cache/hishel/" + key)
    with open(filedir, "w+", encoding="utf-8") as file:
        file.truncate(0)
    assert os.path.getsize(filedir) == 0
    assert storage.retrieve(key) is None



def test_s3storage_timer(use_temp_dir, s3):
    boto3.client("s3").create_bucket(Bucket="testBucket")
    storage = S3Storage(bucket_name="testBucket", ttl=5, check_ttl_every=5)

    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    response.read()

    storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert storage.retrieve(first_key) is not None
    sleep(3)
    assert storage.retrieve(first_key) is not None
    storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)
    assert storage.retrieve(second_key) is not None
    sleep(2)
    assert storage.retrieve(first_key) is None
    assert storage.retrieve(second_key) is not None
    sleep(3)
    assert storage.retrieve(second_key) is None



def test_s3storage_key_error(use_temp_dir, s3):
    """Triggers `NoSuchKey` error."""

    boto3.client("s3").create_bucket(Bucket="testBucket")
    storage = S3Storage(bucket_name="testBucket", ttl=60)
    first_request = Request(b"GET", "https://example.com")
    first_key = generate_key(first_request)

    assert storage.retrieve(first_key) is None
