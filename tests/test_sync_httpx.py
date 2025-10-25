import gzip
from datetime import datetime
from zoneinfo import ZoneInfo

import sqlite3
import httpx
import pytest
from httpx import ByteStream, MockTransport
from inline_snapshot import snapshot
from time_machine import travel

from hishel import SyncSqliteStorage
from hishel.httpx import SyncCacheClient, SyncCacheTransport



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")), tick=False)
def test_simple_caching(caplog: pytest.LogCaptureFixture) -> None:
    client = SyncCacheClient(
        storage=SyncSqliteStorage(connection=sqlite3.connect(":memory:")),
    )

    with caplog.at_level("DEBUG", logger="hishel"):
        client.get("https://hishel.com")
        response = client.get("https://hishel.com")

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



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")), tick=False)
def test_simple_caching_ignoring_spec(caplog: pytest.LogCaptureFixture) -> None:
    client = SyncCacheClient(
        storage=SyncSqliteStorage(connection=sqlite3.connect(":memory:")),
    )

    with caplog.at_level("DEBUG", logger="hishel"):
        client.get("https://hishel.com", extensions={"hishel_spec_ignore": True})
        response = client.get("https://hishel.com", extensions={"hishel_spec_ignore": True})

    assert caplog.messages == snapshot(
        [
            "Trying to get cached response ignoring specification",
            'Found 0 cached entries for the request',
            "Storing response in cache ignoring specification",
            "Trying to get cached response ignoring specification",
            'Found 1 cached entries for the request',
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



def test_encoded_content_caching() -> None:
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

    def handler(request: httpx.Request) -> httpx.Response:
        if not mocked_responses:
            raise RuntimeError("No more mocked responses available")
        return mocked_responses.pop(0)

    storage = SyncSqliteStorage(connection=sqlite3.connect(":memory:"))

    client = SyncCacheClient(
        transport=SyncCacheTransport(next_transport=MockTransport(handler=handler), storage=storage),
        storage=storage,
    )

    # First request - should fetch from the mocked transport and store in cache
    with client.stream("get", "https://localhost", extensions={"hishel_spec_ignore": True}) as response:
        response_data = b"".join([chunk for chunk in response.iter_raw()])
        assert data == response_data
        assert response.headers.get("Content-Length") == str(len(data)) == str(len(response_data))

    # Second request - should fetch from cache
    with client.stream("get", "https://localhost", extensions={"hishel_spec_ignore": True}) as response:
        response_data = b"".join([chunk for chunk in response.iter_raw()])
        assert data == response_data
        assert response.headers.get("Content-Length") == str(len(data)) == str(len(response_data))
