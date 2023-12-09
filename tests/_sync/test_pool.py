import httpcore
import pytest
from httpcore._models import Request, Response

import hishel
from hishel._utils import BaseClock, extract_header_values, header_presents



def test_pool_301(use_temp_dir):
    with hishel.MockConnectionPool() as pool:
        pool.add_responses([httpcore.Response(301, headers=[(b"Location", b"https://example.com")])])
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
        assert extract_header_values(response.headers, b"Content-Type", single=True)[0] == b"application/json"
        assert response.read() == b"test"



def test_pool_stale_response(use_temp_dir):
    controller = hishel.Controller(allow_stale=True)
    with hishel.MockConnectionPool() as pool:
        pool.add_responses(
            [
                httpcore.Response(
                    200,
                    headers=[
                        (b"Cache-Control", b"max-age=3600"),
                        (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
                    ],
                ),
                httpcore.Response(
                    200,
                    headers=[
                        (b"Cache-Control", b"max-age=3600"),
                        (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
                    ],
                ),
            ]
        )
        with hishel.CacheConnectionPool(pool=pool, controller=controller) as cache_pool:
            cache_pool.request("GET", "https://www.example.com")
            response = cache_pool.request("GET", "https://www.example.com")
            assert not response.extensions["from_cache"]



def test_pool_stale_response_with_connecterror(use_temp_dir):
    controller = hishel.Controller(allow_stale=True)

    class ConnectErrorPool(hishel.MockConnectionPool):
        def handle_request(self, request: Request) -> Response:
            if not hasattr(self, "not_first_request"):
                setattr(self, "not_first_request", object())
                return super().handle_request(request)
            raise httpcore._exceptions.ConnectError()

    with ConnectErrorPool() as pool:
        pool.add_responses(
            [
                httpcore.Response(
                    200,
                    headers=[
                        (b"Cache-Control", b"max-age=3600"),
                        (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
                    ],
                ),
            ]
        )
        with hishel.CacheConnectionPool(pool=pool, controller=controller) as cache_pool:
            cache_pool.request("GET", "https://www.example.com")
            response = cache_pool.request("GET", "https://www.example.com")
            assert response.extensions["from_cache"]



def test_pool_with_only_if_cached_directive_without_stored_response(use_temp_dir):
    controller = hishel.Controller()

    with hishel.MockConnectionPool() as pool:
        with hishel.CacheConnectionPool(pool=pool, controller=controller) as cache_pool:
            response = cache_pool.request(
                "GET",
                "https://www.example.com",
                headers=[(b"Cache-Control", b"only-if-cached")],
            )
            assert response.status == 504



def test_pool_with_only_if_cached_directive_with_stored_response(use_temp_dir):
    controller = hishel.Controller()

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
            ]
        )
        with hishel.CacheConnectionPool(pool=pool, controller=controller) as cache_pool:
            cache_pool.request("GET", "https://www.example.com")
            response = cache_pool.request(
                "GET",
                "https://www.example.com",
                headers=[(b"Cache-Control", b"only-if-cached")],
            )
            assert response.status == 504



def test_pool_with_cache_disabled_extension(use_temp_dir):
    class MockedClock(BaseClock):
        def now(self) -> int:
            return 1440504001  # Mon, 25 Aug 2015 12:00:01 GMT

    cachable_response = httpcore.Response(
        200,
        headers=[
            (b"Cache-Control", b"max-age=3600"),
            (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),  # 1 second before the clock
        ],
    )

    with hishel.MockConnectionPool() as pool:
        pool.add_responses([cachable_response, httpcore.Response(201)])
        with hishel.CacheConnectionPool(
            pool=pool, controller=hishel.Controller(clock=MockedClock())
        ) as cache_transport:
            request = httpcore.Request("GET", "https://www.example.com")
            # This should create a cache entry
            cache_transport.handle_request(request)
            # This should return from cache
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"]
            # This should ignore the cache
            caching_disabled_request = httpcore.Request(
                "GET", "https://www.example.com", extensions={"cache_disabled": True}
            )
            response = cache_transport.handle_request(caching_disabled_request)
            assert not response.extensions["from_cache"]
            assert response.status == 201



def test_transport_with_custom_key_generator():
    controller = hishel.Controller(key_generator=lambda request: request.url.host.decode())

    with hishel.MockConnectionPool() as pool:
        pool.add_responses([httpcore.Response(301)])
        with hishel.CacheConnectionPool(
            pool=pool,
            controller=controller,
        ) as cache_transport:
            request = httpcore.Request("GET", "https://www.example.com")
            # This should create a cache entry
            cache_transport.handle_request(request)
            # This should return from cache
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"]
            assert response.extensions["cache_metadata"]["cache_key"] == "www.example.com"
