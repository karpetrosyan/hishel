import pytest

from hishel._core.models import extract_metadata_from_headers


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", "Yes"])
def test_extract_body_key_true_from_headers(value: str) -> None:
    metadata = extract_metadata_from_headers({"x-hIsHeL-bOdY-kEy": value})

    assert metadata["hishel_body_key"] is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "FALSE", "No"])
def test_extract_body_key_false_from_headers(value: str) -> None:
    metadata = extract_metadata_from_headers({"x-hIsHeL-bOdY-kEy": value})

    assert metadata["hishel_body_key"] is False


@pytest.mark.parametrize("value", ["", "sometimes", " true "])
def test_invalid_body_key_header_is_ignored(value: str) -> None:
    metadata = extract_metadata_from_headers({"X-Hishel-Body-Key": value})

    assert "hishel_body_key" not in metadata
