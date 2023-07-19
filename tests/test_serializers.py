from httpcore import Response

from hishel._serializers import DictSerializer, PickleSerializer, YamlSerializer


def test_pickle_serializer_dumps():

    response = Response(
        status=200,
        headers=[
            (b'Content-Type', b'application/json'),
            (b'Transfer-Encoding', b'chunked')
        ],
        content=b'test',
        extensions={
            'reason_phrase': b'OK',
            'http_version': b'HTTP/1.1'
        }
    )
    response.read()
    response_dict = PickleSerializer().dumps(response)
    assert response_dict == b"".join(
        [
            b"\x80\x04\x95\x16\x01\x00\x00\x00\x00\x00\x00\x8c\x08httpcore\x94\x8c\x08",
            b"Response\x94\x93\x94)\x81\x94}\x94(\x8c\x06",
            b"status\x94K\xc8\x8c\x07",
            b"headers\x94]\x94(C\x0c",
            b"Content-Type\x94C\x10application/json\x94\x86\x94C\x11",
            b"Transfer-Encoding\x94C\x07chunked\x94\x86\x94e\x8c\x06",
            b"stream\x94\x8c\x10httpcore._models\x94\x8c\n",
            b"ByteStream\x94\x93\x94)\x81\x94}\x94\x8c\x08",
            b"_content\x94C\x04test\x94sb\x8c\n",
            b"extensions\x94}\x94(\x8c\r",
            b"reason_phrase\x94C\x02OK\x94\x8c\x0c",
            b"http_version\x94C\x08HTTP/1.1\x94u\x8c\x10",
            b"_stream_consumed\x94\x89ub.",
        ]
    )

def test_pickle_serializer_loads():

    raw_response = b"".join(
        [
            b"\x80\x04\x95\x16\x01\x00\x00\x00\x00\x00\x00\x8c\x08httpcore\x94\x8c\x08",
            b"Response\x94\x93\x94)\x81\x94}\x94(\x8c\x06",
            b"status\x94K\xc8\x8c\x07",
            b"headers\x94]\x94(C\x0c",
            b"Content-Type\x94C\x10application/json\x94\x86\x94C\x11",
            b"Transfer-Encoding\x94C\x07chunked\x94\x86\x94e\x8c\x06",
            b"stream\x94\x8c\x10httpcore._models\x94\x8c\n",
            b"ByteStream\x94\x93\x94)\x81\x94}\x94\x8c\x08",
            b"_content\x94C\x04test\x94sb\x8c\n",
            b"extensions\x94}\x94(\x8c\r",
            b"reason_phrase\x94C\x02OK\x94\x8c\x0c",
            b"http_version\x94C\x08HTTP/1.1\x94u\x8c\x10",
            b"_stream_consumed\x94\x89ub.",
        ]
    )

    response = PickleSerializer().loads(raw_response)
    response.read()
    assert response.status == 200
    assert response.headers == [
        (b'Content-Type', b'application/json'),
        (b'Transfer-Encoding', b'chunked')
    ]
    assert response.content == b"test"
    assert response.extensions == {
        'http_version': b'HTTP/1.1',
        'reason_phrase': b'OK'
    }

def test_dict_serializer_dumps():

    response = Response(
        status=200,
        headers=[
            (b'Content-Type', b'application/json'),
            (b'Transfer-Encoding', b'chunked')
        ],
        content=b'test',
        extensions={
            'reason_phrase': b'OK',
            'http_version': b'HTTP/1.1'
        }
    )
    response.read()
    response_dict = DictSerializer().dumps(response)

    assert response_dict == '\n'.join(
        [
            '{',
            '    "status": 200,',
            '    "headers": [',
            '        [',
            '            "Content-Type",',
            '            "application/json"',
            '        ],',
            '        [',
            '            "Transfer-Encoding",',
            '            "chunked"',
            '        ]',
            '    ],',
            '    "content": "dGVzdA==",',
            '    "extensions": {',
            '        "reason_phrase": "OK",',
            '        "http_version": "HTTP/1.1"',
            '    }',
            '}'
        ]
    )

def test_dict_serializer_loads():

    raw_response = '\n'.join(
        [
            '{',
            '    "status": 200,',
            '    "headers": [',
            '        [',
            '            "Content-Type",',
            '            "application/json"',
            '        ],',
            '        [',
            '            "Transfer-Encoding",',
            '            "chunked"',
            '        ]',
            '    ],',
            '    "content": "dGVzdA==",',
            '    "extensions": {',
            '        "reason_phrase": "OK",',
            '        "http_version": "HTTP/1.1"',
            '    }',
            '}'
        ]
    )

    response = DictSerializer().loads(raw_response)
    response.read()
    assert response.status == 200
    assert response.headers == [
        (b'Content-Type', b'application/json'),
        (b'Transfer-Encoding', b'chunked')
    ]
    assert response.content == b"test"
    assert response.extensions == {
        'http_version': b'HTTP/1.1',
        'reason_phrase': b'OK'
    }

def test_yaml_serializer_dumps():

    response = Response(
        status=200,
        headers=[
            (b'Content-Type', b'application/json'),
            (b'Transfer-Encoding', b'chunked')
        ],
        content=b'test',
        extensions={
            'reason_phrase': b'OK',
            'http_version': b'HTTP/1.1'
        }
    )
    response.read()
    response_dict = YamlSerializer().dumps(response)

    assert response_dict == '\n'.join(
            [
                "status: 200",
                "headers:",
                "- - Content-Type",
                "  - application/json",
                "- - Transfer-Encoding",
                "  - chunked",
                "content: dGVzdA==",
                "extensions:",
                "  reason_phrase: OK",
                "  http_version: HTTP/1.1",
                ""
            ]
    )

def test_yaml_serializer_loads():

    raw_response = '\n'.join(
            [
                "status: 200",
                "headers:",
                "- - Content-Type",
                "  - application/json",
                "- - Transfer-Encoding",
                "  - chunked",
                "content: dGVzdA==",
                "extensions:",
                "  reason_phrase: OK",
                "  http_version: HTTP/1.1",
                ""
            ]
    )

    response = YamlSerializer().loads(raw_response)
    response.read()
    assert response.status == 200
    assert response.headers == [
        (b'Content-Type', b'application/json'),
        (b'Transfer-Encoding', b'chunked')
    ]
    assert response.content == b"test"
    assert response.extensions == {
        'http_version': b'HTTP/1.1',
        'reason_phrase': b'OK'
    }
