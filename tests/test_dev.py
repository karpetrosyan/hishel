import httpx

import hishel
from hishel._utils import BaseClock


def test_transport_with_cache_disabled_extension(use_temp_dir):
    class MockedClock(BaseClock):
        def now(self) -> int:
            return 1440504001  # Mon, 25 Aug 2015 12:00:01 GMT

    cachable_response = httpx.Response(
        200,
        headers=[
            (b"Cache-Control", b"max-age=3600"),
            (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),  # 1 second before the clock
        ],
    )

    with hishel.MockTransport() as transport:
        transport.add_responses([cachable_response, httpx.Response(201)])
        with hishel.CacheTransport(
            transport=transport, controller=hishel.Controller(clock=MockedClock())
        ) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")
            # This should create a cache entry
            cache_transport.handle_request(request)
            # This should return from cache
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"]
            # This should ignore the cache
            caching_disabled_request = httpx.Request(
                "GET", "https://www.example.com", headers={"Cache-Control": "max-age=0"}
            )
            response = cache_transport.handle_request(caching_disabled_request)
            assert not response.extensions["from_cache"]
            assert response.status_code == 201
