import httpcore
import pytest

import hishel



def test_pool(use_temp_dir):
    with httpcore.ConnectionPool() as pool:
        with hishel.CacheConnectionPool(pool=pool) as cached_pool:
            cached_pool.request("GET", "https://httpbun.org/redirect/?url=https%3A//httpbun.org&status_code=301")
            response = cached_pool.request("GET", "https://httpbun.org/redirect/?url=https%3A//httpbun.org&status_code=301")
            assert "network_stream" not in response.extensions  # from cache
