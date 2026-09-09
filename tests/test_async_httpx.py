import gzip
import hashlib
from datetime import datetime
from zoneinfo import ZoneInfo

import anysqlite
import httpx
import pytest
from httpx import ByteStream, MockTransport
from inline_snapshot import snapshot
from time_machine import travel

from hishel import AsyncSqliteStorage, CacheOptions
from hishel._policies import FilterPolicy, SpecificationPolicy
from hishel.httpx import AsyncCacheClient, AsyncCacheTransport


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")), tick=False)
async def test_simple_caching(caplog: pytest.LogCaptureFixture) -> None:
    client = AsyncCacheClient(
        storage=AsyncSqliteStorage(connection=await anysqlite.connect(":memory:", check_same_thread=False)),
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
            "hishel_revalidated": False,
            "hishel_stored": False,
            "http_version": b"HTTP/1.1",
            "reason_phrase": b"OK",
        }
    )


@pytest.mark.anyio
@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")), tick=False)
async def test_simple_caching_ignoring_spec(caplog: pytest.LogCaptureFixture) -> None:
    client = AsyncCacheClient(
        storage=AsyncSqliteStorage(connection=await anysqlite.connect(":memory:", check_same_thread=False)),
        policy=FilterPolicy(),
    )

    with caplog.at_level("DEBUG", logger="hishel"):
        await client.get("https://hishel.com", extensions={"hishel_spec_ignore": True})
        response = await client.get("https://hishel.com", extensions={"hishel_spec_ignore": True})

    assert caplog.messages == snapshot(
        [
            "Trying to get cached response ignoring specification",
            "Found 0 cached entries for the request",
            "Storing response in cache ignoring specification",
            "Trying to get cached response ignoring specification",
            "Found 1 cached entries for the request",
            "Found matching cached response for the request",
        ]
    )
    assert response.extensions == snapshot(
        {
            "hishel_from_cache": True,
            "hishel_created_at": 1704067200.0,
            "hishel_revalidated": False,
            "hishel_stored": False,
            "http_version": b"HTTP/1.1",
            "reason_phrase": b"OK",
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

    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:", check_same_thread=False))

    client = AsyncCacheClient(
        transport=AsyncCacheTransport(
            next_transport=MockTransport(handler=handler), storage=storage, policy=FilterPolicy()
        ),
    )

    # First request - should fetch from the mocked transport and store in cache
    async with client.stream("get", "https://localhost", extensions={"hishel_spec_ignore": True}) as response:
        response_data = b"".join([chunk async for chunk in response.aiter_raw()])
        assert data == response_data
        assert response.headers.get("Content-Length") == str(len(data)) == str(len(response_data))
        assert response.headers.get("Content-Encoding") == "gzip"

    # Second request - should fetch from cache
    async with client.stream("get", "https://localhost", extensions={"hishel_spec_ignore": True}) as response:
        response_data = b"".join([chunk async for chunk in response.aiter_raw()])
        assert data == response_data
        assert response.headers.get("Content-Length") == str(len(data)) == str(len(response_data))
        assert response.headers.get("Content-Encoding") == "gzip"


@pytest.mark.anyio
async def test_httpx_response_extensions_are_preserved() -> None:
    network_stream = object()
    mocked_responses = [
        httpx.Response(
            200,
            content=b"ok",
            headers={"Cache-Control": "max-age=3600", "Content-Type": "text/plain"},
            extensions={"http_version": b"HTTP/2", "network_stream": network_stream, "stream_id": 1},
        )
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if not mocked_responses:
            raise RuntimeError("No more mocked responses available")
        return mocked_responses.pop(0)

    client = AsyncCacheClient(
        transport=AsyncCacheTransport(
            next_transport=MockTransport(handler=handler),
            storage=AsyncSqliteStorage(connection=await anysqlite.connect(":memory:", check_same_thread=False)),
        ),
    )

    first = await client.get("https://localhost")
    assert first.extensions["http_version"] == b"HTTP/2"
    assert "network_stream" not in first.extensions
    assert "stream_id" not in first.extensions

    second = await client.get("https://localhost")
    assert second.extensions["hishel_from_cache"] is True
    assert second.extensions["http_version"] == b"HTTP/2"
    assert "network_stream" not in second.extensions
    assert "stream_id" not in second.extensions


@pytest.mark.anyio
async def test_body_key_survives_sending_request() -> None:
    # Regression: the spec path recomputed the body-derived key after the transport
    # had drained the request stream, so entries were stored under sha256(b"").
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"Cache-Control": "max-age=3600"}, content=b"ok")

    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:", check_same_thread=False))
    policy = SpecificationPolicy(cache_options=CacheOptions(supported_methods=["GET", "HEAD", "POST"]))
    policy.use_body_key = True
    client = AsyncCacheClient(
        transport=AsyncCacheTransport(next_transport=MockTransport(handler=handler), storage=storage, policy=policy),
    )

    response = await client.post("https://localhost", content=b"hello")
    assert response.extensions["hishel_stored"] is True

    assert len(await storage.get_entries(hashlib.sha256(b"hello").hexdigest())) == 1
    assert len(await storage.get_entries(hashlib.sha256(b"").hexdigest())) == 0


@pytest.mark.anyio
async def test_httpx_request_extensions_are_preserved() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(
            200,
            content=b"ok",
            headers={"Cache-Control": "max-age=3600", "Content-Type": "text/plain"},
        )

    client = AsyncCacheClient(
        timeout=0.5,
        transport=AsyncCacheTransport(
            next_transport=MockTransport(handler=handler),
            storage=AsyncSqliteStorage(connection=await anysqlite.connect(":memory:", check_same_thread=False)),
        ),
    )

    await client.get("https://localhost", extensions={"sni_hostname": "custom.example.com"})

    assert len(captured_requests) == 1
    assert captured_requests[0].extensions["timeout"]["connect"] == 0.5
    assert captured_requests[0].extensions["sni_hostname"] == "custom.example.com"
