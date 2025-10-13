import gzip
from typing import Any

import httpx
import pytest
from httpx import ByteStream, MockTransport
from inline_snapshot import snapshot

from hishel.beta.httpx import SyncHishelClient


def test_simple_caching(use_temp_dir: Any, caplog: pytest.LogCaptureFixture) -> None:
    client = SyncHishelClient()

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
    assert response.extensions == snapshot({"hishel_from_cache": True})


def test_simple_caching_ignoring_spec(use_temp_dir: Any, caplog: pytest.LogCaptureFixture) -> None:
    client = SyncHishelClient()

    with caplog.at_level("DEBUG", logger="hishel"):
        client.get("https://hishel.com", extensions={"hishel_spec_ignore": True})
        response = client.get("https://hishel.com", extensions={"hishel_spec_ignore": True})

    assert caplog.messages == snapshot(
        [
            "Trying to get cached response ignoring specification",
            "Found 0 cached pairs for the request",
            "No keygen provided, using URL as key",
            "Storing response in cache ignoring specification",
            "Trying to get cached response ignoring specification",
            "Found 1 cached pairs for the request",
            "Found matching cached response for the request",
        ]
    )
    assert response.extensions == snapshot({"hishel_from_cache": True})


def test_encoded_content_caching(use_temp_dir: Any) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            stream=ByteStream(gzip.compress(b"a" * 1000)),
            headers={"Content-Encoding": "gzip", "Content-Type": "text/plain", "Content-Length": "1000"},
        )

    client = SyncHishelClient(transport=MockTransport(handler=handler))

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
