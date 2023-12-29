from __future__ import annotations

import httpx
import pytest
import sniffio

import hishel
from hishel._utils import BaseClock


@pytest.mark.anyio
async def test_transport_301():
    async with hishel.MockAsyncTransport() as transport:
        transport.add_responses([httpx.Response(301, headers=[(b"Location", b"https://example.com")])])
        async with hishel.AsyncCacheTransport(
            transport=transport, storage=hishel.AsyncInMemoryStorage()
        ) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")

            await cache_transport.handle_async_request(request)
            response = await cache_transport.handle_async_request(request)
            assert response.extensions["from_cache"]


@pytest.mark.anyio
async def test_transport_response_validation():
    async with hishel.MockAsyncTransport() as transport:
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
    async with hishel.AsyncCacheTransport(
        transport=transport, storage=hishel.AsyncInMemoryStorage()
    ) as cache_transport:
        request = httpx.Request("GET", "https://www.example.com")

        await cache_transport.handle_async_request(request)
        response = await cache_transport.handle_async_request(request)
        assert response.status_code == 200
        assert response.extensions["from_cache"]
        assert "Content-Type" in response.headers
        assert response.headers["Content-Type"] == "application/json"
        assert await response.aread() == b"test"


@pytest.mark.anyio
async def test_transport_stale_response():
    controller = hishel.Controller(allow_stale=True)

    async with hishel.MockAsyncTransport() as transport:
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
        async with hishel.AsyncCacheTransport(
            transport=transport, controller=controller, storage=hishel.AsyncInMemoryStorage()
        ) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")
            await cache_transport.handle_async_request(request)
            response = await cache_transport.handle_async_request(request)
            assert not response.extensions["from_cache"]


@pytest.mark.anyio
async def test_transport_stale_response_with_connecterror():
    controller = hishel.Controller(allow_stale=True)

    class ConnectErrorTransport(hishel.MockAsyncTransport):
        async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
            if not hasattr(self, "not_first_request"):
                setattr(self, "not_first_request", object())
                return await super().handle_async_request(request)
            raise httpx._exceptions.ConnectError("test")

    async with ConnectErrorTransport() as transport:
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
        async with hishel.AsyncCacheTransport(
            transport=transport, controller=controller, storage=hishel.AsyncInMemoryStorage()
        ) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")
            await cache_transport.handle_async_request(request)
            response = await cache_transport.handle_async_request(request)
            assert response.extensions["from_cache"]


@pytest.mark.anyio
async def test_transport_with_only_if_cached_directive_without_stored_response():
    controller = hishel.Controller()

    async with hishel.MockAsyncTransport() as transport:
        async with hishel.AsyncCacheTransport(
            transport=transport, controller=controller, storage=hishel.AsyncInMemoryStorage()
        ) as cache_transport:
            response = await cache_transport.handle_async_request(
                httpx.Request(
                    "GET",
                    "https://www.example.com",
                    headers=[(b"Cache-Control", b"only-if-cached")],
                )
            )
            assert response.status_code == 504


@pytest.mark.anyio
async def test_transport_with_only_if_cached_directive_with_stored_response():
    controller = hishel.Controller()

    async with hishel.MockAsyncTransport() as transport:
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
        async with hishel.AsyncCacheTransport(
            transport=transport, controller=controller, storage=hishel.AsyncInMemoryStorage()
        ) as cache_transport:
            await cache_transport.handle_async_request(httpx.Request("GET", "https://www.example.com"))
            response = await cache_transport.handle_async_request(
                httpx.Request(
                    "GET",
                    "https://www.example.com",
                    headers=[(b"Cache-Control", b"only-if-cached")],
                )
            )
            assert response.status_code == 504


@pytest.mark.anyio
async def test_transport_with_cache_disabled_extension():
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

    async with hishel.MockAsyncTransport() as transport:
        transport.add_responses([cachable_response, httpx.Response(201)])
        async with hishel.AsyncCacheTransport(
            transport=transport,
            controller=hishel.Controller(clock=MockedClock()),
            storage=hishel.AsyncInMemoryStorage(),
        ) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")
            # This should create a cache entry
            await cache_transport.handle_async_request(request)
            # This should return from cache
            response = await cache_transport.handle_async_request(request)
            assert response.extensions["from_cache"]
            # This should ignore the cache
            caching_disabled_request = httpx.Request(
                "GET", "https://www.example.com", extensions={"cache_disabled": True}
            )
            response = await cache_transport.handle_async_request(caching_disabled_request)
            assert not response.extensions["from_cache"]
            assert response.status_code == 201


@pytest.mark.anyio
async def test_transport_with_custom_key_generator():
    controller = hishel.Controller(key_generator=lambda request: request.url.host.decode())

    async with hishel.MockAsyncTransport() as transport:
        transport.add_responses([httpx.Response(301)])
        async with hishel.AsyncCacheTransport(
            transport=transport,
            controller=controller,
            storage=hishel.AsyncInMemoryStorage(),
        ) as cache_transport:
            request = httpx.Request("GET", "https://www.example.com")
            # This should create a cache entry
            await cache_transport.handle_async_request(request)
            # This should return from cache
            response = await cache_transport.handle_async_request(request)
            assert response.extensions["from_cache"]
            assert response.extensions["cache_metadata"]["cache_key"] == "www.example.com"


@pytest.mark.anyio
async def test_transport_with_wrong_type_of_storage():
    storage: hishel.AsyncFileStorage | hishel.FileStorage

    try:  # pragma: no cover
        sniffio.current_async_library()
        error = "Expected subclass of `Async" "BaseStorage` but got `FileStorage`"
        storage = hishel.FileStorage()
    except sniffio.AsyncLibraryNotFoundError:  # pragma: no cover
        error = "Expected subclass of `BaseStorage` but got `Async" "FileStorage`"
        storage = getattr(hishel, "Async" + "FileStorage")()

    with pytest.raises(TypeError, match=error):
        hishel.AsyncCacheTransport(
            transport=hishel.MockAsyncTransport(),
            controller=hishel.Controller(),
            storage=storage,  # type: ignore
        )
