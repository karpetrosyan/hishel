import os
from datetime import datetime, timedelta
from pathlib import Path
from time import mktime
from wsgiref.handlers import format_date_time

import httpx
import pytest
from httpcore import Request

import hishel
from hishel._utils import generate_key



def test_client_301():
    with hishel.MockTransport() as transport:
        transport.add_responses([httpx.Response(301, headers=[(b"Location", b"https://example.com")])])
        with hishel.CacheClient(transport=transport, storage=hishel.InMemoryStorage()) as client:
            client.request(
                "GET",
                "https://www.example.com",
            )
            response = client.request(
                "GET",
                "https://www.example.com",
            )
            assert response.extensions["from_cache"]



def test_empty_cachefile_handling(use_temp_dir):
    with hishel.MockTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    status_code=200,
                    headers=[
                        ("Cache-Control", "public, max-age=86400, s-maxage=86400"),
                        ("Date", format_date_time(mktime((datetime.now() - timedelta(hours=2)).timetuple()))),
                    ],
                    text="test",
                )
                for _ in range(2)
            ]
        )

        with hishel.CacheClient(storage=hishel.FileStorage(), transport=transport) as client:
            request = Request(b"GET", "https://example.com/")
            key = generate_key(request)
            filedir = Path(os.getcwd() + "/.cache/hishel/" + key)

            client.get("https://example.com/")
            response = client.get("https://example.com/")

            assert response.status_code == 200
            assert response.text == "test"
            assert response.extensions["from_cache"]

            with open(filedir, "w+", encoding="utf-8") as file:
                file.truncate(0)
            assert os.path.getsize(filedir) == 0

            response = client.get("https://example.com/")
            assert response.status_code == 200
            assert response.text == "test"
            assert response.extensions["from_cache"] is False

            response = client.get("https://example.com/")
            assert response.extensions["from_cache"]



def test_post_caching():
    with hishel.MockTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    status_code=200,
                    headers=[
                        ("Cache-Control", "public, max-age=86400, s-maxage=86400"),
                        ("Date", format_date_time(mktime((datetime.now() - timedelta(hours=2)).timetuple()))),
                    ],
                    text=f"test-{idx}",
                )
                for idx in range(2)
            ]
        )

        with hishel.CacheClient(
            storage=hishel.InMemoryStorage(),
            transport=transport,
            controller=hishel.Controller(cacheable_methods=["POST"]),
        ) as client:
            # Create cache file.
            response = client.post("https://example.com", json={"test": 1})
            assert response.status_code == 200
            assert not response.extensions["from_cache"]
            assert response.text == "test-0"

            # Get from cache file.
            response = client.post("https://example.com", json={"test": 1})
            assert response.status_code == 200
            assert response.extensions["from_cache"]
            assert response.text == "test-0"

            # Create a new cache file
            response = client.post("https://example.com", json={"test": 2})
            assert response.status_code == 200
            assert not response.extensions["from_cache"]
            assert response.text == "test-1"

            # Take second response from cache
            response = client.post("https://example.com", json={"test": 2})
            assert response.status_code == 200
            assert response.extensions["from_cache"]
            assert response.text == "test-1"

            # Check on first response
            response = client.post("https://example.com", json={"test": 1})
            assert response.status_code == 200
            assert response.extensions["from_cache"]
            assert response.text == "test-0"



def test_client_get():
    with hishel.MockTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    status_code=200,
                    headers=[
                        ("Cache-Control", "public, max-age=86400, s-maxage=86400"),
                        ("Date", format_date_time(mktime((datetime.now() - timedelta(hours=2)).timetuple()))),
                    ],
                    text="test text",
                )
            ]
        )

        with hishel.CacheClient(storage=hishel.InMemoryStorage(), transport=transport) as client:
            response = client.get("https://example.com")
            assert response.status_code == 200
            assert not response.extensions["from_cache"]
            assert response.text == "test text"

            response = client.get("https://example.com")
            assert response.status_code == 200
            assert response.extensions["from_cache"]
            assert response.text == "test text"



def test_client_head():
    with hishel.MockTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    status_code=200,
                    headers=[
                        ("Cache-Control", "public, max-age=86400, s-maxage=86400"),
                        ("Date", format_date_time(mktime((datetime.now() - timedelta(hours=2)).timetuple()))),
                    ],
                )
                for _ in range(2)
            ]
        )

        with hishel.CacheClient(storage=hishel.InMemoryStorage(), transport=transport) as client:
            response = client.head("https://example.com")
            assert response.status_code == 200
            assert not response.extensions["from_cache"]

            response = client.head("https://example.com")
            assert response.status_code == 200
            assert not response.extensions["from_cache"]



def test_force_cache():
    with hishel.MockTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    status_code=200,
                    headers=[
                        ("Cache-Control", "no-store"),
                        ("Date", format_date_time(mktime((datetime.now() - timedelta(hours=2)).timetuple()))),
                    ],
                )
                for _ in range(3)
            ]
        )

        with hishel.CacheClient(storage=hishel.InMemoryStorage(), transport=transport) as client:
            response = client.head("https://example.com")
            assert response.status_code == 200
            assert not response.extensions["from_cache"]

            # Check that "no-store" is respected
            response = client.head("https://example.com")
            assert response.status_code == 200
            assert not response.extensions["from_cache"]

            response = client.head("https://example.com", extensions={"force_cache": True})
            assert response.status_code == 200
            assert not response.extensions["from_cache"]

            response = client.head("https://example.com", extensions={"force_cache": True})
            assert response.status_code == 200
            assert response.extensions["from_cache"]



def test_cache_disabled():
    with hishel.MockTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    status_code=200,
                    headers=[
                        ("Cache-Control", "public, max-age=86400, s-maxage=86400"),
                        ("Date", format_date_time(mktime((datetime.now() - timedelta(hours=2)).timetuple()))),
                    ],
                )
                for _ in range(2)
            ]
        )

        with hishel.CacheClient(storage=hishel.InMemoryStorage(), transport=transport) as client:
            response = client.get(
                "https://www.example.com/cacheable-endpoint", extensions={"cache_disabled": True}
            )
            assert response.status_code == 200
            assert not response.extensions["from_cache"]

            response = client.get(
                "https://www.example.com/cacheable-endpoint", extensions={"cache_disabled": True}
            )
            assert response.status_code == 200
            assert not response.extensions["from_cache"]
