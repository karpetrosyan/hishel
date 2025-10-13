from typing import Any

import pytest
from inline_snapshot import snapshot
from requests import Session

from hishel.beta.requests import CacheAdapter


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
    assert {k: v for k, v in response.headers.items() if k.lower().startswith("x-hishel")} == snapshot(
        {"X-Hishel-From-Cache": "True"}
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
            "Found 0 cached pairs for the request",
            "No keygen provided, using URL as key",
            "Storing response in cache ignoring specification",
            "Trying to get cached response ignoring specification",
            "Found 1 cached pairs for the request",
            "Found matching cached response for the request",
        ]
    )
    assert {k: v for k, v in response.headers.items() if k.lower().startswith("x-hishel")} == snapshot(
        {"X-Hishel-From-Cache": "True"}
    )
