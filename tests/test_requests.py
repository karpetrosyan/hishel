from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from inline_snapshot import snapshot
from requests import Session
from time_machine import travel

from hishel.requests import CacheAdapter


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")), tick=False)
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
        {
            "X-Hishel-From-Cache": "True",
            "X-Hishel-Created-At": '1704067200.0',
            "X-Hishel-Spec-Ignored": "False",
            "X-Hishel-Revalidated": "False",
            "X-Hishel-Stored": "False",
        }
    )


@travel(datetime(2024, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("UTC")), tick=False)
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
            "Storing response in cache ignoring specification",
            "Trying to get cached response ignoring specification",
            "Found 1 cached pairs for the request",
            "Found matching cached response for the request",
        ]
    )
    assert {k: v for k, v in response.headers.items() if k.lower().startswith("x-hishel")} == snapshot(
        {
            "X-Hishel-Spec-Ignored": "True",
            "X-Hishel-From-Cache": "True",
            "X-Hishel-Created-At": '1704067200.0',
            "X-Hishel-Revalidated": "False",
            "X-Hishel-Stored": "False",
        }
    )
