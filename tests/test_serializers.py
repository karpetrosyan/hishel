import datetime
import json

import pytest
from httpcore import Request, Response

from hishel._serializers import JSONByteSerializer, JSONSerializer, Metadata, PickleSerializer, YAMLSerializer
from hishel._utils import normalized_url

try:
    import yaml
except ImportError:  # pragma: nocover
    yaml = None  # type: ignore


def test_pickle_serializer_dumps_and_loads():
    request = Request(
        method="GET",
        url="https://example.com",
        headers=[(b"Accept-Encoding", b"gzip")],
        extensions={"sni_hostname": "example.com"},
    )
    response = Response(
        status=200,
        headers=[
            (b"Content-Type", b"application/json"),
            (b"Transfer-Encoding", b"chunked"),
        ],
        content=b"test",
        extensions={"reason_phrase": b"OK", "http_version": b"HTTP/1.1"},
    )
    response.read()

    metadata = Metadata(
        cache_key="test",
        number_of_uses=0,
        created_at=datetime.datetime(year=2003, month=8, day=25, hour=12),
    )

    raw_response = PickleSerializer().dumps(response=response, request=request, metadata=metadata)

    response, request, metadata = PickleSerializer().loads(raw_response)
    response.read()
    assert response.status == 200
    assert response.headers == [
        (b"Content-Type", b"application/json"),
        (b"Transfer-Encoding", b"chunked"),
    ]
    assert response.content == b"test"
    assert response.extensions == {"http_version": b"HTTP/1.1", "reason_phrase": b"OK"}

    assert request.method == b"GET"
    assert normalized_url(request.url) == "https://example.com/"
    assert request.headers == [(b"Accept-Encoding", b"gzip")]
    assert request.extensions == {"sni_hostname": "example.com"}

    assert metadata["cache_key"] == "test"
    assert metadata["number_of_uses"] == 0
    assert metadata["created_at"] == datetime.datetime(year=2003, month=8, day=25, hour=12)


def test_dict_serializer_dumps():
    request = Request(
        method="GET",
        url="https://example.com",
        headers=[(b"Accept-Encoding", b"gzip")],
        extensions={"sni_hostname": "example.com"},
    )
    response = Response(
        status=200,
        headers=[
            (b"Content-Type", b"application/json"),
            (b"Transfer-Encoding", b"chunked"),
        ],
        content=b"test",
        extensions={"reason_phrase": b"OK", "http_version": b"HTTP/1.1"},
    )
    response.read()

    metadata = Metadata(
        cache_key="test",
        number_of_uses=0,
        created_at=datetime.datetime(year=2003, month=8, day=25, hour=12),
    )

    full_json = JSONSerializer().dumps(response=response, request=request, metadata=metadata)

    assert full_json == "\n".join(
        [
            "{",
            '    "response": {',
            '        "status": 200,',
            '        "headers": [',
            "            [",
            '                "Content-Type",',
            '                "application/json"',
            "            ],",
            "            [",
            '                "Transfer-Encoding",',
            '                "chunked"',
            "            ]",
            "        ],",
            '        "content": "dGVzdA==",',
            '        "extensions": {',
            '            "reason_phrase": "OK",',
            '            "http_version": "HTTP/1.1"',
            "        }",
            "    },",
            '    "request": {',
            '        "method": "GET",',
            '        "url": "https://example.com/",',
            '        "headers": [',
            "            [",
            '                "Accept-Encoding",',
            '                "gzip"',
            "            ]",
            "        ],",
            '        "extensions": {',
            '            "sni_hostname": "example.com"',
            "        }",
            "    },",
            '    "metadata": {',
            '        "cache_key": "test",',
            '        "number_of_uses": 0,',
            '        "created_at": "Mon, 25 Aug 2003 12:00:00 GMT"',
            "    }",
            "}",
        ]
    )


def test_dict_serializer_loads():
    raw_response = "\n".join(
        [
            "{",
            '    "response": {',
            '        "status": 200,',
            '        "headers": [',
            "            [",
            '                "Content-Type",',
            '                "application/json"',
            "            ],",
            "            [",
            '                "Transfer-Encoding",',
            '                "chunked"',
            "            ]",
            "        ],",
            '        "content": "dGVzdA==",',
            '        "extensions": {',
            '            "reason_phrase": "OK",',
            '            "http_version": "HTTP/1.1"',
            "        }",
            "    },",
            '    "request": {',
            '        "method": "GET",',
            '        "url": "https://example.com/",',
            '        "headers": [',
            "            [",
            '                "Accept-Encoding",',
            '                "gzip"',
            "            ]",
            "        ],",
            '        "extensions": {',
            '            "sni_hostname": "example.com"',
            "        }",
            "    },",
            '    "metadata": {',
            '        "cache_key": "test",',
            '        "number_of_uses": 0,',
            '        "created_at": "Mon, 25 Aug 2003 12:00:00 GMT"',
            "    }",
            "}",
        ]
    )

    response, request, metadata = JSONSerializer().loads(raw_response)
    response.read()
    assert response.status == 200
    assert response.headers == [
        (b"Content-Type", b"application/json"),
        (b"Transfer-Encoding", b"chunked"),
    ]
    assert response.content == b"test"
    assert response.extensions == {"http_version": b"HTTP/1.1", "reason_phrase": b"OK"}

    assert request.method == b"GET"
    assert normalized_url(request.url) == "https://example.com/"
    assert request.headers == [(b"Accept-Encoding", b"gzip")]
    assert request.extensions == {"sni_hostname": "example.com"}

    assert metadata["cache_key"] == "test"
    assert metadata["number_of_uses"] == 0
    assert metadata["created_at"] == datetime.datetime(year=2003, month=8, day=25, hour=12)


def test_yaml_serializer_dumps():
    if yaml is None:  # pragma: no cover
        pytest.skip("yaml not installed")
    request = Request(
        method="GET",
        url="https://example.com",
        headers=[(b"Accept-Encoding", b"gzip")],
        extensions={"sni_hostname": "example.com"},
    )
    response = Response(
        status=200,
        headers=[
            (b"Content-Type", b"application/json"),
            (b"Transfer-Encoding", b"chunked"),
        ],
        content=b"test",
        extensions={"reason_phrase": b"OK", "http_version": b"HTTP/1.1"},
    )
    response.read()

    metadata = Metadata(
        cache_key="test",
        number_of_uses=0,
        created_at=datetime.datetime(year=2003, month=8, day=25, hour=12),
    )

    full_json = YAMLSerializer().dumps(response=response, request=request, metadata=metadata)

    assert full_json == "\n".join(
        [
            "response:",
            "  status: 200",
            "  headers:",
            "  - - Content-Type",
            "    - application/json",
            "  - - Transfer-Encoding",
            "    - chunked",
            "  content: dGVzdA==",
            "  extensions:",
            "    reason_phrase: OK",
            "    http_version: HTTP/1.1",
            "request:",
            "  method: GET",
            "  url: https://example.com/",
            "  headers:",
            "  - - Accept-Encoding",
            "    - gzip",
            "  extensions:",
            "    sni_hostname: example.com",
            "metadata:",
            "  cache_key: test",
            "  number_of_uses: 0",
            "  created_at: Mon, 25 Aug 2003 12:00:00 GMT",
            "",
        ]
    )


def test_yaml_serializer_loads():
    if yaml is None:  # pragma: no cover
        pytest.skip("yaml not installed")
    raw_response = "\n".join(
        [
            "response:",
            "  status: 200",
            "  headers:",
            "  - - Content-Type",
            "    - application/json",
            "  - - Transfer-Encoding",
            "    - chunked",
            "  content: dGVzdA==",
            "  extensions:",
            "    reason_phrase: OK",
            "    http_version: HTTP/1.1",
            "request:",
            "  method: GET",
            "  url: https://example.com/",
            "  headers:",
            "  - - Accept-Encoding",
            "    - gzip",
            "  extensions:",
            "    sni_hostname: example.com",
            "metadata:",
            "  cache_key: test",
            "  number_of_uses: 0",
            "  created_at: Mon, 25 Aug 2003 12:00:00 GMT",
            "",
        ]
    )

    response, request, metadata = YAMLSerializer().loads(raw_response)
    response.read()
    assert response.status == 200
    assert response.headers == [
        (b"Content-Type", b"application/json"),
        (b"Transfer-Encoding", b"chunked"),
    ]
    assert response.content == b"test"
    assert response.extensions == {"http_version": b"HTTP/1.1", "reason_phrase": b"OK"}

    assert request.method == b"GET"
    assert normalized_url(request.url) == "https://example.com/"
    assert request.headers == [(b"Accept-Encoding", b"gzip")]
    assert request.extensions == {"sni_hostname": "example.com"}

    assert metadata["cache_key"] == "test"
    assert metadata["number_of_uses"] == 0
    assert metadata["created_at"] == datetime.datetime(year=2003, month=8, day=25, hour=12)


def test_jsonbyte_serializer_dumps():
    request = Request(
        method="GET",
        url="https://example.com",
        headers=[(b"Accept-Encoding", b"gzip")],
        extensions={"sni_hostname": "example.com"},
    )
    response = Response(
        status=200,
        headers=[
            (b"Content-Type", b"application/json"),
            (b"Transfer-Encoding", b"chunked"),
        ],
        content=b"test",
        extensions={"reason_phrase": b"OK", "http_version": b"HTTP/1.1"},
    )
    response.read()

    metadata = Metadata(
        cache_key="test",
        number_of_uses=0,
        created_at=datetime.datetime(year=2003, month=8, day=25, hour=12),
    )

    full = JSONByteSerializer().dumps(response=response, request=request, metadata=metadata)
    meta_raw, body = full.split(b"\0", 1)
    meta = json.loads(meta_raw.decode("utf-8"))

    assert body == b"test"
    assert (
        meta["response"]["status"] == 200
        and meta["request"]["method"] == "GET"
        and meta["request"]["url"] == "https://example.com/"
    )
    assert meta["response"]["headers"] == [["Content-Type", "application/json"], ["Transfer-Encoding", "chunked"]]
    assert meta["metadata"]["created_at"] == "Mon, 25 Aug 2003 12:00:00 GMT"


def test_jsonbyte_serializer_loads():
    meta = {
        "response": {
            "status": 200,
            "headers": [["Content-Type", "application/json"], ["Transfer-Encoding", "chunked"]],
            "extensions": {"reason_phrase": "OK", "http_version": "HTTP/1.1"},
        },
        "request": {
            "method": "GET",
            "url": "https://example.com/",
            "headers": [["Accept-Encoding", "gzip"]],
            "extensions": {"sni_hostname": "example.com"},
        },
        "metadata": {"cache_key": "test", "number_of_uses": 0, "created_at": "Mon, 25 Aug 2003 12:00:00 GMT"},
    }

    raw_response = json.dumps(meta, separators=(",", ":")).encode("utf-8") + b"\0" + b"test"
    response, request, metadata = JSONByteSerializer().loads(raw_response)

    response.read()
    assert response.status == 200
    assert response.headers == [
        (b"Content-Type", b"application/json"),
        (b"Transfer-Encoding", b"chunked"),
    ]
    assert response.content == b"test"
    assert response.extensions == {"http_version": b"HTTP/1.1", "reason_phrase": b"OK"}

    assert request.method == b"GET"
    assert normalized_url(request.url) == "https://example.com/"
    assert request.headers == [(b"Accept-Encoding", b"gzip")]
    assert request.extensions == {"sni_hostname": "example.com"}

    assert metadata["cache_key"] == "test"
    assert metadata["number_of_uses"] == 0
    assert metadata["created_at"] == datetime.datetime(year=2003, month=8, day=25, hour=12)
