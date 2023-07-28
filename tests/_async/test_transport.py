import httpx
import pytest

import hishel


@pytest.mark.anyio
async def test_transport_301():
    async with hishel.MockAsyncTransport() as transport:
        transport.add_responses(
            [httpx.Response(301, headers=[(b"Location", b"https://example.com")])]
        )
        async with hishel.AsyncCacheTransport(transport=transport) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")

            await cache_transport.handle_async_request(request)
            response = await cache_transport.handle_async_request(request)
            assert response.extensions["from_cache"]
