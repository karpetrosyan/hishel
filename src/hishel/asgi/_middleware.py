from __future__ import annotations

import hashlib
import typing as t
from urllib.parse import quote

from hishel import AsyncBaseStorage, AsyncSqliteStorage, CacheOptions, Headers, Request, Response
from hishel._async_rfc import handle_request_with_rfc
from hishel._utils import generate_http_date, make_async_iterator

_Scope = t.MutableMapping[str, t.Any]
_Receive = t.Callable[[], t.Awaitable[t.MutableMapping[str, t.Any]]]
_Send = t.Callable[[t.MutableMapping[str, t.Any]], t.Awaitable[None]]
_ASGIApp = t.Callable[[_Scope, _Receive, _Send], t.Awaitable[None]]

CACHEABLE_METHODS = frozenset({"GET", "HEAD"})

# These let an app send a body from a file behind the middleware's back, which
# would leave it with an empty body to store.
_BODY_BYPASSING_EXTENSIONS = frozenset({"http.response.pathsend", "http.response.zerocopysend"})


def _request_url(scope: _Scope) -> str:
    # The Host header, so that different hosts served by one app don't share entries.
    host = dict(scope["headers"]).get(b"host", b"").decode("latin-1")
    if not host:
        server_host, server_port = scope.get("server") or ("localhost", None)
        host = f"{server_host}:{server_port}" if server_port is not None else server_host

    # The raw path, so that "/a%2Fb" and "/a/b" don't share entries.
    raw_path = scope.get("raw_path")
    path = raw_path.decode("latin-1") if raw_path else quote(scope["path"])
    query = scope.get("query_string", b"").decode("latin-1")
    return f"{scope.get('scheme', 'http')}://{host}{path}" + (f"?{query}" if query else "")


def _headers_to_internal(headers: t.Iterable[tuple[bytes, bytes]]) -> Headers:
    grouped: dict[str, list[str]] = {}
    for key, value in headers:
        grouped.setdefault(key.decode("latin-1").lower(), []).append(value.decode("latin-1"))
    # The body is stored without its transfer encoding.
    grouped.pop("transfer-encoding", None)
    return Headers(grouped)


def _scope_with_changes(scope: _Scope, original: Headers, wanted: Headers) -> _Scope:
    """
    The scope to call the app with: anything that differs from ``original`` is
    applied to its raw headers, leaving every other pair as it was.
    """
    changed = {
        key.encode("latin-1"): value.encode("latin-1") for key, value in wanted.items() if original.get(key) != value
    }
    kept = [(key, value) for key, value in scope["headers"] if key.lower() not in changed]
    extensions = {
        key: value for key, value in scope.get("extensions", {}).items() if key not in _BODY_BYPASSING_EXTENSIONS
    }
    return {**scope, "headers": [*kept, *changed.items()], "extensions": extensions}


class ASGICacheMiddleware:
    """
    Caches the responses of an ASGI app. By default follows RFC 9111, because a
    server usually serves many users and its app says what can be cached. With
    ``rfc=False``, caches successful GET and HEAD responses by method and URL,
    ignoring HTTP caching headers, until the storage's TTL or TTI expires them.

    Each response is read fully before it is sent, so endpoints that never finish
    responding, such as server-sent events, can't be served through this.
    """

    def __init__(
        self,
        app: _ASGIApp,
        storage: AsyncBaseStorage | None = None,
        rfc: bool | CacheOptions = True,
    ) -> None:
        self.app = app
        self.storage = storage or AsyncSqliteStorage()
        self.rfc = rfc

    async def __call__(self, scope: _Scope, receive: _Receive, send: _Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(
            method=scope["method"], url=_request_url(scope), headers=_headers_to_internal(scope["headers"])
        )
        # In RFC mode, all methods share a key, so that an unsafe request finds the entries it invalidates.
        # The prefix keeps it apart from the key 1.x used, which Redis may still hold in another format.
        identity = f"RFC {request.url}" if self.rfc is not False else f"{request.method} {request.url}"
        key = hashlib.sha256(identity.encode()).hexdigest()

        async def call_app(internal_request: Request) -> Response:
            # The state machine only changes a request to add revalidation headers.
            return await self._call_app(_scope_with_changes(scope, request.headers, internal_request.headers), receive)

        if self.rfc is False:
            if request.method not in CACHEABLE_METHODS:
                await self.app(scope, receive, send)
                return
            response = await self._respond_without_rfc(request, call_app, key)
        else:
            options = CacheOptions() if self.rfc is True else self.rfc
            response = await handle_request_with_rfc(request, call_app, self.storage, key, options)

        await self._send_response(response, send)

    async def _respond_without_rfc(
        self,
        request: Request,
        call_app: t.Callable[[Request], t.Awaitable[Response]],
        key: str,
    ) -> Response:
        entries = await self.storage.get_entries(key)
        if entries:
            return entries[0].response

        response = await call_app(request)
        # A 206 only holds part of the body, so it can't answer later requests.
        if not 200 <= response.status_code < 300 or response.status_code == 206:
            return response

        entry = await self.storage.create_entry(request, response, key)
        return entry.response

    async def _call_app(self, scope: _Scope, receive: _Receive) -> Response:
        status: int | None = None
        headers: list[tuple[bytes, bytes]] = []
        chunks: list[bytes] = []

        async def buffer(message: t.MutableMapping[str, t.Any]) -> None:
            nonlocal status, headers
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = message.get("headers", [])
            elif message["type"] == "http.response.body":
                chunks.append(message.get("body", b""))

        await self.app(scope, receive, buffer)
        if status is None:
            raise RuntimeError("The ASGI app returned without starting a response.")

        internal_headers = _headers_to_internal(headers)
        if "date" not in internal_headers:
            # Freshness is calculated from this.
            internal_headers["date"] = generate_http_date()
        return Response(status_code=status, headers=internal_headers, stream=make_async_iterator(chunks))

    async def _send_response(self, response: Response, send: _Send) -> None:
        assert isinstance(response.stream, t.AsyncIterator)
        await send(
            {
                "type": "http.response.start",
                "status": response.status_code,
                "headers": [
                    (key.encode("latin-1"), value.encode("latin-1"))
                    for key in response.headers
                    for value in response.headers.get_list(key) or []
                ],
            }
        )
        async for chunk in response.stream:
            await send({"type": "http.response.body", "body": chunk, "more_body": True})
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def aclose(self) -> None:
        await self.storage.close()
