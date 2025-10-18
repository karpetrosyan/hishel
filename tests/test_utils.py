from unittest import mock

import httpcore
import pytest
from httpcore import Request

from hishel._utils import (
    extract_header_values,
    extract_header_values_decoded,
    float_seconds_to_int_milliseconds,
    generate_key,
    get_safe_url,
    header_presents,
    parse_date,
)


def test_generate_key():
    request = Request(b"GET", "https://example.com", headers=[])

    key = generate_key(request)

    assert key == "bd152069787aaad359c85af6f2edbb25"


def test_fips_generate_key():
    request = Request(b"GET", "https://example.com", headers=[])

    # Simulate FIPS mode by using sha256 instead of blake2b
    with mock.patch("hashlib.blake2b", side_effect=AttributeError("ERROR")):
        key = generate_key(request)

    assert key == "ea96dc6995764a0e6cf26bd2550deb01c18f69c0e586aa1fe201683129b8c15a"


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


def test_parse_date():
    date = "Mon, 25 Aug 2015 12:00:00 GMT"
    timestamp = parse_date(date)
    assert timestamp == 1440504000


def test_parse_invalid_date():
    date = "0"
    timestamp = parse_date(date)
    assert timestamp is None


def test_float_seconds_to_milliseconds():
    seconds = 1.234
    milliseconds = float_seconds_to_int_milliseconds(seconds)
    assert milliseconds == 1234


@pytest.mark.parametrize(
    "url, expected",
    [
        pytest.param(
            "https://example.com/path?query=1",
            "https://example.com/path",
            id="url_with_query_is_ignored",
        ),
        pytest.param(
            "https://example.com/path",
            "https://example.com/path",
            id="url_without_query",
        ),
        pytest.param("https://example.com", "https://example.com/", id="url_without_path"),
        pytest.param(
            "https://xn--e1afmkfd.xn--p1ag",
            "https://пример.ру/",
            id="url_with_idna",
        ),
    ],
)
def test_safe_url(
    url: str,
    expected: str,
) -> None:
    httpcore_url = httpcore.URL(url)
    safe_url = get_safe_url(httpcore_url)

    assert safe_url == expected
