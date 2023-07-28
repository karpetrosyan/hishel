import httpcore
import pytest

import hishel
from hishel._utils import extract_header_values, header_presents



def test_pool_301(use_temp_dir):
    with hishel.MockConnectionPool() as pool:
        pool.add_responses(
            [httpcore.Response(301, headers=[(b"Location", b"https://example.com")])]
        )
        with hishel.CacheConnectionPool(pool=pool) as cache_pool:
            cache_pool.request("GET", "https://www.example.com")
            response = cache_pool.request("GET", "https://www.example.com")
            assert response.extensions["from_cache"]



def test_pool_response_validation(use_temp_dir):
    with hishel.MockConnectionPool() as pool:
        pool.add_responses(
            [
                httpcore.Response(
                    200,
                    headers=[
                        (b"Cache-Control", b"max-age=3600"),
                        (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
                    ],
                    content=b"test",
                ),
                httpcore.Response(
                    304,
                    headers=[
                        (b"Cache-Control", b"max-age=3600"),
                        (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
                        (b"Content-Type", b"application/json"),
                    ],
                ),
            ]
        )
    with hishel.CacheConnectionPool(pool=pool) as cache_pool:
        request = httpcore.Request("GET", "https://www.example.com")

        cache_pool.handle_request(request)
        response = cache_pool.handle_request(request)
        assert response.status == 200
        assert response.extensions["from_cache"]
        assert header_presents(response.headers, b"Content-Type")
        assert (
            extract_header_values(response.headers, b"Content-Type", single=True)[0]
            == b"application/json"
        )
        assert response.read() == b"test"
