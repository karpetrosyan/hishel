import httpx
import pytest

import hishel


@pytest.mark.anyio
async def test_transport():
    async with httpx.AsyncHTTPTransport() as transport:
        async with hishel.AsyncCacheTransport(transport=transport) as cache_transport:
            request = httpx.Request(
                "GET",
                "https://httpbun.org/redirect/?url=https%3A//httpbun.org&status_code=301",
            )

            await cache_transport.handle_async_request(request)
            response = await cache_transport.handle_async_request(request)
            assert "network_stream" not in response.extensions
