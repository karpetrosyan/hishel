import gzip
import hashlib
import sqlite3
import threading
import time
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import requests
from time_machine import travel

from hishel import CacheOptions, SyncSqliteStorage
from hishel.requests import CacheAdapter


class Origin:
    """A real local server, because what matters here is how Requests and urllib3 treat a real response."""

    def __init__(self):
        self.requests: list[BaseHTTPRequestHandler] = []
        self.handler = lambda request: (200, {"Content-Type": "text/plain"}, b"body")
        origin = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def respond(self):
                length = int(self.headers.get("Content-Length") or 0)
                self.body = self.rfile.read(length)
                origin.requests.append(self)
                result = origin.handler(self)
                if result is None:
                    return  # The handler wrote the response itself.
                status, headers, body = result
                self.send_response(status)
                pairs = headers.items() if isinstance(headers, dict) else headers
                for key, value in pairs:
                    self.send_header(key, value)
                if not any(key.lower() == "content-length" for key, _ in pairs):
                    self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            do_GET = do_HEAD = do_POST = respond

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def hits(self):
        return len(self.requests)


@pytest.fixture
def origin():
    origin = Origin()
    yield origin
    origin.server.shutdown()
    origin.server.server_close()


def _key(method, url, rfc=False):
    identity = f"RFC {url}" if rfc else f"{method} {url}"
    return hashlib.sha256(identity.encode()).hexdigest()


def new_session(rfc=False, **kwargs):
    storage = SyncSqliteStorage(connection=sqlite3.connect(":memory:", check_same_thread=False), **kwargs)
    session = requests.Session()
    session.mount("http://", CacheAdapter(storage=storage, rfc=rfc))
    return session


def test_default_mode_ignores_caching_headers(origin):
    origin.handler = lambda request: (200, {"Cache-Control": "no-store"}, b"body")
    session = new_session()

    assert session.get(origin.url).content == b"body"
    assert session.get(origin.url).content == b"body"

    assert origin.hits == 1


@pytest.mark.parametrize("status", [404, 500, 206])
def test_default_mode_does_not_store_other_statuses(origin, status):
    origin.handler = lambda request: (status, {}, b"body")
    session = new_session()

    assert session.get(origin.url).status_code == status
    assert session.get(origin.url).status_code == status

    assert origin.hits == 2


def test_default_mode_does_not_cache_post(origin):
    session = new_session()

    assert session.post(origin.url, data=b"sent").content == b"body"
    session.post(origin.url, data=b"sent")

    assert origin.hits == 2
    assert origin.requests[0].body == b"sent"


def test_methods_and_urls_have_separate_entries(origin):
    session = new_session()

    session.get(origin.url + "a")
    session.get(origin.url + "b")
    session.head(origin.url + "a")
    session.get(origin.url + "a")

    assert origin.hits == 3


@pytest.mark.parametrize("rfc", [False, True])
def test_cached_head_response_keeps_its_content_length(origin, rfc):
    # A cached HEAD has a Content-Length and no body, which urllib3 would otherwise reject.
    origin.handler = lambda request: (200, {"Cache-Control": "max-age=60", "Content-Length": "4"}, b"body")
    session = new_session(rfc=rfc)

    session.head(origin.url)
    response = session.head(origin.url)

    assert origin.hits == 1
    assert response.headers["Content-Length"] == "4"
    assert response.content == b""


@pytest.mark.parametrize("rfc", [False, True])
def test_gzip_body_is_decoded_on_a_miss_and_on_a_hit(origin, rfc):
    compressed = gzip.compress(b"body")
    origin.handler = lambda request: (200, {"Content-Encoding": "gzip", "Cache-Control": "max-age=60"}, compressed)
    session = new_session(rfc=rfc)

    assert session.get(origin.url).content == b"body"
    response = session.get(origin.url)

    assert origin.hits == 1
    assert response.content == b"body"
    assert response.headers["Content-Encoding"] == "gzip"


@pytest.mark.parametrize("rfc", [False, True])
def test_chunked_response(origin, rfc):
    origin.handler = lambda request: (
        request.wfile.write(
            b"HTTP/1.1 200 OK\r\nCache-Control: max-age=60\r\nTransfer-Encoding: chunked\r\n\r\n4\r\nbody\r\n0\r\n\r\n"
        )
        and None
    )
    session = new_session(rfc=rfc)

    assert session.get(origin.url).content == b"body"
    response = session.get(origin.url)

    assert origin.hits == 1
    assert response.content == b"body"
    assert "Transfer-Encoding" not in response.headers


@pytest.mark.parametrize("rfc", [False, True])
def test_repeated_set_cookie_values_reach_the_session(origin, rfc):
    pairs = [("Set-Cookie", "a=1"), ("Set-Cookie", "b=2"), ("Cache-Control", "max-age=60")]
    origin.handler = lambda request: (200, pairs, b"body")
    session = new_session(rfc=rfc)

    response = session.get(origin.url)

    assert session.cookies.get_dict() == {"a": "1", "b": "2"}
    assert response.cookies.get_dict() == {"a": "1", "b": "2"}

    cached = session.get(origin.url)
    assert origin.hits == 1
    assert cached.raw.headers.getlist("Set-Cookie") == ["a=1", "b=2"]


def test_timeout_reaches_the_server(origin):
    def slow(request):
        time.sleep(0.5)
        return 200, {}, b"body"

    origin.handler = slow

    with pytest.raises(requests.exceptions.Timeout):
        new_session().get(origin.url, timeout=0.05)


def test_response_has_the_usual_attributes(origin):
    origin.handler = lambda request: (200, {"Content-Type": "text/plain; charset=utf-8"}, "héllo".encode())
    session = new_session()

    for _ in range(2):
        response = session.get(origin.url)
        assert response.text == "héllo"
        assert response.url == origin.url
        assert response.reason == "OK"
        assert response.encoding == "utf-8"
        assert response.request.url == origin.url
        assert response.ok
    assert origin.hits == 1


def test_streaming_a_response_fully_stores_it(origin):
    session = new_session()

    with session.get(origin.url, stream=True) as response:
        assert b"".join(response.iter_content(2)) == b"body"
    with session.get(origin.url, stream=True) as response:
        assert b"".join(response.iter_content(2)) == b"body"

    assert origin.hits == 1


def test_abandoning_a_stream_stores_nothing(origin):
    origin.handler = lambda request: (200, {}, b"x" * 300_000)
    session = new_session()

    with session.get(origin.url, stream=True) as response:
        next(response.iter_content(10))

    assert len(session.get(origin.url).content) == 300_000
    assert origin.hits == 2


@pytest.mark.parametrize(("post_status", "expected_hits"), [(200, 3), (500, 2)])
def test_rfc_mode_unsafe_request_invalidates_unless_it_failed(origin, post_status, expected_hits):
    def respond(request):
        if request.command == "POST":
            return (post_status, {}, b"")
        return (200, {"Cache-Control": "max-age=100"}, b"body")

    origin.handler = respond
    session = new_session(rfc=True)

    session.get(origin.url)
    session.post(origin.url)
    session.get(origin.url)

    assert origin.hits == expected_hits


def test_rfc_mode_respects_no_store(origin):
    origin.handler = lambda request: (200, {"Cache-Control": "no-store"}, b"body")
    session = new_session(rfc=True)

    session.get(origin.url)
    session.get(origin.url)

    assert origin.hits == 2


def test_rfc_mode_accepts_cache_options(origin):
    origin.handler = lambda request: (200, {"Cache-Control": "private, max-age=60"}, b"body")

    shared = new_session(rfc=True)
    shared.get(origin.url)
    shared.get(origin.url)
    assert origin.hits == 2

    private = new_session(rfc=CacheOptions(shared=False))
    private.get(origin.url)
    private.get(origin.url)
    assert origin.hits == 3


def test_rfc_mode_revalidates_and_serves_the_cached_body(origin):
    def handler(request):
        headers = {"ETag": '"v1"', "Cache-Control": "max-age=0", "Date": formatdate(usegmt=True)}
        if request.headers.get("If-None-Match") == '"v1"':
            return 304, {**headers, "Content-Length": "0"}, b""
        return 200, headers, b"body"

    origin.handler = handler
    session = new_session(rfc=True)

    assert session.get(origin.url, headers={"X-Kept": "yes"}).content == b"body"
    prepared_request = session.prepare_request(requests.Request("GET", origin.url, headers={"X-Kept": "yes"}))
    response = session.send(prepared_request)

    assert response.status_code == 200
    assert response.content == b"body"
    assert origin.hits == 2
    assert origin.requests[1].headers["If-None-Match"] == '"v1"'
    assert origin.requests[1].headers["X-Kept"] == "yes"
    assert "If-None-Match" not in prepared_request.headers
    # A third request still works, so the connection and the entry survived.
    assert session.get(origin.url, headers={"X-Kept": "yes"}).content == b"body"


def test_closing_a_session_with_one_adapter_mounted_twice(origin):
    adapter = CacheAdapter(storage=SyncSqliteStorage(connection=sqlite3.connect(":memory:", check_same_thread=False)))
    session = requests.Session()
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    session.get(origin.url)
    session.close()


def at(seconds):
    return travel(START + seconds, tick=False)


START = time.time()
FRESH = {"Cache-Control": "max-age=1000"}


@pytest.mark.parametrize("rfc", [False, True])
def test_ttl_header_overrides_the_storage_default(origin, rfc):
    origin.handler = lambda request: (200, FRESH, b"body")
    session = new_session(rfc=rfc, default_ttl=1000)

    with at(0):
        session.get(origin.url, headers={"X-Hishel-Ttl": "10"})
    with at(5):
        session.get(origin.url)
    assert origin.hits == 1
    with at(20):
        session.get(origin.url)
    assert origin.hits == 2


@pytest.mark.parametrize("rfc", [False, True])
def test_tti_header_expires_an_entry_that_is_not_used(origin, rfc):
    origin.handler = lambda request: (200, FRESH, b"body")
    session = new_session(rfc=rfc, default_ttl=1000)

    with at(0):
        session.get(origin.url, headers={"X-Hishel-Tti": "10"})
    with at(8):
        session.get(origin.url)
    with at(16):
        session.get(origin.url)
    assert origin.hits == 1
    with at(40):
        session.get(origin.url)
    assert origin.hits == 2


@pytest.mark.parametrize("value", ["1.5", b"1.5"])
def test_fractions_and_bytes_are_accepted(origin, value):
    session = new_session()

    with at(0):
        session.get(origin.url, headers={"X-Hishel-Ttl": value})
    with at(1):
        session.get(origin.url)
    assert origin.hits == 1
    with at(2):
        session.get(origin.url)
    assert origin.hits == 2


@pytest.mark.parametrize("rfc", [False, True])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_expiry_headers_do_not_reach_the_server_or_the_stored_request(origin, rfc, method):
    session = new_session(rfc=rfc)

    session.request(method, origin.url, headers={"X-Hishel-Ttl": "10", "X-Hishel-Tti": "10", "X-Kept": "yes"})

    assert "X-Hishel-Ttl" not in origin.requests[0].headers
    assert "X-Hishel-Tti" not in origin.requests[0].headers
    assert origin.requests[0].headers["X-Kept"] == "yes"
    for entry in session.get_adapter(origin.url).storage.get_entries(_key(method, origin.url, rfc)):
        assert "x-hishel-ttl" not in entry.request.headers


def test_the_callers_request_keeps_its_expiry_headers(origin):
    session = new_session()
    prepared = session.prepare_request(requests.Request("GET", origin.url, headers={"X-Hishel-Ttl": "10"}))

    session.send(prepared)

    assert prepared.headers["X-Hishel-Ttl"] == "10"


@pytest.mark.parametrize("name", ["X-Hishel-Ttl", "X-Hishel-Tti"])
@pytest.mark.parametrize("value", ["abc", "", "-1", "nan", "inf", "1h"])
def test_invalid_expiry_headers_raise_before_reaching_the_server(origin, name, value):
    session = new_session()

    with pytest.raises(ValueError, match=f"{name} must be a number of seconds"):
        session.get(origin.url, headers={name: value})

    assert origin.hits == 0


@pytest.mark.parametrize("value", ["my-key", b"my-key"])
def test_key_header_replaces_the_key_for_lookup_and_store(origin, value):
    origin.handler = lambda request: (200, FRESH, request.path.encode())
    session = new_session()

    session.get(origin.url + "a", headers={"X-Hishel-Key": value})
    response = session.get(origin.url + "b", headers={"X-Hishel-Key": value})
    assert origin.hits == 1
    assert response.content == b"/a"

    # Stored under the key given, so not under the usual one.
    session.get(origin.url + "a")
    assert origin.hits == 2


@pytest.mark.parametrize("rfc", [False, True])
def test_different_keys_keep_one_url_apart(origin, rfc):
    origin.handler = lambda request: (200, FRESH, b"body")
    session = new_session(rfc=rfc)

    for _ in range(2):
        session.get(origin.url, headers={"X-Hishel-Key": "a"})
        session.get(origin.url, headers={"X-Hishel-Key": "b"})

    assert origin.hits == 2


def test_rfc_mode_does_not_serve_another_url_stored_under_the_key(origin):
    origin.handler = lambda request: (200, FRESH, request.path.encode())
    session = new_session(rfc=True)

    session.get(origin.url + "a", headers={"X-Hishel-Key": "k"})
    response = session.get(origin.url + "b", headers={"X-Hishel-Key": "k"})

    assert origin.hits == 2
    assert response.content == b"/b"


@pytest.mark.parametrize("rfc", [False, True])
@pytest.mark.parametrize("method", ["GET", "POST"])
def test_key_header_does_not_reach_the_server_or_the_stored_request(origin, rfc, method):
    session = new_session(rfc=rfc)

    session.request(method, origin.url, headers={"X-Hishel-Key": "k", "X-Kept": "yes"})

    assert "X-Hishel-Key" not in origin.requests[0].headers
    assert origin.requests[0].headers["X-Kept"] == "yes"
    for entry in session.get_adapter(origin.url).storage.get_entries("k"):
        assert "x-hishel-key" not in entry.request.headers


@pytest.mark.parametrize("rfc", [False, True])
def test_key_header_does_not_make_post_cacheable(origin, rfc):
    origin.handler = lambda request: (200, FRESH, b"body")
    session = new_session(rfc=rfc)

    session.post(origin.url, headers={"X-Hishel-Key": "k"})
    session.post(origin.url, headers={"X-Hishel-Key": "k"})

    assert origin.hits == 2


def test_empty_key_header_raises_before_reaching_the_server(origin):
    with pytest.raises(ValueError, match="X-Hishel-Key must not be empty"):
        new_session().get(origin.url, headers={"X-Hishel-Key": ""})

    assert origin.hits == 0


@pytest.mark.parametrize("rfc", [False, True])
def test_get_and_head_sharing_a_key_do_not_answer_each_other(origin, rfc):
    origin.handler = lambda request: (200, FRESH, b"body")
    session = new_session(rfc=rfc)

    for _ in range(2):
        assert session.get(origin.url, headers={"X-Hishel-Key": "k"}).content == b"body"
        assert session.head(origin.url, headers={"X-Hishel-Key": "k"}).content == b""

    assert origin.hits == 2
