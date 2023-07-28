import httpcore
import pytest

import hishel


@pytest.mark.anyio
async def test_pool_301(use_temp_dir):
    async with hishel.MockAsyncConnectionPool() as pool:
        pool.add_responses(
            [httpcore.Response(301, headers=[(b"Location", b"https://example.com")])]
        )
        async with hishel.AsyncCacheConnectionPool(pool=pool) as cache_pool:
            await cache_pool.request("GET", "https://www.example.com")
            response = await cache_pool.request("GET", "https://www.example.com")
            assert response.extensions["from_cache"]
