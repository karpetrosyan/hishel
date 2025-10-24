import gzip
from datetime import datetime
from zoneinfo import ZoneInfo

import anysqlite
import httpx
import pytest
from httpx import ByteStream, MockTransport
from inline_snapshot import snapshot
from time_machine import travel

from hishel import AsyncSqliteStorage
from hishel.httpx import AsyncCacheClient, AsyncCacheTransport


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")), tick=False)
async def test_simple_caching(caplog: pytest.LogCaptureFixture) -> None:
    client = AsyncCacheClient(
        storage=AsyncSqliteStorage(connection=await anysqlite.connect(":memory:")),
    )

    with caplog.at_level("DEBUG", logger="hishel"):
        await client.get("https://hishel.com")
        response = await client.get("https://hishel.com")

    assert caplog.messages == snapshot(
        [
            "Handling state: IdleClient",
            "Handling state: CacheMiss",
            "Storing response in cache",
            "Handling state: StoreAndUse",
            "Handling state: IdleClient",
            "Handling state: FromCache",
        ]
    )
    assert response.extensions == snapshot(
        {
            "hishel_from_cache": True,
            "hishel_created_at": 1704067200.0,
            "hishel_spec_ignored": False,
            "hishel_revalidated": False,
            "hishel_stored": False,
        }
    )


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")), tick=False)
async def test_simple_caching_ignoring_spec(caplog: pytest.LogCaptureFixture) -> None:
    client = AsyncCacheClient(
        storage=AsyncSqliteStorage(connection=await anysqlite.connect(":memory:")),
    )

    with caplog.at_level("DEBUG", logger="hishel"):
        await client.get("https://hishel.com", extensions={"hishel_spec_ignore": True})
        response = await client.get("https://hishel.com", extensions={"hishel_spec_ignore": True})

    assert caplog.messages == snapshot(
        [
            "Trying to get cached response ignoring specification",
            "Found 0 cached pairs for the request",
            "Storing response in cache ignoring specification",
            "Trying to get cached response ignoring specification",
            "Found 1 cached pairs for the request",
            "Found matching cached response for the request",
        ]
    )
    assert response.extensions == snapshot(
        {
            "hishel_spec_ignored": True,
            "hishel_from_cache": True,
            "hishel_created_at": 1704067200.0,
            "hishel_revalidated": False,
            "hishel_stored": False,
        }
    )


@pytest.mark.anyio
async def test_encoded_content_caching() -> None:
    data = gzip.compress(b"a" * 1000)
    compressed_data = ByteStream(data)
    mocked_responses = [
        httpx.Response(
            200,
            stream=compressed_data,
            headers={
                "Content-Encoding": "gzip",
                "Content-Type": "text/plain",
                "Content-Length": str(len(data)),
            },
        )
    ]

    async def handler(request: httpx.Request) -> httpx.Response:
        if not mocked_responses:
            raise RuntimeError("No more mocked responses available")
        return mocked_responses.pop(0)

    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))

    client = AsyncCacheClient(
        transport=AsyncCacheTransport(next_transport=MockTransport(handler=handler), storage=storage),
        storage=storage,
    )

    # First request - should fetch from the mocked transport and store in cache
    async with client.stream("get", "https://localhost", extensions={"hishel_spec_ignore": True}) as response:
        response_data = b"".join([chunk async for chunk in response.aiter_raw()])
        assert data == response_data
        assert response.headers.get("Content-Length") == str(len(data)) == str(len(response_data))

    # Second request - should fetch from cache
    async with client.stream("get", "https://localhost", extensions={"hishel_spec_ignore": True}) as response:
        response_data = b"".join([chunk async for chunk in response.aiter_raw()])
        assert data == response_data
        assert response.headers.get("Content-Length") == str(len(data)) == str(len(response_data))
