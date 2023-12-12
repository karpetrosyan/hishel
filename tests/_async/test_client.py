import httpx
import pytest

import hishel


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
