import calendar
import json
import typing as tp
from email.utils import parsedate_tz
from pathlib import Path

from httpcore import URL

from ._headers import Vary


def generate_key(method: bytes,
                 url: URL,
                 headers: tp.List[tp.Tuple[bytes, bytes]]) -> str:
    vary_values = [val.decode('ascii') for val in extract_header_values(headers, b'vary')]
    vary = Vary.from_value(vary_values=vary_values)
    vary_headers_suffix = b""
    for vary_value in vary._values:
        vary_headers_suffix += vary_value.encode('ascii') + b'='
        vary_headers_suffix += b', '.join(extract_header_values(headers, vary_value.encode('ascii')))
    key = ''.join(
        [
            method.decode('ascii'),
            repr(url),
            vary_headers_suffix.decode('ascii'),
        ]
    )

    return key


def extract_header_values(
    headers: tp.List[tp.Tuple[bytes, bytes]],
    header_key: bytes,
    single: bool = False
) -> tp.List[bytes]:
    extracted_headers = []

    for key, value in headers:
        if key.lower() == header_key.lower():
            extracted_headers.append(value)
            if single:
                break
    return extracted_headers

def extract_header_values_decoded(
    headers: tp.List[tp.Tuple[bytes, bytes]],
    header_key: bytes,
    single: bool = False
) -> tp.List[str]:
    values = extract_header_values(headers=headers, header_key=header_key, single=single)
    return [value.decode() for value in values]


def load_path_map(
    path: Path,
) -> tp.Dict[str, Path]:
    dct: tp.Dict[str, Path] = json.loads(path.read_text())

    for key, value in dct.items():
        dct[key] = Path(dct[key])
    return dct

def header_presents(
    headers: tp.List[tp.Tuple[bytes, bytes]],
    header_key: bytes
) -> bool:
    return bool(extract_header_values(headers, header_key, single=True))


def parse_date(date: str) -> int:
    expires = parsedate_tz(date)
    timestamp = calendar.timegm(expires[:6])  # type: ignore
    return timestamp
