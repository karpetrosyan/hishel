from httpcore import Request
from httpcore._models import ByteStream

from hishel._controller import get_updated_headers
from hishel._utils import (
    extract_header_values,
    extract_header_values_decoded,
    float_seconds_to_int_milliseconds,
    generate_key,
    header_presents,
    parse_date,
)


def test_generate_key():
    request = Request(b"GET", "https://example.com", headers=[])

    key = generate_key(request)

    assert key == "a7adb5b2ce6743dee8eb1af8e605b3fa"


def test_generate_key_with_body():
    get_request = Request(b"POST", "https://example.com", content=b"1")
    post_request = Request(b"POST", "https://example.com", content=b"2")
    get_key = generate_key(get_request)
    post_key = generate_key(post_request)
    assert get_key != post_key


def test_generate_key_with_iterable_body():
    byte_stream = ByteStream(b"1234567890")
    request = Request(b"POST", "https://example.com", content=byte_stream)
    key = generate_key(request)
    assert key == "ac9bc139d1f08fca6849de9e0db2a843"
    request2 = Request(b"POST", "https://example.com")
    key2 = generate_key(request2)
    assert key != key2


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

    update_headers = get_updated_headers(stored_response_headers=old_headers, new_response_headers=new_headers)

    assert len(update_headers) == 3
    assert extract_header_values(update_headers, b"Language")[0] == b"am"
    assert extract_header_values(update_headers, b"Content-Type")[0] == b"application/json"
    assert extract_header_values(update_headers, b"Authorization")[0] == b"secret-key"


def test_parse_date():
    date = "Mon, 25 Aug 2015 12:00:00 GMT"
    timestamp = parse_date(date)
    assert timestamp == 1440504000


def test_float_seconds_to_milliseconds():
    seconds = 1.234
    milliseconds = float_seconds_to_int_milliseconds(seconds)
    assert milliseconds == 1234
