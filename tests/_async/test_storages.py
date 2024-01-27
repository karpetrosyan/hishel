import datetime
import os

import anysqlite
import boto3
import pytest
from httpcore import Request, Response
from moto import mock_s3

from hishel import AsyncFileStorage, AsyncInMemoryStorage, AsyncRedisStorage, AsyncS3Storage, AsyncSQLiteStorage
from hishel._serializers import Metadata
from hishel._utils import asleep, generate_key

dummy_metadata = Metadata(cache_key="test", number_of_uses=0, created_at=datetime.datetime.now(datetime.timezone.utc))


async def is_redis_down() -> bool:
    import redis.asyncio as redis

    connection = redis.Redis()
    try:
        return not await connection.ping()
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


@pytest.mark.anyio
async def test_filestorage(use_temp_dir):
    storage = AsyncFileStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(key, response=response, request=request, metadata=dummy_metadata)

    stored_data = await storage.retrieve(key)
    assert stored_data is not None
    stored_response, stored_request, metadata = stored_data
    stored_response.read()
    assert isinstance(stored_response, Response)
    assert stored_response.status == 200
    assert stored_response.headers == []
    assert stored_response.content == b"test"


@pytest.mark.anyio
async def test_s3storage(use_temp_dir, s3):
    boto3.client("s3").create_bucket(Bucket="testBucket")
    storage = AsyncS3Storage(bucket_name="testBucket")

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(key, response=response, request=request, metadata=dummy_metadata)

    stored_data = await storage.retrieve(key)
    assert stored_data is not None
    stored_response, stored_request, metadata = stored_data
    stored_response.read()
    assert isinstance(stored_response, Response)
    assert stored_response.status == 200
    assert stored_response.headers == []
    assert stored_response.content == b"test"


@pytest.mark.asyncio
async def test_redisstorage():
    if await is_redis_down():  # pragma: no cover
        pytest.fail("Redis server was not found")
    storage = AsyncRedisStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(key, response=response, request=request, metadata=dummy_metadata)

    stored_data = await storage.retrieve(key)
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

    stored_data = await storage.retrieve(key)
    assert stored_data is not None
    stored_response, stored_request, metadata = stored_data
    stored_response.read()
    assert isinstance(stored_response, Response)
    assert stored_response.status == 200
    assert stored_response.headers == []
    assert stored_response.content == b"test"


@pytest.mark.anyio
async def test_inmemorystorage():
    storage = AsyncInMemoryStorage()

    request = Request(b"GET", "https://example.com")

    key = generate_key(request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(key, response=response, request=request, metadata=dummy_metadata)

    stored_data = await storage.retrieve(key)
    assert stored_data is not None
    stored_response, stored_request, metadata = stored_data
    stored_response.read()
    assert isinstance(stored_response, Response)
    assert stored_response.status == 200
    assert stored_response.headers == []
    assert stored_response.content == b"test"


@pytest.mark.asyncio
async def test_filestorage_expired(use_temp_dir):
    storage = AsyncFileStorage(ttl=0.2, check_ttl_every=0.1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert await storage.retrieve(first_key) is not None

    await asleep(0.3)
    await storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert await storage.retrieve(first_key) is None


@pytest.mark.asyncio
async def test_s3storage_expired(use_temp_dir, s3):
    boto3.client("s3").create_bucket(Bucket="testBucket")
    storage = AsyncS3Storage(bucket_name="testBucket", ttl=1)

    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert await storage.retrieve(first_key) is not None

    await asleep(1)
    await storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert await storage.retrieve(first_key) is None


@pytest.mark.asyncio
async def test_filestorage_timer(use_temp_dir):
    storage = AsyncFileStorage(ttl=0.2, check_ttl_every=0.2)

    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert await storage.retrieve(first_key) is not None
    await asleep(0.1)
    assert await storage.retrieve(first_key) is not None
    await storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)
    assert await storage.retrieve(second_key) is not None
    await asleep(0.1)
    assert await storage.retrieve(first_key) is None
    assert await storage.retrieve(second_key) is not None
    await asleep(0.1)
    assert await storage.retrieve(second_key) is None


@pytest.mark.asyncio
async def test_redisstorage_expired():
    if await is_redis_down():  # pragma: no cover
        pytest.fail("Redis server was not found")
    storage = AsyncRedisStorage(ttl=0.1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert await storage.retrieve(first_key) is not None

    await asleep(0.3)
    await storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert await storage.retrieve(first_key) is None


@pytest.mark.asyncio
async def test_sqlite_expired():
    storage = AsyncSQLiteStorage(ttl=0.1, connection=await anysqlite.connect(":memory:"))
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert await storage.retrieve(first_key) is not None

    await asleep(0.3)
    await storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert await storage.retrieve(first_key) is None


@pytest.mark.asyncio
async def test_inmemory_expired():
    storage = AsyncInMemoryStorage(ttl=0.1)
    first_request = Request(b"GET", "https://example.com")
    second_request = Request(b"GET", "https://anotherexample.com")

    first_key = generate_key(first_request)
    second_key = generate_key(second_request)

    response = Response(200, headers=[], content=b"test")
    await response.aread()

    await storage.store(first_key, response=response, request=first_request, metadata=dummy_metadata)
    assert await storage.retrieve(first_key) is not None

    await asleep(0.3)
    await storage.store(second_key, response=response, request=second_request, metadata=dummy_metadata)

    assert await storage.retrieve(first_key) is None
