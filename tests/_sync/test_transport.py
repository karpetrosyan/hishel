import httpx
import pytest

import hishel



def test_transport_301(use_temp_dir):
    with hishel.MockTransport() as transport:
        transport.add_responses(
            [httpx.Response(301, headers=[(b"Location", b"https://example.com")])]
        )
        with hishel.CacheTransport(transport=transport) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")

            cache_transport.handle_request(request)
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"]



def test_transport_response_validation(use_temp_dir):
    with hishel.MockTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    200,
                    headers=[
                        (b"Cache-Control", b"max-age=3600"),
                        (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
                    ],
                    content="test",
                ),
                httpx.Response(
                    304,
                    headers=[
                        (b"Cache-Control", b"max-age=3600"),
                        (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
                        (b"Content-Type", b"application/json"),
                    ],
                ),
            ]
        )
    with hishel.CacheTransport(transport=transport) as cache_transport:
        request = httpx.Request("GET", "https://www.example.com")

        cache_transport.handle_request(request)
        response = cache_transport.handle_request(request)
        assert response.status_code == 200
        assert response.extensions["from_cache"]
        assert "Content-Type" in response.headers
        assert response.headers["Content-Type"] == "application/json"
        assert response.read() == b"test"



def test_transport_stale_response(use_temp_dir):
    controller = hishel.Controller(allow_stale=True)

    with hishel.MockTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    200,
                    headers=[
                        (b"Cache-Control", b"max-age=3600"),
                        (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
                    ],
                ),
                httpx.Response(
                    200,
                    headers=[
                        (b"Cache-Control", b"max-age=3600"),
                        (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
                    ],
                ),
            ]
        )
        with hishel.CacheTransport(
            transport=transport, controller=controller
        ) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")
            cache_transport.handle_request(request)
            response = cache_transport.handle_request(request)
            assert not response.extensions["from_cache"]



def test_transport_stale_response_with_connecterror(use_temp_dir):
    controller = hishel.Controller(allow_stale=True)

    class ConnectErrorTransport(hishel.MockConnectionPool):
        def handle_request(self, request: httpx.Request) -> httpx.Response:
            if not hasattr(self, "not_first_request"):
                setattr(self, "not_first_request", object())
                return super().handle_request(request)
            raise httpx._exceptions.ConnectError("test")

    with ConnectErrorTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    200,
                    headers=[
                        (b"Cache-Control", b"max-age=3600"),
                        (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
                    ],
                ),
                httpx.Response(
                    200,
                    headers=[
                        (b"Cache-Control", b"max-age=3600"),
                        (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
                    ],
                ),
            ]
        )
        with hishel.CacheTransport(
            transport=transport, controller=controller
        ) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")
            cache_transport.handle_request(request)
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"]
