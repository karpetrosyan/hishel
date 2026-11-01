import gzip
import hashlib
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, AsyncIterator

import anysqlite
import fakeredis.aioredis
import httpx2
import pytest
from redis import RedisError
from time_machine import travel

from hishel import AsyncRedisStorage, AsyncSqliteStorage
from hishel.httpx2 import AsyncCacheClient, AsyncCacheTransport

START = datetime(2026, 1, 1, tzinfo=timezone.utc)
URL = "https://x/"


@pytest.fixture
def anyio_backend():
    return "asyncio"


def at(seconds):
    return travel(START + timedelta(seconds=seconds), tick=False)


async def new_storage(kind="sqlite", **kwargs):
    if kind == "sqlite":
        return AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"), **kwargs)
    kwargs.setdefault("default_ttl", None)
    return AsyncRedisStorage(fakeredis.aioredis.FakeRedis(), **kwargs)


class Upstream(httpx2.MockTransport):
    """Answers from a handler and records every request it receives."""

    def __init__(self, handler=None):
        self.requests: list[httpx2.Request] = []
        self.sent_headers: list[Any] = []

        def recording(request):
            self.requests.append(request)
            self.sent_headers.append(request.headers.copy())
            return handler(request) if handler else httpx2.Response(200, content=b"body")

        super().__init__(recording)


class TrackedStream(httpx2.SyncByteStream, httpx2.AsyncByteStream):
    """A real streaming body, which unlike content= isn't read up front, and which records being closed."""

    def __init__(self, chunks):
        self.chunks = chunks
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk

    async def aclose(self):
        self.closed = True


async def client_for(upstream, kind="sqlite", rfc=False, **kwargs):
    storage = await new_storage(kind, **kwargs)
    return httpx2.AsyncClient(transport=AsyncCacheTransport(upstream, storage=storage, rfc=rfc))


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["sqlite", "redis"])
async def test_second_get_is_served_from_cache(kind):
    upstream = Upstream(lambda r: httpx2.Response(200, headers={"x-a": "1"}, content=b"body"))
    client = await client_for(upstream, kind)
    first = await client.get(URL)
    second = await client.get(URL)
    assert first.content == second.content == b"body"
    assert (first.status_code, second.status_code) == (200, 200)
    assert second.headers["x-a"] == "1"
    assert len(upstream.requests) == 1


@pytest.mark.anyio
async def test_different_urls_are_separate():
    upstream = Upstream()
    client = await client_for(upstream)
    await client.get("https://x/a")
    await client.get("https://x/b")
    await client.get("https://x/a?q=1")
    assert len(upstream.requests) == 3


@pytest.mark.anyio
async def test_get_and_head_are_separate_and_post_is_never_cached():
    upstream = Upstream()
    client = await client_for(upstream)
    await client.get(URL)
    await client.head(URL)
    await client.head(URL)
    assert len(upstream.requests) == 2
    await client.post(URL, content=b"x")
    await client.post(URL, content=b"x")
    assert upstream.requests[-1].content == b"x"
    assert len(upstream.requests) == 4
    await client.get(URL)
    assert len(upstream.requests) == 4


@pytest.mark.anyio
@pytest.mark.parametrize("status", [404, 500, 206, 301])
async def test_unsuccessful_and_partial_responses_are_not_cached(status):
    upstream = Upstream(lambda r: httpx2.Response(status, content=b"x"))
    client = await client_for(upstream)
    assert (await client.get(URL)).status_code == status
    await client.get(URL)
    assert len(upstream.requests) == 2


@pytest.mark.anyio
async def test_uncacheable_response_is_returned_as_is():
    response = httpx2.Response(500, content=b"x")
    transport = AsyncCacheTransport(Upstream(lambda r: response), storage=await new_storage(), rfc=False)
    assert await transport.handle_async_request(httpx2.Request("GET", URL)) is response


@pytest.mark.anyio
async def test_http_caching_headers_are_ignored():
    upstream = Upstream(lambda r: httpx2.Response(200, headers={"cache-control": "no-store"}, content=b"body"))
    client = await client_for(upstream)
    await client.get(URL)
    await client.get(URL, headers={"cache-control": "no-cache"})
    assert len(upstream.requests) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["sqlite", "redis"])
async def test_entry_expires_with_the_storage_ttl(kind):
    upstream = Upstream()
    client = await client_for(upstream, kind, default_ttl=100)
    with at(0):
        await client.get(URL)
    with at(99):
        await client.get(URL)
        assert len(upstream.requests) == 1
    with at(101):
        await client.get(URL)
        assert len(upstream.requests) == 2


@pytest.mark.anyio
async def test_streamed_body_is_cached_and_upstream_is_closed():
    stream = TrackedStream([b"a", b"b"])
    upstream = Upstream(lambda r: httpx2.Response(200, stream=stream))
    client = await client_for(upstream)
    assert (await client.get(URL)).content == b"ab"
    assert stream.closed
    assert (await client.get(URL)).content == b"ab"
    assert len(upstream.requests) == 1


@pytest.mark.anyio
async def test_abandoned_stream_is_not_cached_and_upstream_is_closed():
    stream = TrackedStream([b"a", b"b", b"c"])
    upstream = Upstream(lambda r: httpx2.Response(200, stream=stream))
    transport = AsyncCacheTransport(upstream, storage=await new_storage(), rfc=False)
    client = httpx2.AsyncClient(transport=transport)
    async with client.stream("GET", URL) as response:
        async for _ in response.aiter_raw():
            break
    assert stream.closed

    upstream2 = TrackedStream([b"fresh"])
    transport.next_transport = Upstream(lambda r: httpx2.Response(200, stream=upstream2))
    assert (await client.get(URL)).content == b"fresh"


@pytest.mark.anyio
async def test_compressed_body_is_stored_raw_and_decoded_on_every_read():
    raw = gzip.compress(b"hello")
    upstream = Upstream(
        lambda r: httpx2.Response(
            200,
            headers={"content-encoding": "gzip", "content-length": str(len(raw))},
            stream=TrackedStream([raw]),
        )
    )
    transport = AsyncCacheTransport(upstream, storage=await new_storage(), rfc=False)
    client = httpx2.AsyncClient(transport=transport)
    assert (await client.get(URL)).content == b"hello"
    second = await client.get(URL)
    assert second.content == b"hello"
    assert second.headers["content-encoding"] == "gzip"
    assert second.num_bytes_downloaded == len(raw)


@pytest.mark.anyio
async def test_already_read_compressed_response_stays_consistent():
    raw = gzip.compress(b"hello")
    upstream = Upstream(lambda r: httpx2.Response(200, headers={"content-encoding": "gzip"}, content=raw))
    client = await client_for(upstream)
    assert (await client.get(URL)).content == b"hello"
    second = await client.get(URL)
    assert second.content == b"hello"
    assert "content-encoding" not in second.headers
    assert second.headers["content-length"] == "5"


@pytest.mark.anyio
async def test_repeated_headers_are_kept_separate_on_miss_and_hit():
    upstream = Upstream(
        lambda r: httpx2.Response(200, headers=[("set-cookie", "a=1"), ("set-cookie", "b=2, c")], content=b"x")
    )
    client = await client_for(upstream)
    for _ in range(2):
        response = await client.get(URL)
        assert response.headers.get_list("set-cookie") == ["a=1", "b=2, c"]
    assert len(upstream.requests) == 1


SET_COOKIES = [("set-cookie", "a=1; Expires=Thu, 01 Jan 2032 00:00:00 GMT"), ("set-cookie", "b=2")]
SET_COOKIE_VALUES = [value for _, value in SET_COOKIES]


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["sqlite", "redis"])
async def test_rfc_keeps_repeated_set_cookie_separate_on_miss_and_hit(kind):
    headers = [*SET_COOKIES, ("cache-control", "max-age=10"), ("date", date_at(0))]
    upstream = Upstream(lambda r: httpx2.Response(200, headers=headers, content=b"x"))
    client = await client_for(upstream, kind, rfc=True)
    with at(0):
        for _ in range(2):
            response = await client.get(URL)
            assert response.headers.get_list("set-cookie") == SET_COOKIE_VALUES
    assert len(upstream.requests) == 1
    assert dict(client.cookies) == {"a": "1", "b": "2"}


@pytest.mark.anyio
async def test_rfc_keeps_repeated_set_cookie_separate_when_not_stored():
    headers = [*SET_COOKIES, ("cache-control", "no-store")]
    client = await client_for(Upstream(lambda r: httpx2.Response(200, headers=headers, content=b"x")), rfc=True)
    response = await client.get(URL)
    assert response.headers.get_list("set-cookie") == SET_COOKIE_VALUES
    assert dict(client.cookies) == {"a": "1", "b": "2"}


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["sqlite", "redis"])
async def test_rfc_keeps_repeated_set_cookie_separate_after_revalidation(kind):
    answers = iter(
        [
            httpx2.Response(
                200,
                headers=[*SET_COOKIES, ("cache-control", "max-age=10"), ("etag", '"v1"'), ("date", date_at(0))],
                content=b"x",
            ),
            httpx2.Response(304, headers={"etag": '"v1"', "cache-control": "max-age=10", "date": date_at(100)}),
        ]
    )
    upstream = Upstream(lambda r: next(answers))
    client = await client_for(upstream, kind, rfc=True)
    with at(0):
        await client.get(URL)
    with at(100):
        revalidated = await client.get(URL)
        hit = await client.get(URL)
    assert revalidated.headers.get_list("set-cookie") == SET_COOKIE_VALUES
    assert hit.headers.get_list("set-cookie") == SET_COOKIE_VALUES
    assert len(upstream.requests) == 2


@pytest.mark.anyio
async def test_transfer_encoding_is_not_replayed():
    upstream = Upstream(
        lambda r: httpx2.Response(200, headers={"transfer-encoding": "chunked"}, stream=TrackedStream([b"x"]))
    )
    client = await client_for(upstream)
    await client.get(URL)
    assert "transfer-encoding" not in (await client.get(URL)).headers


@pytest.mark.anyio
async def test_original_request_reaches_upstream_untouched():
    upstream = Upstream()
    client = await client_for(upstream)
    await client.get(URL, timeout=7, extensions={"custom": "yes"})
    sent = upstream.requests[0]
    assert sent.extensions["custom"] == "yes"
    assert sent.extensions["timeout"]["read"] == 7


@pytest.mark.anyio
async def test_miss_keeps_upstream_extensions_and_hit_works_without_them():
    upstream = Upstream(
        lambda r: httpx2.Response(200, extensions={"http_version": b"HTTP/2"}, stream=TrackedStream([b"x"]))
    )
    client = await client_for(upstream)
    assert (await client.get(URL)).http_version == "HTTP/2"
    assert (await client.get(URL)).http_version == "HTTP/1.1"


@pytest.mark.anyio
async def test_storage_failure_still_serves_the_response(caplog):
    upstream = Upstream(lambda r: httpx2.Response(200, stream=TrackedStream([b"x" * 500])))
    client = await client_for(upstream, max_stream_size=10)
    assert (await client.get(URL)).content == b"x" * 500
    assert (await client.get(URL)).content == b"x" * 500
    assert len(upstream.requests) == 2


@pytest.mark.anyio
async def test_closing_transport_closes_upstream_and_storage():
    storage = await new_storage()
    closed = []

    class Next(Upstream):
        async def aclose(self):
            closed.append("upstream")

    transport = AsyncCacheTransport(Next(), storage=storage)
    await transport.aclose()
    assert closed == ["upstream"]
    with pytest.raises(RuntimeError, match="closed"):
        await storage.get_entries("k")


# A real server, so real sockets, chunked encoding and gzip are involved.


class Handler(BaseHTTPRequestHandler):
    hits = 0
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        type(self).hits += 1
        body = gzip.compress(b"hello " * 100000)
        self.send_response(200)
        self.send_header("Content-Encoding", "gzip")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("Set-Cookie", "a=1")
        self.send_header("Set-Cookie", "b=2")
        self.end_headers()
        for start in range(0, len(body), 100):
            part = body[start : start + 100]
            self.wfile.write(b"%x\r\n%s\r\n" % (len(part), part))
        self.wfile.write(b"0\r\n\r\n")

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    Handler.hits = 0
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}/"
    httpd.shutdown()


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["sqlite", "redis"])
async def test_client_against_a_real_server(server, kind):
    storage = await new_storage(kind)
    async with AsyncCacheClient(storage=storage, trust_env=False, rfc=False) as client:
        assert isinstance(client._transport, AsyncCacheTransport)
        first = await client.get(server)
        second = await client.get(server)
        assert first.text == second.text == "hello " * 100000
        assert Handler.hits == 1
        assert second.headers.get_list("set-cookie") == ["a=1", "b=2"]
        assert "transfer-encoding" not in second.headers


@pytest.mark.anyio
async def test_client_with_default_sqlite_storage_in_a_file(server, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    async with AsyncCacheClient(trust_env=False, rfc=False) as client:
        assert (await client.get(server)).status_code == 200
        assert (await client.get(server)).status_code == 200
    assert Handler.hits == 1


# RFC mode, and per-request overrides


def date_at(seconds):
    return format_datetime(START + timedelta(seconds=seconds), usegmt=True)


def fresh(body=b"body", seconds=0, **headers):
    return httpx2.Response(
        200, headers={"cache-control": "max-age=100", "date": date_at(seconds), **headers}, content=body
    )


def stale_then(*later):
    """A response that is stale after 10s, followed by whatever the revalidation should answer."""
    answers = iter(
        [
            httpx2.Response(
                200,
                headers={"cache-control": "max-age=10", "etag": '"v1"', "date": date_at(0)},
                stream=TrackedStream([b"one"]),
            ),
            *later,
        ]
    )
    return Upstream(lambda r: next(answers))


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["sqlite", "redis"])
async def test_rfc_serves_fresh_responses(kind):
    upstream = Upstream(lambda r: fresh())
    storage = await new_storage(kind)
    client = httpx2.AsyncClient(transport=AsyncCacheTransport(upstream, storage=storage, rfc=True))
    with at(0):
        assert (await client.get(URL)).content == b"body"
    with at(50):
        response = await client.get(URL)
    assert response.content == b"body"
    assert int(response.headers["age"]) == 50
    assert len(upstream.requests) == 1


@pytest.mark.anyio
async def test_rfc_respects_no_store():
    upstream = Upstream(lambda r: httpx2.Response(200, headers={"cache-control": "no-store"}, content=b"body"))
    client = await client_for(upstream, rfc=True)
    await client.get(URL)
    await client.get(URL)
    assert len(upstream.requests) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["sqlite", "redis"])
async def test_rfc_304_serves_the_cached_body_with_new_headers(kind):
    upstream = stale_then(
        httpx2.Response(
            304, headers={"cache-control": "max-age=10", "etag": '"v1"', "x-fresh": "yes", "date": date_at(100)}
        )
    )
    client = await client_for(upstream, kind, rfc=True)
    with at(0):
        assert (await client.get(URL)).content == b"one"
    with at(100):
        response = await client.get(URL, timeout=7)
    assert response.content == b"one"
    assert response.headers["x-fresh"] == "yes"
    assert upstream.sent_headers[1]["if-none-match"] == '"v1"'
    assert upstream.requests[1].extensions["timeout"]["read"] == 7
    with at(105):
        assert (await client.get(URL)).content == b"one"
    assert len(upstream.requests) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("status", [200, 500])
async def test_rfc_full_response_to_revalidation_is_served(status):
    stream = TrackedStream([b"two"])
    upstream = stale_then(httpx2.Response(status, headers={"date": date_at(100)}, stream=stream))
    client = await client_for(upstream, rfc=True)
    with at(0):
        await client.get(URL)
    with at(100):
        response = await client.get(URL)
    assert (response.status_code, response.content) == (status, b"two")
    assert stream.closed


@pytest.mark.anyio
async def test_rfc_304_matching_nothing_goes_back_upstream_without_conditions():
    upstream = stale_then(
        httpx2.Response(304, headers={"etag": '"other"', "date": date_at(100)}),
        httpx2.Response(
            200, headers={"cache-control": "max-age=10", "date": date_at(100)}, stream=TrackedStream([b"two"])
        ),
    )
    client = await client_for(upstream, rfc=True)
    with at(0):
        await client.get(URL)
    with at(100):
        assert (await client.get(URL)).content == b"two"
    assert "if-none-match" not in upstream.sent_headers[2]


@pytest.mark.anyio
async def test_rfc_abandoned_stream_is_not_cached_and_upstream_is_closed():
    stream = TrackedStream([b"a", b"b"])
    upstream = Upstream(
        lambda r: httpx2.Response(200, headers={"cache-control": "max-age=100", "date": date_at(0)}, stream=stream)
    )
    client = await client_for(upstream, rfc=True)
    with at(0):
        async with client.stream("GET", URL) as response:
            async for _ in response.aiter_raw():
                break
        assert stream.closed
        assert (await client.get(URL)).content == b"ab"
    assert len(upstream.requests) == 2


@pytest.mark.anyio
async def test_rfc_request_body_reaches_upstream():
    upstream = Upstream()
    client = await client_for(upstream, rfc=True)
    await client.post(URL, content=b"payload")
    assert upstream.requests[0].content == b"payload"


@pytest.mark.anyio
async def test_request_can_turn_rfc_off():
    upstream = Upstream(lambda r: httpx2.Response(200, headers={"cache-control": "no-store"}, content=b"body"))
    client = await client_for(upstream, rfc=True)
    await client.get(URL, extensions={"caching": {"rfc": False}})
    await client.get(URL, extensions={"caching": {"rfc": False}})
    assert len(upstream.requests) == 1


@pytest.mark.anyio
async def test_request_can_turn_rfc_on():
    upstream = Upstream(lambda r: httpx2.Response(200, headers={"cache-control": "no-store"}, content=b"body"))
    client = await client_for(upstream, rfc=False)
    await client.get(URL, extensions={"caching": {"rfc": True}})
    await client.get(URL, extensions={"caching": {"rfc": True}})
    assert len(upstream.requests) == 2


@pytest.mark.anyio
async def test_request_can_use_another_storage_which_the_transport_does_not_close():
    other = await new_storage()
    upstream = Upstream()
    transport = AsyncCacheTransport(upstream, storage=await new_storage(), rfc=False)
    client = httpx2.AsyncClient(transport=transport)
    await client.get(URL, extensions={"caching": {"storage": other}})
    await client.get(URL, extensions={"caching": {"storage": other}})
    assert len(upstream.requests) == 1
    await client.get(URL)
    assert len(upstream.requests) == 2
    await transport.aclose()
    assert len(await other.get_entries(hashlib.sha256(f"GET {URL}".encode()).hexdigest())) == 1


@pytest.mark.anyio
async def test_client_rfc_argument_reaches_the_transport(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    async with AsyncCacheClient(trust_env=False) as client:
        assert client._transport.config["rfc"] is False  # type: ignore[attr-defined]
    async with AsyncCacheClient(trust_env=False, rfc=True) as client:
        assert client._transport.config["rfc"] is True  # type: ignore[attr-defined]


# rfc as CacheOptions


@pytest.mark.anyio
async def test_empty_options_still_mean_rfc_on():
    upstream = Upstream(lambda r: httpx2.Response(200, headers={"cache-control": "no-store"}, content=b"body"))
    client = await client_for(upstream, rfc={})
    await client.get(URL)
    await client.get(URL)
    assert len(upstream.requests) == 2


@pytest.mark.anyio
async def test_shared_option_controls_private_responses():
    def private(r):
        return httpx2.Response(200, headers={"cache-control": "private, max-age=100", "date": date_at(0)}, content=b"x")

    shared_upstream = Upstream(private)
    client = await client_for(shared_upstream, rfc=True)
    with at(0):
        await client.get(URL)
        await client.get(URL)
    assert len(shared_upstream.requests) == 2

    private_upstream = Upstream(private)
    client = await client_for(private_upstream, rfc={"shared": False})
    with at(0):
        await client.get(URL)
        await client.get(URL)
    assert len(private_upstream.requests) == 1


@pytest.mark.anyio
async def test_allow_stale_option_serves_stale_without_asking():
    def stale(r):
        return httpx2.Response(200, headers={"cache-control": "max-age=10", "date": date_at(0)}, content=b"x")

    upstream = Upstream(stale)
    client = await client_for(upstream, rfc={"allow_stale": True})
    with at(0):
        await client.get(URL)
    with at(100):
        await client.get(URL)
    assert len(upstream.requests) == 1

    upstream = Upstream(stale)
    client = await client_for(upstream, rfc=True)
    with at(0):
        await client.get(URL)
    with at(100):
        await client.get(URL)
    assert len(upstream.requests) == 2


@pytest.mark.anyio
async def test_supported_methods_option_decides_what_is_stored():
    def ok(r):
        return httpx2.Response(200, headers={"cache-control": "max-age=100", "date": date_at(0)}, content=b"x")

    upstream = Upstream(ok)
    client = await client_for(upstream, rfc=True)
    with at(0):
        await client.post(URL, content=b"a")
        await client.post(URL, content=b"a")
    assert len(upstream.requests) == 2

    upstream = Upstream(ok)
    storage = await new_storage()
    transport = AsyncCacheTransport(upstream, storage=storage, rfc={"supported_methods": ["GET", "HEAD", "POST"]})
    client = httpx2.AsyncClient(transport=transport)
    key = hashlib.sha256(f"RFC {URL}".encode()).hexdigest()
    with at(0):
        await client.post(URL, content=b"a")
        assert len(await storage.get_entries(key)) == 1  # stored
        await client.post(URL, content=b"a")
    assert len(upstream.requests) == 2  # but unsafe methods always reach the server


@pytest.mark.anyio
async def test_rfc_mode_unsafe_request_invalidates_the_entries_of_its_url():
    upstream = Upstream(
        lambda r: httpx2.Response(200, headers={"cache-control": "max-age=100", "date": date_at(0)}, content=b"x")
    )
    client = await client_for(upstream, rfc=True)
    with at(0):
        await client.get(URL)
        await client.get(URL)
        assert len(upstream.requests) == 1

        await client.post(URL, content=b"a")
        await client.get(URL)
    assert [r.method for r in upstream.requests] == ["GET", "POST", "GET"]


@pytest.mark.anyio
async def test_rfc_mode_failed_unsafe_request_keeps_the_entries():
    def respond(r):
        if r.method == "POST":
            return httpx2.Response(500)
        return httpx2.Response(200, headers={"cache-control": "max-age=100", "date": date_at(0)}, content=b"x")

    upstream = Upstream(respond)
    client = await client_for(upstream, rfc=True)
    with at(0):
        await client.get(URL)
        await client.post(URL, content=b"a")
        await client.get(URL)
    assert [r.method for r in upstream.requests] == ["GET", "POST"]


@pytest.mark.anyio
async def test_rfc_mode_does_not_use_the_key_left_in_redis_by_1x():
    redis_client = fakeredis.aioredis.FakeRedis()
    await redis_client.sadd(f"hishel:idx:{hashlib.sha256(URL.encode()).hexdigest()}", "old")
    transport = AsyncCacheTransport(Upstream(), storage=AsyncRedisStorage(redis_client), rfc=True)
    client = httpx2.AsyncClient(transport=transport)

    assert (await client.get(URL)).status_code == 200


@pytest.mark.anyio
@pytest.mark.parametrize("rfc", [False, True])
async def test_cache_outage_still_reaches_the_server(rfc):
    storage = await new_storage("redis")

    async def broken(*args, **kwargs):
        raise RedisError("down")

    storage._client.zrangebyscore = broken
    storage._client.set = broken
    upstream = Upstream()
    client = httpx2.AsyncClient(transport=AsyncCacheTransport(upstream, storage=storage, rfc=rfc))

    assert (await client.get(URL)).content == b"body"
    assert len(upstream.requests) == 1


@pytest.mark.anyio
async def test_unsafe_request_still_succeeds_when_the_database_is_locked(tmp_path):
    path = tmp_path / "cache.db"
    storage = AsyncSqliteStorage(database_path=path)
    upstream = Upstream(
        lambda r: httpx2.Response(200, headers={"cache-control": "max-age=100", "date": date_at(0)}, content=b"x")
    )
    client = httpx2.AsyncClient(transport=AsyncCacheTransport(upstream, storage=storage, rfc=True))
    with at(0):
        await client.get(URL)
        connection = await storage._ensure_connection()
        await connection.execute("PRAGMA busy_timeout=1")

        blocker = sqlite3.connect(path, isolation_level=None)
        blocker.execute("BEGIN IMMEDIATE")
        response = await client.post(URL, content=b"a")
        blocker.close()

    assert response.status_code == 200
    assert [r.method for r in upstream.requests] == ["GET", "POST"]


@pytest.mark.anyio
async def test_unparsable_date_does_not_break_later_requests():
    upstream = Upstream(
        lambda r: httpx2.Response(
            200, headers={"cache-control": "max-age=100", "date": "Mon, 01 Jan 99999 00:00:00 GMT"}, content=b"x"
        )
    )
    client = await client_for(upstream, rfc=True)

    assert (await client.get(URL)).status_code == 200
    assert (await client.get(URL)).status_code == 200


@pytest.mark.anyio
async def test_request_can_pass_options():
    def private(r):
        return httpx2.Response(200, headers={"cache-control": "private, max-age=100", "date": date_at(0)}, content=b"x")

    upstream = Upstream(private)
    client = await client_for(upstream, rfc=True)
    extensions = {"caching": {"rfc": {"shared": False}}}
    with at(0):
        await client.get(URL, extensions=extensions)
        await client.get(URL, extensions=extensions)
    assert len(upstream.requests) == 1


@pytest.mark.anyio
async def test_client_accepts_options(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    async with AsyncCacheClient(trust_env=False, rfc={"shared": False}) as client:
        assert client._transport.config["rfc"] == {"shared": False}  # type: ignore[attr-defined]


# The original request is what gets sent


@pytest.mark.anyio
async def test_rfc_sends_the_original_request_object():
    upstream = Upstream()
    client = await client_for(upstream, rfc=True)
    request = client.build_request("GET", URL)
    await client.send(request)
    assert upstream.requests[0] is request


@pytest.mark.anyio
async def test_rfc_keeps_transfer_encoding_of_a_streamed_upload():
    async def body() -> AsyncIterator[bytes]:
        yield b"a"
        yield b"b"

    upstream = Upstream()
    client = await client_for(upstream, rfc=True)
    await client.post(URL, content=body())
    assert upstream.requests[0].headers["transfer-encoding"] == "chunked"
    assert upstream.requests[0].content == b"ab"


@pytest.mark.anyio
async def test_rfc_keeps_header_name_casing_and_order():
    upstream = Upstream()
    client = await client_for(upstream, rfc=True)
    await client.get(URL, headers=[("X-Custom-Name", "1"), ("X-Custom-Name", "2")])
    raw = upstream.requests[0].headers.raw
    assert raw.count((b"X-Custom-Name", b"1")) == 1
    assert raw.count((b"X-Custom-Name", b"2")) == 1


@pytest.mark.anyio
async def test_rfc_revalidation_adds_conditions_only_while_sending():
    seen: dict[str, Any] = {}

    def handler(request):
        if not seen:
            seen["first"] = True
            return httpx2.Response(
                200,
                headers={"cache-control": "max-age=10", "etag": '"v1"', "date": date_at(0)},
                stream=TrackedStream([b"x"]),
            )
        seen["if_none_match"] = request.headers.get("if-none-match")
        seen["raw"] = request.headers.raw
        seen["request"] = request
        return httpx2.Response(304, headers={"etag": '"v1"', "cache-control": "max-age=10", "date": date_at(100)})

    client = await client_for(Upstream(handler), rfc=True)
    with at(0):
        await client.get(URL)
    request = client.build_request("GET", URL, headers={"X-Custom-Name": "1"})
    with at(100):
        response = await client.send(request)
    assert seen["if_none_match"] == '"v1"'
    assert seen["request"] is request
    assert (b"X-Custom-Name", b"1") in seen["raw"]
    assert "if-none-match" not in request.headers
    assert "if-none-match" not in response.request.headers


@pytest.mark.anyio
async def test_rfc_request_headers_are_restored_when_sending_fails():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx2.Response(
                200,
                headers={"cache-control": "max-age=10", "etag": '"v1"', "date": date_at(0)},
                stream=TrackedStream([b"x"]),
            )
        raise httpx2.ConnectError("down")

    client = await client_for(Upstream(handler), rfc=True)
    with at(0):
        await client.get(URL)
    request = client.build_request("GET", URL)
    with at(100), pytest.raises(httpx2.ConnectError):
        await client.send(request)
    assert "if-none-match" not in request.headers


@pytest.mark.anyio
async def test_rfc_same_request_object_can_be_sent_again_after_revalidation():
    answers = iter(
        [
            httpx2.Response(
                200,
                headers={"cache-control": "max-age=10", "etag": '"v1"', "date": date_at(0)},
                stream=TrackedStream([b"x"]),
            ),
            httpx2.Response(304, headers={"etag": '"v1"', "cache-control": "max-age=10", "date": date_at(100)}),
            httpx2.Response(304, headers={"etag": '"v1"', "cache-control": "max-age=10", "date": date_at(200)}),
        ]
    )
    upstream = Upstream(lambda r: next(answers))
    client = await client_for(upstream, rfc=True)
    request = client.build_request("GET", URL)
    with at(0):
        await client.send(request)
    with at(100):
        assert (await client.send(request)).content == b"x"
    with at(200):
        assert (await client.send(request)).content == b"x"
    assert len(upstream.requests) == 3


@pytest.mark.anyio
async def test_rfc_revalidation_overrides_conditions_the_caller_set_only_while_sending():
    answers = iter(
        [
            httpx2.Response(
                200,
                headers={"cache-control": "max-age=10", "etag": '"v1"', "date": date_at(0)},
                stream=TrackedStream([b"x"]),
            ),
            httpx2.Response(304, headers={"etag": '"v1"', "cache-control": "max-age=10", "date": date_at(100)}),
        ]
    )
    upstream = Upstream(lambda r: next(answers))
    client = await client_for(upstream, rfc=True)
    with at(0):
        await client.get(URL)
    request = client.build_request("GET", URL, headers={"If-None-Match": '"mine"'})
    with at(100):
        await client.send(request)
    assert upstream.sent_headers[1]["if-none-match"] == '"v1"'
    assert request.headers["if-none-match"] == '"mine"'


DUPLICATES = [
    ("X-Dup", "1"),
    ("X-Other", "a"),
    ("x-dup", "2, with comma"),
    ("Cookie", "a=1"),
    ("Cookie", "b=2"),
]


def stale_with_etag(etag='"v1"'):
    answers = iter(
        [
            httpx2.Response(
                200,
                headers={"cache-control": "max-age=10", "etag": etag, "date": date_at(0)},
                stream=TrackedStream([b"x"]),
            ),
            httpx2.Response(304, headers={"etag": etag, "cache-control": "max-age=10", "date": date_at(100)}),
        ]
    )
    return Upstream(lambda r: next(answers))


@pytest.mark.anyio
async def test_rfc_miss_sends_raw_headers_exactly_as_built():
    upstream = Upstream()
    client = await client_for(upstream, rfc=True)
    request = client.build_request("GET", URL, headers=DUPLICATES)
    raw = list(request.headers.raw)
    await client.send(request)
    assert upstream.sent_headers[0].raw == raw
    assert request.headers.raw == raw


@pytest.mark.anyio
async def test_rfc_revalidation_only_appends_to_raw_headers():
    upstream = stale_with_etag()
    client = await client_for(upstream, rfc=True)
    with at(0):
        await client.get(URL)
    request = client.build_request("GET", URL, headers=DUPLICATES)
    raw = list(request.headers.raw)
    with at(100):
        await client.send(request)
    assert upstream.sent_headers[1].raw == [*raw, (b"if-none-match", b'"v1"')]
    assert request.headers.raw == raw


@pytest.mark.anyio
async def test_rfc_revalidation_replaces_every_copy_of_a_caller_condition():
    upstream = stale_with_etag()
    client = await client_for(upstream, rfc=True)
    with at(0):
        await client.get(URL)
    request = client.build_request(
        "GET", URL, headers=[("If-None-Match", '"a"'), ("X-Keep", "1"), ("if-none-match", '"b"')]
    )
    raw = list(request.headers.raw)
    with at(100):
        await client.send(request)
    sent = upstream.sent_headers[1]
    assert sent.get_list("if-none-match") == ['"v1"']
    assert sent.get_list("x-keep") == ["1"]
    assert request.headers.raw == raw


@pytest.mark.anyio
async def test_rfc_revalidation_with_a_non_ascii_etag_does_not_fail_the_request():
    etag = '"é"'
    upstream = Upstream()
    answers = iter(
        [
            httpx2.Response(
                200,
                headers=[(b"cache-control", b"max-age=10"), (b"etag", etag.encode()), (b"date", date_at(0).encode())],
                stream=TrackedStream([b"x"]),
            ),
            httpx2.Response(304, headers=[(b"etag", etag.encode()), (b"date", date_at(100).encode())]),
        ]
    )
    upstream = Upstream(lambda r: next(answers))
    client = await client_for(upstream, rfc=True)
    with at(0):
        await client.get(URL)
    with at(100):
        assert (await client.get(URL)).content == b"x"
    assert (b"if-none-match", etag.encode()) in upstream.sent_headers[1].raw


@pytest.mark.anyio
@pytest.mark.parametrize("rfc", [True, False])
@pytest.mark.parametrize("raw_value, text", [("é".encode(), "é"), ("é".encode("latin-1"), "é")], ids=["utf8", "latin1"])
async def test_non_ascii_response_headers_survive_miss_and_hit(rfc, raw_value, text):
    upstream = Upstream(
        lambda r: httpx2.Response(
            200,
            headers=[(b"x-name", raw_value), (b"cache-control", b"max-age=100"), (b"date", date_at(0).encode())],
            stream=TrackedStream([b"x"]),
        )
    )
    client = await client_for(upstream, rfc=rfc)
    with at(0):
        first = await client.get(URL)
        second = await client.get(URL)
    assert first.headers["x-name"] == second.headers["x-name"] == text
    assert first.content == second.content == b"x"
    assert len(upstream.requests) == 1


@pytest.mark.anyio
async def test_rfc_is_off_by_default():
    upstream = Upstream(lambda r: httpx2.Response(200, headers={"cache-control": "no-store"}, content=b"body"))
    client = httpx2.AsyncClient(transport=AsyncCacheTransport(upstream, storage=await new_storage()))
    await client.get(URL)
    await client.get(URL)
    assert len(upstream.requests) == 1


@pytest.mark.anyio
async def test_304_does_not_change_the_stored_content_length():
    answers = iter(
        [
            httpx2.Response(
                200,
                headers={"cache-control": "max-age=10", "etag": '"v1"', "content-length": "5", "date": date_at(0)},
                stream=TrackedStream([b"hello"]),
            ),
            httpx2.Response(
                304,
                headers={"cache-control": "max-age=10", "etag": '"v1"', "content-length": "0", "date": date_at(100)},
            ),
        ]
    )
    client = await client_for(Upstream(lambda r: next(answers)), rfc=True)
    with at(0):
        await client.get(URL)
    with at(100):
        response = await client.get(URL)
    assert response.content == b"hello"
    assert response.headers["content-length"] == "5"
    with at(105):
        again = await client.get(URL)
    assert again.content == b"hello"
    assert again.headers["content-length"] == "5"


@pytest.mark.anyio
@pytest.mark.parametrize("value", ["garbage", "bytes=0-10", "bytes=0-1,5-6", "bytes=a-b"])
async def test_rfc_range_requests_go_to_the_server_whatever_their_form(value):
    upstream = Upstream(lambda r: fresh())
    client = await client_for(upstream, rfc=True)
    with at(0):
        await client.get(URL)
        response = await client.get(URL, headers={"range": value})
    assert response.status_code == 200
    assert len(upstream.requests) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["sqlite", "redis"])
@pytest.mark.parametrize("rfc", [False, True])
async def test_ttl_extension_overrides_the_storage_default(kind, rfc):
    upstream = Upstream(lambda r: fresh())
    client = await client_for(upstream, kind, rfc=rfc, default_ttl=1000)
    extensions = {"caching": {"ttl": 10}}
    with at(0):
        await client.get(URL, extensions=extensions)
    with at(5):
        await client.get(URL)
    assert len(upstream.requests) == 1
    with at(20):
        await client.get(URL)
    assert len(upstream.requests) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["sqlite", "redis"])
@pytest.mark.parametrize("rfc", [False, True])
async def test_tti_extension_expires_an_entry_that_is_not_used(kind, rfc):
    upstream = Upstream(lambda r: fresh())
    client = await client_for(upstream, kind, rfc=rfc, default_ttl=1000)
    extensions = {"caching": {"tti": 10}}
    with at(0):
        await client.get(URL, extensions=extensions)
    with at(8):
        await client.get(URL)
    with at(16):
        await client.get(URL)
    assert len(upstream.requests) == 1
    with at(40):
        await client.get(URL)
    assert len(upstream.requests) == 2


@pytest.mark.anyio
async def test_ttl_extension_does_not_change_an_entry_already_stored():
    upstream = Upstream(lambda r: fresh())
    client = await client_for(upstream)
    with at(0):
        await client.get(URL)
    with at(1):
        await client.get(URL, extensions={"caching": {"ttl": 1}})
    with at(500):
        await client.get(URL)
    assert len(upstream.requests) == 1


@pytest.mark.anyio
async def test_other_overrides_leave_the_storage_ttl_in_place():
    upstream = Upstream(lambda r: fresh())
    client = await client_for(upstream, default_ttl=10)
    with at(0):
        await client.get(URL, extensions={"caching": {"rfc": False}})
    with at(20):
        await client.get(URL)
    assert len(upstream.requests) == 2


def with_key(key):
    return {"caching": {"key": key}}


@pytest.mark.anyio
@pytest.mark.parametrize("kind", ["sqlite", "redis"])
@pytest.mark.parametrize("key", ["my-key", "ключ"])
async def test_key_extension_replaces_the_key_for_lookup_and_store(kind, key):
    upstream = Upstream(lambda r: fresh(str(r.url).encode()))
    client = await client_for(upstream, kind)

    await client.get(URL, extensions=with_key(key))
    response = await client.get("https://y/", extensions=with_key(key))
    assert len(upstream.requests) == 1
    assert response.content == URL.encode()

    # Stored under the key given, so not under the usual one.
    await client.get(URL)
    assert len(upstream.requests) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("rfc", [False, True])
async def test_different_keys_keep_one_url_apart(rfc):
    upstream = Upstream(lambda r: fresh())
    client = await client_for(upstream, rfc=rfc)

    with at(0):
        for _ in range(2):
            await client.get(URL, extensions=with_key("a"))
            await client.get(URL, extensions=with_key("b"))

    assert len(upstream.requests) == 2


@pytest.mark.anyio
async def test_rfc_mode_does_not_serve_another_url_stored_under_the_key():
    upstream = Upstream(lambda r: fresh(str(r.url).encode()))
    client = await client_for(upstream, rfc=True)

    with at(0):
        await client.get(URL, extensions=with_key("k"))
        response = await client.get("https://y/", extensions=with_key("k"))

        assert len(upstream.requests) == 2
        assert response.content == b"https://y/"
        assert (await client.get(URL, extensions=with_key("k"))).content == URL.encode()
        assert len(upstream.requests) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("rfc", [False, True])
async def test_key_extension_does_not_make_post_cacheable(rfc):
    upstream = Upstream(lambda r: fresh())
    client = await client_for(upstream, rfc=rfc)

    await client.post(URL, extensions=with_key("k"))
    await client.post(URL, extensions=with_key("k"))

    assert len(upstream.requests) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("rfc", [False, True])
async def test_get_and_head_sharing_a_key_do_not_answer_each_other(rfc):
    upstream = Upstream(lambda r: fresh())
    client = await client_for(upstream, rfc=rfc)

    with at(0):
        for _ in range(2):
            assert (await client.get(URL, extensions=with_key("k"))).content == b"body"
            await client.head(URL, extensions=with_key("k"))

    assert [request.method for request in upstream.requests] == ["GET", "HEAD"]
