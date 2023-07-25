import pytest

import hishel


@pytest.mark.anyio
async def test_client():
    async with hishel.AsyncCacheClient() as client:
        await client.request(
            "GET",
            "https://httpbun.org/redirect/?url=https%3A//httpbun.org&status_code=301",
        )
        response = await client.request(
            "GET",
            "https://httpbun.org/redirect/?url=https%3A//httpbun.org&status_code=301",
        )
        assert "network_stream" not in response.extensions  # from cache
