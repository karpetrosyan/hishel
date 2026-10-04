import httpx
import pytest

from hishel._core.models import extract_metadata_from_headers


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", "Yes"])
def test_extract_body_key_true_from_headers(value: str) -> None:
    metadata = extract_metadata_from_headers(httpx.Headers({"X-Hishel-Body-Key": value}))

    assert metadata["hishel_body_key"] is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "FALSE", "No"])
def test_extract_body_key_false_from_headers(value: str) -> None:
    metadata = extract_metadata_from_headers(httpx.Headers({"X-Hishel-Body-Key": value}))

    assert metadata["hishel_body_key"] is False


@pytest.mark.parametrize("value", ["", "sometimes", " true "])
def test_invalid_body_key_header_is_ignored(value: str) -> None:
    metadata = extract_metadata_from_headers(httpx.Headers({"X-Hishel-Body-Key": value}))

    assert "hishel_body_key" not in metadata


def test_body_key_header_is_matched_case_insensitively() -> None:
    """Field names are lowercase on the wire over HTTP/2 and HTTP/3.

    The transports pass `httpx.Headers`, which compares names without regard
    to case, the same as the other `X-Hishel-*` headers.
    """
    metadata = extract_metadata_from_headers(httpx.Headers({"x-hishel-body-key": "true"}))

    assert metadata["hishel_body_key"] is True
