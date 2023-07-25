from httpcore import Request

from hishel._controller import get_updated_headers
from hishel._utils import (
    extract_header_values,
    extract_header_values_decoded,
    generate_key,
    header_presents,
    parse_date,
)


def test_generate_key():
    request = Request(b"GET", "https://example.com", headers=[])

    key = generate_key(request.method, request.url, request.headers)

    assert key == "bd152069787aaad359c85af6f2edbb25"


def test_generate_key_with_vary():
    request = Request(
        b"GET",
        "https://example.com",
        headers=[
            (b"Vary", b"Content-Type, Accept"),
            (b"Accept", b"application/json"),
            (b"Content-Type", b"application/json"),
        ],
    )

    key = generate_key(request.method, request.url, request.headers)

    assert key == "cb44189c538f1200bb8430a27dadff8b"


def test_extract_header_values():
    headers = [
        (b"Content-Type", b"application/json"),
        (b"Content-Type", b"application/html"),
    ]

    values = extract_header_values(headers, b"Content-Type")
    assert values == [b"application/json", b"application/html"]


def test_extract_header_values_decoded():
    headers = [
        (b"Content-Type", b"application/json"),
        (b"Content-Type", b"application/html"),
    ]

    values = extract_header_values_decoded(headers, b"Content-Type")
    assert values == ["application/json", "application/html"]


def test_extract_header_single_value():
    headers = [
        (b"Content-Type", b"application/json"),
        (b"Content-Type", b"application/html"),
    ]

    values = extract_header_values(headers, b"Content-Type", single=True)
    assert values == [b"application/json"]


def test_header_presents():
    headers = [
        (b"Content-Type", b"application/json"),
        (b"Content-Type", b"application/html"),
        (b"Accept", b"application/json"),
    ]

    accept_presents = header_presents(headers, b"Accept")
    assert accept_presents

    transfer_encoding_presents = header_presents(headers, b"Transfer-Encoding")
    assert not transfer_encoding_presents


def test_get_updated_headers():
    old_headers = [(b"Content-Type", b"application/json"), (b"Language", b"en")]

    new_headers = [
        (b"Language", b"am"),
        (b"Content-Length", b"1024"),
        (b"Authorization", b"secret-key"),
    ]

    update_headers = get_updated_headers(
        stored_response_headers=old_headers, new_response_headers=new_headers
    )

    assert len(update_headers) == 3
    assert extract_header_values(update_headers, b"Language")[0] == b"am"
    assert (
        extract_header_values(update_headers, b"Content-Type")[0] == b"application/json"
    )
    assert extract_header_values(update_headers, b"Authorization")[0] == b"secret-key"


def test_parse_date():
    date = "Mon, 25 Aug 2015 12:00:00 GMT"
    timestamp = parse_date(date)
    assert timestamp == 1440504000
