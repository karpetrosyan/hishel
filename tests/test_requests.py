import sqlite3
from io import BytesIO
from typing import Any

import pytest
from inline_snapshot import snapshot
from requests import PreparedRequest, Response, Session
from requests.adapters import HTTPAdapter
from urllib3 import HTTPResponse

from hishel import SyncSqliteStorage
from hishel._utils import filter_mapping
from hishel.requests import CacheAdapter


@pytest.mark.parametrize(
    "location, expected_url",
    [
        (None, "http://example.com/dir/start"),
        ("/target", "http://example.com/target"),
        ("target", "http://example.com/dir/target"),
        ("http://example.com/target", "http://example.com/target"),
    ],
)
def test_response_url(monkeypatch: pytest.MonkeyPatch, location: str | None, expected_url: str) -> None:
    start_url = "http://example.com/dir/start"
    sent_urls = []

    def send(adapter: HTTPAdapter, request: PreparedRequest, **kwargs: Any) -> Response:
        sent_urls.append(request.url)
        headers = {"Cache-Control": "public, max-age=3600"}
        is_redirect = location is not None and request.url == start_url
        if is_redirect:
            assert location is not None
            headers["Location"] = location
        raw = HTTPResponse(
            body=BytesIO(b"" if is_redirect else b"content"),
            status=301 if is_redirect else 200,
            headers=headers,
            preload_content=False,
        )
        return adapter.build_response(request, raw)

    monkeypatch.setattr(HTTPAdapter, "send", send)
    storage = SyncSqliteStorage(connection=sqlite3.connect(":memory:", check_same_thread=False))
    with Session() as session:
        session.mount("http://", CacheAdapter(storage=storage))
        for from_cache in (False, True):
            response = session.get(start_url)
            assert response.status_code == 200
            assert response.content == b"content"
            assert response.url == expected_url
            assert response.request.url == expected_url
            assert [item.url for item in response.history] == ([start_url] if location else [])
            for item in [*response.history, response]:
                assert item.headers["X-Hishel-From-Cache"] == str(from_cache)

    assert sent_urls == ([start_url, expected_url] if location else [start_url])


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
