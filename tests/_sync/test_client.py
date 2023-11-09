import httpx
import pytest

import hishel



def test_client_301():
    with hishel.MockTransport() as transport:
        transport.add_responses(
            [httpx.Response(301, headers=[(b"Location", b"https://example.com")])]
        )
        with hishel.CacheClient(transport=transport) as client:
            client.request(
                "GET",
                "https://www.example.com",
            )
            response = client.request(
                "GET",
                "https://www.example.com",
            )
            assert response.extensions["from_cache"]

def test_disable_cache():
    with hishel.MockTransport() as transport:
        transport.add_responses(
            [httpx.Response(301, headers=[(b"Location", b"https://example.com")])]
        )
        with hishel.CacheClient(transport=transport) as client:
            client.request(
                "GET",
                "https://www.example.com",
            )
            # Disable cache and confirm that the response is not cached
            with client.cache_disabled():
                response = client.request(
                    "GET",
                    "https://www.example.com",
                )
            assert "from_cache" not in response.extensions
            # Re-enable cache and confirm that the response is cached
            response = client.request(
                "GET",
                "https://www.example.com",
            )
            assert response.extensions["from_cache"]