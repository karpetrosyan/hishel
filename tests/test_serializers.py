from httpcore import Response

from hishel._serializers import DictSerializer, YamlSerializer


def test_dict_serializer_dump():

    response = Response(
        status=200,
        headers=[
            (b'Content-Type', b'application/json'),
            (b'Transfer-Encoding', b'chunked')
        ]
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
            '    "content": "",',
            '    "extensions": {}',
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
            '    "content": "",',
            '    "extensions": {}',
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
    assert response.content == b""

def test_yaml_serializer_dump():

    response = Response(
        status=200,
        headers=[
            (b'Content-Type', b'application/json'),
            (b'Transfer-Encoding', b'chunked')
        ]
    )
    response.read()
    response_dict = YamlSerializer().dumps(response)

    assert response_dict == '\n'.join(
            [
                "content: ''",
                "extensions: {}",
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
                "content: ''",
                "extensions: {}",
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
    assert response.content == b""
