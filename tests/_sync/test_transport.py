import typing as tp

import httpx
import pytest
import sniffio

import hishel
from hishel._utils import BaseClock, extract_header_values_decoded



def test_transport_301():
    with hishel.MockTransport() as transport:
        transport.add_responses([httpx.Response(301, headers=[(b"Location", b"https://example.com")])])
        with hishel.CacheTransport(
            transport=transport, storage=hishel.InMemoryStorage()
        ) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")

            cache_transport.handle_request(request)
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"]



def test_transport_response_validation():
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
    with hishel.CacheTransport(
        transport=transport, storage=hishel.InMemoryStorage()
    ) as cache_transport:
        request = httpx.Request("GET", "https://www.example.com")

        cache_transport.handle_request(request)
        response = cache_transport.handle_request(request)
        assert response.status_code == 200
        assert response.extensions["from_cache"]
        assert "Content-Type" in response.headers
        assert response.headers["Content-Type"] == "application/json"
        assert response.read() == b"test"



def test_transport_stale_response():
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
            transport=transport, controller=controller, storage=hishel.InMemoryStorage()
        ) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")
            cache_transport.handle_request(request)
            response = cache_transport.handle_request(request)
            assert not response.extensions["from_cache"]



def test_transport_stale_response_with_connecterror():
    controller = hishel.Controller(allow_stale=True)

    class ConnectErrorTransport(hishel.MockTransport):
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
            transport=transport, controller=controller, storage=hishel.InMemoryStorage()
        ) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")
            cache_transport.handle_request(request)
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"]



def test_transport_with_only_if_cached_directive_without_stored_response():
    controller = hishel.Controller()

    with hishel.MockTransport() as transport:
        with hishel.CacheTransport(
            transport=transport, controller=controller, storage=hishel.InMemoryStorage()
        ) as cache_transport:
            response = cache_transport.handle_request(
                httpx.Request(
                    "GET",
                    "https://www.example.com",
                    headers=[(b"Cache-Control", b"only-if-cached")],
                )
            )
            assert response.status_code == 504



def test_transport_with_only_if_cached_directive_with_stored_response():
    controller = hishel.Controller()

    with hishel.MockTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    200,
                    headers=[
                        (b"Cache-Control", b"max-age=3600"),
                        (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
                    ],
                    content=b"test",
                ),
            ]
        )
        with hishel.CacheTransport(
            transport=transport, controller=controller, storage=hishel.InMemoryStorage()
        ) as cache_transport:
            cache_transport.handle_request(httpx.Request("GET", "https://www.example.com"))
            response = cache_transport.handle_request(
                httpx.Request(
                    "GET",
                    "https://www.example.com",
                    headers=[(b"Cache-Control", b"only-if-cached")],
                )
            )
            assert response.status_code == 504



def test_transport_with_cache_disabled_extension():
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
            transport=transport,
            controller=hishel.Controller(clock=MockedClock()),
            storage=hishel.InMemoryStorage(),
        ) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")
            # This should create a cache entry
            cache_transport.handle_request(request)
            # This should return from cache
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"]
            # This should ignore the cache
            caching_disabled_request = httpx.Request(
                "GET", "https://www.example.com", extensions={"cache_disabled": True}
            )
            response = cache_transport.handle_request(caching_disabled_request)
            assert not response.extensions["from_cache"]
            assert response.status_code == 201



def test_transport_with_custom_key_generator():
    controller = hishel.Controller(key_generator=lambda request, body: request.url.host.decode())

    with hishel.MockTransport() as transport:
        transport.add_responses([httpx.Response(301)])
        with hishel.CacheTransport(
            transport=transport,
            controller=controller,
            storage=hishel.InMemoryStorage(),
        ) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")
            # This should create a cache entry
            cache_transport.handle_request(request)
            # This should return from cache
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"]
            assert response.extensions["cache_metadata"]["cache_key"] == "www.example.com"



def test_transport_with_wrong_type_of_storage():
    storage: tp.Union[hishel.FileStorage, hishel.FileStorage]

    try:  # pragma: no cover
        sniffio.current_async_library()
        error = "Expected subclass of `Async" "BaseStorage` but got `FileStorage`"
        storage = hishel.FileStorage()
    except sniffio.AsyncLibraryNotFoundError:  # pragma: no cover
        error = "Expected subclass of `BaseStorage` but got `Async" "FileStorage`"
        storage = getattr(hishel, "Async" + "FileStorage")()

    with pytest.raises(TypeError, match=error):
        hishel.CacheTransport(
            transport=hishel.MockTransport(),
            controller=hishel.Controller(),
            storage=storage,  # type: ignore
        )



def test_transport_caching_post_method():
    controller = hishel.Controller(cacheable_methods=["POST"])

    with hishel.MockTransport() as transport:
        transport.add_responses([httpx.Response(301), httpx.Response(200)])
        with hishel.CacheTransport(
            transport=transport,
            controller=controller,
            storage=hishel.InMemoryStorage(),
        ) as cache_transport:
            request = httpx.Request("POST", "https://www.example.com", json={"request": 1})
            # This should create a cache entry
            cache_transport.handle_request(request)
            # This should return from cache
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"]

            # Method and URL are the same but the body is different
            request = httpx.Request("POST", "https://www.example.com", json={"request": 2})

            # This should create a new cache entry instead of using the previous one
            response = cache_transport.handle_request(request)
            assert response.status_code == 200
            assert not response.extensions["from_cache"]



def test_transport_revalidation():
    class MockedClock(BaseClock):
        def __init__(self, initial: int):
            self.current = initial

        def now(self) -> int:
            return self.current

        def inc(self, seconds: int = 1) -> None:
            self.current += seconds

    clock = MockedClock(1440504000)  # Tue, 25 Aug 2015 12:00:00 GMT
    controller = hishel.Controller(clock=clock)
    storage = hishel.InMemoryStorage()

    with hishel.MockTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    200,
                    headers=[
                        (b"Cache-Control", b"max-age=2"),
                        (b"Date", b"Tue, 25 Aug 2015 12:00:00 GMT"),
                    ],
                    content=b"Hello, World.",
                ),
                httpx.Response(
                    200,
                    headers=[
                        (b"Cache-Control", b"max-age=2"),
                        (b"Date", b"Tue, 25 Aug 2015 12:00:02 GMT"),
                    ],
                    content=b"Hello, World.",
                ),
                httpx.Response(
                    304,
                    headers=[
                        (b"Cache-Control", b"max-age=2"),
                        (b"Date", b"Tue, 25 Aug 2015 12:00:04 GMT"),
                    ],
                ),
            ]
        )
        with hishel.CacheTransport(
            transport=transport,
            controller=controller,
            storage=storage,
        ) as cache_transport:
            request = httpx.Request("GET", "https://example.com/")

            # MISS
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"] is False

            # HIT
            clock.inc()
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"] is True

            # Cache contains the right date
            stored = storage.retrieve(response.extensions["cache_metadata"]["cache_key"])
            assert stored
            stored_response, stored_request, stored_metadata = stored
            assert extract_header_values_decoded(stored_response.headers, b"Date") == ["Tue, 25 Aug 2015 12:00:00 GMT"]

            # Found in cache, but expired ... MISS
            clock.inc()
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"] is False

            # HIT, new cache version
            clock.inc()
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"] is True

            # Cache contains the right date
            stored = storage.retrieve(response.extensions["cache_metadata"]["cache_key"])
            assert stored
            stored_response, stored_request, stored_metadata = stored
            assert extract_header_values_decoded(stored_response.headers, b"Date") == ["Tue, 25 Aug 2015 12:00:02 GMT"]

            # HIT after revalidation
            clock.inc()
            response = cache_transport.handle_request(request)
            assert response.extensions["from_cache"] is True

            # Date is updated, but the original content is still there (although 304 did not contain it)
            stored = storage.retrieve(response.extensions["cache_metadata"]["cache_key"])
            assert stored
            stored_response, stored_request, stored_metadata = stored
            assert extract_header_values_decoded(stored_response.headers, b"Date") == ["Tue, 25 Aug 2015 12:00:04 GMT"]
            assert stored_response.status == 200
            stored_response.read()
            assert stored_response.content == b"Hello, World."
