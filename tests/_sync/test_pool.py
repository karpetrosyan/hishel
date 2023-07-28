import httpcore
import pytest

import hishel



def test_pool_301(use_temp_dir):
    with hishel.MockConnectionPool() as pool:
        pool.add_responses(
            [httpcore.Response(301, headers=[(b"Location", b"https://example.com")])]
        )
        with hishel.CacheConnectionPool(pool=pool) as cache_pool:
            cache_pool.request("GET", "https://www.example.com")
            response = cache_pool.request("GET", "https://www.example.com")
            assert response.extensions["from_cache"]
