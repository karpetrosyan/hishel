
from httpcore import Request

from hishel._utils import generate_key


def test_generate_key():
    request = Request(
        b'GET',
        'https://example.com',
        headers=[]
    )

    key = generate_key(
        request.method,
        request.url,
        request.headers
    )

    assert key == "GETURL(scheme=b'https', host=b'example.com', port=None, target=b'/')"

def test_generate_key_with_vary():
    request = Request(
        b'GET',
        'https://example.com',
        headers=[
                (b"Vary", b"Content-Type, Accept"),
                (b"Accept", b"application/json"),
                (b"Content-Type", b"application/json")
                ]
    )

    key = generate_key(
        request.method,
        request.url,
        request.headers
    )

    assert key == (
        "GETURL(scheme=b'https', host=b'example.com', port=None, "
        "target=b'/')Content-Type=application/jsonAccept=application/json"
    )
