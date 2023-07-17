
from httpcore import Request

from hishel._utils import generate_key
from hishel._utils import extract_header_values


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


def test_extract_header_values():
    headers = [
        (b'Content-Type', b'application/json'),
        (b'Content-Type', b'application/html')
    ]

    values = extract_header_values(
        headers, b'Content-Type'
    )
    assert values == [b'application/json', b'application/html']

def test_extract_header_single_value():
    headers = [
        (b'Content-Type', b'application/json'),
        (b'Content-Type', b'application/html')
    ]

    values = extract_header_values(
        headers, b'Content-Type', single=True
    )
    assert values == [b'application/json']