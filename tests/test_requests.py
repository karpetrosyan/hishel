from typing import Any

import pytest
from inline_snapshot import snapshot
from requests import Session

from hishel._utils import filter_mapping
from hishel.requests import CacheAdapter


def test_simple_caching(use_temp_dir: Any, caplog: pytest.LogCaptureFixture) -> None:
    session = Session()
    adapter = CacheAdapter()

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    with caplog.at_level("DEBUG", logger="hishel"):
        session.get("https://hishel.com")
        response = session.get("https://hishel.com")

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
    assert filter_mapping(
        {k: v for k, v in response.headers.items() if k.lower().startswith("x-hishel")}, ["x-hishel-created-at"]
    ) == snapshot(
        {
            "X-Hishel-From-Cache": "True",
            "X-Hishel-Spec-Ignored": "False",
            "X-Hishel-Revalidated": "False",
            "X-Hishel-Stored": "False",
        }
    )


def test_simple_caching_ignoring_spec(use_temp_dir: Any, caplog: pytest.LogCaptureFixture) -> None:
    session = Session()
    adapter = CacheAdapter()

    session.mount("http://", adapter)
    session.mount("https://", adapter)

    with caplog.at_level("DEBUG", logger="hishel"):
        session.get("https://hishel.com", headers={"x-hishel-spec-ignore": "True"})
        response = session.get("https://hishel.com", headers={"x-hishel-spec-ignore": "True"})

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
    assert filter_mapping(
        {k: v for k, v in response.headers.items() if k.lower().startswith("x-hishel")}, ["x-hishel-created-at"]
    ) == snapshot(
        {
            "X-Hishel-Spec-Ignored": "True",
            "X-Hishel-From-Cache": "True",
            "X-Hishel-Revalidated": "False",
            "X-Hishel-Stored": "False",
        }
    )


def test_encoded_content_caching(use_temp_dir: Any) -> None:
    """Test that gzip-encoded content is properly cached and retrieved."""
    session = Session()
    adapter = CacheAdapter()
    session.mount("https://", adapter)

    # First request - should fetch from mock and store in cache
    response1 = session.get("https://httpbingo.org/gzip", headers={"x-hishel-spec-ignore": "True"})
    # just check that we can read the content and decode it properly
    response1.json()
    assert response1.headers.get("Content-Encoding") == "gzip"

    # Second request - should fetch from cache (no additional mock call)
    response2 = session.get("https://httpbingo.org/gzip", headers={"x-hishel-spec-ignore": "True"})
    # just check that we can read the content and decode it properly
    response2.json()
    assert response2.headers.get("Content-Encoding") == "gzip"
