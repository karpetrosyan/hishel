import httpx
import pytest

import hishel



def test_transport():
    with httpx.HTTPTransport() as transport:
        with hishel.CacheTransport(transport=transport) as cache_transport:
            request = httpx.Request(
                "GET",
                "https://httpbun.org/redirect/?url=https%3A//httpbun.org&status_code=301",
            )

            cache_transport.handle_request(request)
            response = cache_transport.handle_request(request)
            assert "network_stream" not in response.extensions
