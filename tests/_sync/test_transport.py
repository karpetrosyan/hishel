import httpx
import pytest

import hishel



def test_transport_301():
    with hishel.MockTransport() as transport:
        transport.add_responses(
            [httpx.Response(301, headers=[(b"Location", b"https://example.com")])]
        )
        with hishel.CacheTransport(transport=transport) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")

            cache_transport.handle_request(request)
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"]
