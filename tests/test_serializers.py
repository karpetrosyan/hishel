from httpcore import Response

from hishel._serializers import DictSerializer, YamlSerializer


def test_dict_serializer_dump():

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
    
def test_yaml_serializer_dump():

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
                "content: dGVzdA==",  # b'test'
                "extensions:",
                "  http_version: HTTP/1.1",
                "  reason_phrase: OK",
                "headers:",
                "- - Content-Type",
                "  - application/json",
                "- - Transfer-Encoding",
                "  - chunked",
                "status: 200",
                ""
            ]
    )

def test_yaml_serializer_loads():

    raw_response = '\n'.join(
            [
                "content: dGVzdA==",  # b'test'
                "extensions:",
                "  http_version: HTTP/1.1",
                "  reason_phrase: OK",
                "headers:",
                "- - Content-Type",
                "  - application/json",
                "- - Transfer-Encoding",
                "  - chunked",
                "status: 200",
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
