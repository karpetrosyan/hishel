import pytest

import hishel



def test_transport():
    with hishel.CacheClient() as client:
        client.request(
            "GET",
            "https://httpbun.org/redirect/?url=https%3A//httpbun.org&status_code=301",
        )
        response = client.request(
            "GET",
            "https://httpbun.org/redirect/?url=https%3A//httpbun.org&status_code=301",
        )
        assert "network_stream" not in response.extensions  # from cache
