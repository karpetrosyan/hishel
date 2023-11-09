import httpx
import pytest

import hishel


@pytest.mark.anyio
async def test_client_301():
    async with hishel.MockAsyncTransport() as transport:
        transport.add_responses(
            [httpx.Response(301, headers=[(b"Location", b"https://example.com")])]
        )
        async with hishel.AsyncCacheClient(transport=transport) as client:
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
async def test_disable_cache():
    async with hishel.MockAsyncTransport() as transport:
        transport.add_responses(
            [httpx.Response(301, headers=[(b"Location", b"https://example.com")])]
        )
        async with hishel.AsyncCacheClient(transport=transport) as client:
            await client.request(
                "GET",
                "https://www.example.com",
            )
            # Disable cache and confirm that the response is not cached
            with client.cache_disabled():
                response = await client.request(
                    "GET",
                    "https://www.example.com",
                )
            assert "from_cache" not in response.extensions
            # Re-enable cache and confirm that the response is cached
            response = await client.request(
                "GET",
                "https://www.example.com",
            )
            assert response.extensions["from_cache"]


@pytest.mark.anyio
async def test_nested_disable_cache():
    async with hishel.MockAsyncTransport() as transport:
        transport.add_responses(
            [httpx.Response(301, headers=[(b"Location", b"https://example.com")])]
        )
        async with hishel.AsyncCacheClient(transport=transport) as client:
            await client.request(
                "GET",
                "https://www.example.com",
            )
            # Disable cache and confirm that the response is not cached
            with client.cache_disabled():
                with client.cache_disabled():
                    with client.cache_disabled():
                        response = await client.request(
                            "GET",
                            "https://www.example.com",
                        )
            assert "from_cache" not in response.extensions
            # Re-enable cache and confirm that the response is cached
            response = await client.request(
                "GET",
                "https://www.example.com",
            )
            assert response.extensions["from_cache"]
