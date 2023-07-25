import httpcore
import pytest

import hishel


@pytest.mark.anyio
async def test_pool(use_temp_dir):
    async with httpcore.AsyncConnectionPool() as pool:
        async with hishel.AsyncCacheConnectionPool(pool=pool) as cached_pool:
            await cached_pool.request(
                "GET",
                "https://httpbun.org/redirect/?url=https%3A//httpbun.org&status_code=301",
            )
            response = await cached_pool.request(
                "GET",
                "https://httpbun.org/redirect/?url=https%3A//httpbun.org&status_code=301",
            )
            assert "network_stream" not in response.extensions  # from cache
