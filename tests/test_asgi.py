import tempfile
from email.utils import formatdate
from pathlib import Path

import anysqlite
import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from starlette.testclient import TestClient

from hishel import AsyncSqliteStorage, CacheOptions
from hishel.asgi import ASGICacheMiddleware
from hishel.fastapi import cache


@pytest.fixture
def anyio_backend():
    return "asyncio"


class App:
    """A small ASGI app that records the scopes it was called with."""

    def __init__(self, status=200, headers=(), body=b"body", chunks=None):
        self.calls = []
        self.status = status
        self.headers = list(headers)
        self.chunks = chunks if chunks is not None else [body]

    async def __call__(self, scope, receive, send):
        self.calls.append(scope)
        if scope["type"] == "http":
            message = await receive()
            scope["received"] = message.get("body", b"")
        await send({"type": "http.response.start", "status": self.status, "headers": self.headers})
        for chunk in self.chunks:
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})


async def client_for(app, **kwargs):
    storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(ASGICacheMiddleware(app, storage=storage, **kwargs)),
        base_url="http://testserver",
    )


CACHEABLE = [(b"cache-control", b"public, max-age=60")]


@pytest.mark.anyio
async def test_rfc_mode_is_the_default_and_respects_the_app():
    app = App(headers=CACHEABLE)
    client = await client_for(app)

    assert (await client.get("/")).content == b"body"
    assert (await client.get("/")).content == b"body"
    assert len(app.calls) == 1

    no_store = App(headers=[(b"cache-control", b"no-store")])
    client = await client_for(no_store)
    await client.get("/")
    await client.get("/")
    assert len(no_store.calls) == 2


@pytest.mark.anyio
async def test_default_mode_ignores_caching_headers():
    app = App(headers=[(b"cache-control", b"no-store")])
    client = await client_for(app, rfc=False)

    await client.get("/")
    assert (await client.get("/")).content == b"body"

    assert len(app.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("status", [404, 500, 206])
async def test_default_mode_does_not_store_other_statuses(status):
    app = App(status=status)
    client = await client_for(app, rfc=False)

    assert (await client.get("/")).status_code == status
    assert (await client.get("/")).status_code == status

    assert len(app.calls) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("rfc", [False, True])
async def test_post_reaches_the_app_with_its_body(rfc):
    app = App(headers=CACHEABLE)
    client = await client_for(app, rfc=rfc)

    await client.post("/", content=b"sent")
    await client.post("/", content=b"sent")

    assert len(app.calls) == 2
    assert app.calls[0]["received"] == b"sent"


@pytest.mark.anyio
async def test_rfc_mode_post_invalidates_the_entries_of_its_url():
    app = App(headers=CACHEABLE)
    client = await client_for(app)

    await client.get("/")
    await client.get("/")
    assert len(app.calls) == 1

    await client.post("/", content=b"sent")
    await client.get("/")

    assert [call["method"] for call in app.calls] == ["GET", "POST", "GET"]


@pytest.mark.anyio
async def test_non_http_scopes_pass_through():
    calls = []

    async def app(scope, receive, send):
        calls.append(scope["type"])

    middleware = ASGICacheMiddleware(app, storage=AsyncSqliteStorage(connection=await anysqlite.connect(":memory:")))
    await middleware({"type": "lifespan"}, None, None)  # type: ignore[arg-type]
    await middleware({"type": "websocket"}, None, None)  # type: ignore[arg-type]

    assert calls == ["lifespan", "websocket"]


@pytest.mark.anyio
@pytest.mark.parametrize(
    "first, second",
    [
        ("/a", "/b"),
        ("/a?x=1", "/a?x=2"),
        # Decoded, these are the same path.
        ("/a%2Fb", "/a/b"),
    ],
)
async def test_urls_have_separate_entries(first, second):
    app = App(headers=CACHEABLE)
    client = await client_for(app)

    await client.get(first)
    await client.get(second)
    await client.get(first)

    assert len(app.calls) == 2


@pytest.mark.anyio
async def test_hosts_have_separate_entries():
    app = App(headers=CACHEABLE)
    client = await client_for(app)

    await client.get("/", headers={"Host": "a.example.com"})
    await client.get("/", headers={"Host": "b.example.com"})
    await client.get("/", headers={"Host": "a.example.com"})

    assert len(app.calls) == 2


@pytest.mark.anyio
@pytest.mark.parametrize("rfc", [False, True])
async def test_body_chunks_are_kept_on_a_miss_and_on_a_hit(rfc):
    app = App(headers=CACHEABLE, chunks=[b"a", b"", b"b"])
    client = await client_for(app, rfc=rfc)

    assert (await client.get("/")).content == b"ab"
    assert (await client.get("/")).content == b"ab"
    assert len(app.calls) == 1


@pytest.mark.anyio
@pytest.mark.parametrize("rfc", [False, True])
async def test_repeated_set_cookie_values_stay_apart(rfc):
    pairs = [(b"set-cookie", b"a=1"), (b"set-cookie", b"b=2"), (b"cache-control", b"public, max-age=60")]
    app = App(headers=pairs)
    client = await client_for(app, rfc=CacheOptions(shared=False) if rfc else False)

    for _ in range(2):
        response = await client.get("/")
        assert response.headers.get_list("set-cookie") == ["a=1", "b=2"]
    assert len(app.calls) == 1


@pytest.mark.anyio
async def test_a_missing_date_is_added_so_freshness_can_be_calculated():
    client = await client_for(App(headers=CACHEABLE))

    assert "date" in (await client.get("/")).headers


@pytest.mark.anyio
async def test_a_date_from_the_app_is_kept():
    date = "Thu, 01 Jan 2026 00:00:00 GMT"
    client = await client_for(App(headers=[(b"date", date.encode())]))

    assert (await client.get("/")).headers.get_list("date") == [date]


@pytest.mark.anyio
async def test_revalidation_adds_headers_for_the_app_and_serves_the_cached_body():
    calls = []

    async def app(scope, receive, send):
        calls.append(dict(scope["headers"]))
        headers = [
            (b"etag", b'"v1"'),
            (b"cache-control", b"public, max-age=0"),
            (b"date", formatdate(usegmt=True).encode()),
        ]
        revalidating = dict(scope["headers"]).get(b"if-none-match") == b'"v1"'
        await send({"type": "http.response.start", "status": 304 if revalidating else 200, "headers": headers})
        await send({"type": "http.response.body", "body": b"" if revalidating else b"body", "more_body": False})

    client = await client_for(app)

    await client.get("/", headers={"X-Kept": "yes"})
    response = await client.get("/", headers={"X-Kept": "yes"})

    assert response.status_code == 200
    assert response.content == b"body"
    assert calls[1][b"if-none-match"] == b'"v1"'
    assert calls[1][b"x-kept"] == b"yes"


@pytest.mark.anyio
async def test_an_app_that_never_responds_raises():
    async def app(scope, receive, send):
        pass

    with pytest.raises(RuntimeError, match="without starting a response"):
        await (await client_for(app)).get("/")


@pytest.mark.anyio
async def test_app_errors_propagate_and_store_nothing():
    calls = []

    async def app(scope, receive, send):
        calls.append(scope)
        raise ValueError("boom")

    client = await client_for(app)
    for _ in range(2):
        with pytest.raises(ValueError, match="boom"):
            await client.get("/")
    assert len(calls) == 2


@pytest.mark.anyio
async def test_a_file_served_with_pathsend_is_stored_with_its_body():
    # A server advertising this extension would otherwise leave the middleware with an empty body.
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "file.txt"
        path.write_bytes(b"from a file")

        fastapi_app = FastAPI()

        @fastapi_app.get("/file", dependencies=[cache(max_age=60, public=True)])
        async def get_file():
            return FileResponse(path)

        storage = AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))
        middleware = ASGICacheMiddleware(fastapi_app, storage=storage)

        messages = []

        async def send(message):
            messages.append(message)

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        scope = {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/file",
            "raw_path": b"/file",
            "query_string": b"",
            "root_path": "",
            "headers": [(b"host", b"testserver")],
            "server": ("testserver", 80),
            "extensions": {"http.response.pathsend": {}},
        }
        await middleware(scope, receive, send)

    assert b"".join(message.get("body", b"") for message in messages) == b"from a file"


@pytest.mark.anyio
async def test_fastapi_cache_dependency_sets_headers_the_middleware_follows():
    calls = []
    app = FastAPI()

    @app.get("/cached", dependencies=[cache(max_age=60, public=True)])
    async def cached():
        calls.append("cached")
        return {"value": len(calls)}

    @app.get("/uncached", dependencies=[cache(no_store=True)])
    async def uncached():
        calls.append("uncached")
        return {"value": len(calls)}

    client = await client_for(app)

    first = await client.get("/cached")
    second = await client.get("/cached")
    assert first.json() == second.json()
    assert calls == ["cached"]
    assert first.headers["cache-control"] == "max-age=60, public"
    assert "date" in first.headers

    await client.get("/uncached")
    await client.get("/uncached")
    assert calls == ["cached", "uncached", "uncached"]


def test_fastapi_cache_directives():
    app = FastAPI()

    @app.get(
        "/",
        dependencies=[
            cache(
                max_age=1,
                s_maxage=2,
                private=["Set-Cookie"],
                no_cache=["A", "B"],
                immutable=True,
                must_revalidate=True,
                stale_while_revalidate=3,
            )
        ],
    )
    async def index():
        return {}

    assert TestClient(app).get("/").headers["cache-control"] == (
        'max-age=1, s-maxage=2, stale-while-revalidate=3, private="Set-Cookie", '
        'no-cache="A, B", must-revalidate, immutable'
    )


def test_works_through_add_middleware_and_streaming_responses():
    calls = []
    app = FastAPI()
    storage = AsyncSqliteStorage(database_path=str(Path(tempfile.mkdtemp()) / "cache.db"))
    app.add_middleware(ASGICacheMiddleware, storage=storage, rfc=False)

    @app.get("/stream")
    async def stream():
        calls.append("stream")

        async def body():
            yield b"a"
            yield b"b"

        return StreamingResponse(body())

    with TestClient(app) as client:
        assert client.get("/stream").content == b"ab"
        assert client.get("/stream").content == b"ab"

    assert calls == ["stream"]
