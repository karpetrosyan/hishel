from httpcore import Response
from hishel._serializers import DictSerializer

def test_dict_serializer_dump():
    
    response = Response(
        status=200,
        headers=[
            (b'Content-Type', b'application/json'),
            (b'Transfer-Encoding', b'chunked')
        ]
    )
    response_dict = DictSerializer().dumps(response)

    assert response_dict == ''.join(
        [
            '{"status": 200, "headers": [["Q29udGVudC1UeXBl", "YXBwbGljYXRpb24vanNvbg=="], '
            '["VHJhbnNmZXItRW5jb2Rpbmc=", "Y2h1bmtlZA=="]], "content": "", "extensions": {}}'
        ]
    )

def test_dict_serializer_loads():

    response_dict = ''.join(
        [
            '{"status": 200, "headers": [["Q29udGVudC1UeXBl", "YXBwbGljYXRpb24vanNvbg=="], '
            '["VHJhbnNmZXItRW5jb2Rpbmc=", "Y2h1bmtlZA=="]], "content": "", "extensions": {}}'
        ]
    )

    response = DictSerializer().loads(response_dict)
    response.read()
    assert response.status == 200
    assert response.headers == [
        (b'Content-Type', b'application/json'),
        (b'Transfer-Encoding', b'chunked')
    ]
    assert response.content == b""