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

date_header = format_date_time(mktime((datetime.now() - timedelta(hours=2)).timetuple()))


@pytest.mark.anyio
async def test_client_301():
    async with hishel.MockAsyncTransport() as transport:
        transport.add_responses([httpx.Response(301, headers=[(b"Location", b"https://example.com")])])
        async with hishel.AsyncCacheClient(transport=transport, storage=hishel.AsyncInMemoryStorage()) as client:
            await client.request(
                "GET",
                "https://www.example.com",
            )
            response = await client.request(
                "GET",
                "https://www.example.com",
            )
            assert response.extensions["from_cache"]


@pytest.mark.anyio
async def test_empty_cachefile_handling(use_temp_dir):
    async with hishel.MockAsyncTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    status_code=200,
                    headers=[
                        ("Cache-Control", "public, max-age=86400, s-maxage=86400"),
                        ("Date", date_header),
                    ],
                    text="test",
                )
                for _ in range(2)
            ]
        )

        async with hishel.AsyncCacheClient(storage=hishel.AsyncFileStorage(), transport=transport) as client:
            request = Request(b"GET", "https://example.com/")
            key = generate_key(request)
            filedir = Path(os.getcwd() + "/.cache/hishel/" + key)

            await client.get("https://example.com/")
            response = await client.get("https://example.com/")

            assert response.status_code == 200
            assert response.text == "test"
            assert response.extensions["from_cache"]

            with open(filedir, "w+", encoding="utf-8") as file:
                file.truncate(0)
            assert os.path.getsize(filedir) == 0

            response = await client.get("https://example.com/")
            assert response.status_code == 200
            assert response.text == "test"
            assert response.extensions["from_cache"] is False

            response = await client.get("https://example.com/")
            assert response.extensions["from_cache"]


@pytest.mark.anyio
async def test_post_caching():
    async with hishel.MockAsyncTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    status_code=200,
                    headers=[
                        ("Cache-Control", "public, max-age=86400, s-maxage=86400"),
                        ("Date", date_header),
                    ],
                    text=f"test-{idx}",
                )
                for idx in range(2)
            ]
        )

        async with hishel.AsyncCacheClient(
            storage=hishel.AsyncInMemoryStorage(),
            transport=transport,
            controller=hishel.Controller(cacheable_methods=["POST"]),
        ) as client:
            # Create cache file.
            response = await client.post("https://example.com", json={"test": 1})
            assert response.status_code == 200
            assert not response.extensions["from_cache"]
            assert response.text == "test-0"

            # Get from cache file.
            response = await client.post("https://example.com", json={"test": 1})
            assert response.status_code == 200
            assert response.extensions["from_cache"]
            assert response.text == "test-0"

            # Create a new cache file
            response = await client.post("https://example.com", json={"test": 2})
            assert response.status_code == 200
            assert not response.extensions["from_cache"]
            assert response.text == "test-1"

            # Take second response from cache
            response = await client.post("https://example.com", json={"test": 2})
            assert response.status_code == 200
            assert response.extensions["from_cache"]
            assert response.text == "test-1"

            # Check on first response
            response = await client.post("https://example.com", json={"test": 1})
            assert response.status_code == 200
            assert response.extensions["from_cache"]
            assert response.text == "test-0"


@pytest.mark.anyio
async def test_client_get():
    async with hishel.MockAsyncTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    status_code=200,
                    headers=[
                        ("Cache-Control", "public, max-age=86400, s-maxage=86400"),
                        ("Date", date_header),
                    ],
                    text="test text",
                )
            ]
        )

        async with hishel.AsyncCacheClient(storage=hishel.AsyncInMemoryStorage(), transport=transport) as client:
            response = await client.get("https://example.com")
            assert response.status_code == 200
            assert not response.extensions["from_cache"]
            assert response.text == "test text"

            response = await client.get("https://example.com")
            assert response.status_code == 200
            assert response.extensions["from_cache"]
            assert response.text == "test text"


@pytest.mark.anyio
async def test_client_head():
    async with hishel.MockAsyncTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    status_code=200,
                    headers=[
                        ("Cache-Control", "public, max-age=86400, s-maxage=86400"),
                        ("Date", date_header),
                    ],
                )
                for _ in range(2)
            ]
        )

        async with hishel.AsyncCacheClient(storage=hishel.AsyncInMemoryStorage(), transport=transport) as client:
            response = await client.head("https://example.com")
            assert response.status_code == 200
            assert not response.extensions["from_cache"]

            response = await client.head("https://example.com")
            assert response.status_code == 200
            assert not response.extensions["from_cache"]


@pytest.mark.anyio
async def test_force_cache():
    async with hishel.MockAsyncTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    status_code=200,
                    headers=[
                        ("Cache-Control", "no-store"),
                        ("Date", date_header),
                    ],
                )
                for _ in range(3)
            ]
        )

        async with hishel.AsyncCacheClient(
            storage=hishel.AsyncInMemoryStorage(),
            controller=hishel.Controller(cacheable_methods=['HEAD']),
            transport=transport,
        ) as client:
            response = await client.head("https://example.com")
            assert response.status_code == 200
            assert not response.extensions["from_cache"]

            # Check that "no-store" is respected
            response = await client.head("https://example.com")
            assert response.status_code == 200
            assert not response.extensions["from_cache"]

            response = await client.head("https://example.com", extensions={"force_cache": True})
            assert response.status_code == 200
            assert not response.extensions["from_cache"]

            response = await client.head("https://example.com", extensions={"force_cache": True})
            assert response.status_code == 200
            assert response.extensions["from_cache"]


@pytest.mark.anyio
async def test_cache_disabled():
    async with hishel.MockAsyncTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    status_code=200,
                    headers=[
                        ("Cache-Control", "public, max-age=86400, s-maxage=86400"),
                        ("Date", date_header),
                    ],
                )
                for _ in range(2)
            ]
        )

        async with hishel.AsyncCacheClient(storage=hishel.AsyncInMemoryStorage(), transport=transport) as client:
            response = await client.get(
                "https://www.example.com/cacheable-endpoint", extensions={"cache_disabled": True}
            )
            assert response.status_code == 200
            assert not response.extensions["from_cache"]

            response = await client.get(
                "https://www.example.com/cacheable-endpoint", extensions={"cache_disabled": True}
            )
            assert response.status_code == 200
            assert not response.extensions["from_cache"]
