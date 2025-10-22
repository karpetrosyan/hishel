import gzip
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx
import pytest
import zstandard as zstd
from httpx import ByteStream, MockTransport
from inline_snapshot import snapshot
from time_machine import travel

from hishel.httpx import SyncCacheClient, httpx_to_internal, internal_to_httpx



@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")), tick=False)
def test_simple_caching(use_temp_dir: Any, caplog: pytest.LogCaptureFixture) -> None:
    client = SyncCacheClient()

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
def test_simple_caching_ignoring_spec(use_temp_dir: Any, caplog: pytest.LogCaptureFixture) -> None:
    client = SyncCacheClient()

    with caplog.at_level("DEBUG", logger="hishel"):
        client.get("https://hishel.com", extensions={"hishel_spec_ignore": True})
        response = client.get("https://hishel.com", extensions={"hishel_spec_ignore": True})

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



def test_encoded_content_caching(use_temp_dir: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=ByteStream(gzip.compress(b"a" * 1000)),
            headers={"Content-Encoding": "gzip", "Content-Type": "text/plain", "Content-Length": "1000"},
        )

    client = SyncCacheClient(transport=MockTransport(handler=handler))

    response = client.get("https://localhost")

    assert response.content == b"a" * 1000
    assert response.headers.get("Content-Encoding") == "gzip"
    assert response.headers.get("Content-Length") == "1000"

    with client.stream("GET", "https://localhost") as second_response:
        assert response.headers.get("Content-Encoding") == "gzip"
        assert response.headers.get("Content-Length") == "1000"
        content = b""
        for chunk in second_response.iter_raw():
            content += chunk
        assert gzip.decompress(content) == response.content



def test_compressed_data() -> None:
    compressed_content = zstd.ZstdCompressor().compress(b"test content")

    response = httpx.Response(
        200,
        stream=ByteStream(compressed_content),
        headers={
            "Content-Encoding": "zstd",
            "Content-Type": "text/plain",
            "Content-Length": str(len(compressed_content)),
        },
    )

    internal_response = httpx_to_internal(response)

    httpx_response = internal_to_httpx(internal_response)

    assert httpx_response.status_code == response.status_code
    assert httpx_response.headers == response.headers
    assert httpx_response.read() == b"test content"



def test_consumed_stream_conversion() -> None:
    response = httpx.Response(
        200,
        stream=ByteStream(b"test"),
        headers={
            "Content-Type": "text/plain",
        },
    )
    response.read()  # Consume the stream

    with pytest.raises(ValueError, match="Cannot get the raw data of a consumed httpx.Response."):
        httpx_to_internal(response)
