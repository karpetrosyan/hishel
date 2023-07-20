import calendar
import typing as tp
from email.utils import parsedate_tz
from hashlib import blake2b

import httpcore
import httpx
from httpcore import URL

from ._headers import Vary


def normalized_url(url: tp.Union[httpcore.URL, str, bytes]) -> str:

    if isinstance(url, str):
        return url

    if isinstance(url, bytes):
        return url.decode('ascii')

    if isinstance(url, httpcore.URL):
        port = f":{url.port}" if url.port is not None else ""
        return f'{url.scheme.decode("ascii")}://{url.host.decode("ascii")}{port}{url.target.decode("ascii")}'
    assert False, "Invalid type for `normalized_url`"


def generate_key(method: bytes,
                 url: URL,
                 headers: tp.List[tp.Tuple[bytes, bytes]]) -> str:
    vary_values = [val.decode('ascii') for val in extract_header_values(headers, b'vary')]
    vary = Vary.from_value(vary_values=vary_values)
    vary_headers_suffix = b""
    for vary_value in vary._values:
        vary_headers_suffix += vary_value.encode('ascii') + b'='
        vary_headers_suffix += b', '.join(extract_header_values(headers, vary_value.encode('ascii')))

    encoded_url = normalized_url(url).encode('ascii')

    key_parts = [
            method,
            encoded_url,
            vary_headers_suffix,
         ]


    key = blake2b(digest_size=16)
    for part in key_parts:
        key.update(part)
    return key.hexdigest()


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


def header_presents(
    headers: tp.List[tp.Tuple[bytes, bytes]],
    header_key: bytes
) -> bool:
    return bool(extract_header_values(headers, header_key, single=True))


def parse_date(date: str) -> int:
    expires = parsedate_tz(date)
    timestamp = calendar.timegm(expires[:6])  # type: ignore
    return timestamp

def to_httpx_response(httpcore_response: httpcore.Response) -> httpx.Response:

    response = httpx.Response(
        status_code=httpcore_response.status,
        headers=httpcore_response.headers,
        content=httpcore_response.content,
        extensions=httpcore_response.extensions
    )
    response.read()
    return response

def to_httpcore_response(httpx_response: httpx.Response) -> httpcore.Response:

    response = httpcore.Response(
        status=httpx_response.status_code,
        headers=httpx_response.headers.raw,
        content=httpx_response.content,
        extensions=httpx_response.extensions
    )
    response.read()
    return response

def to_httpx_request(httpcore_request: httpcore.Request) -> httpx.Request:

    return httpx.Request(
        httpcore_request.method,
        normalized_url(httpcore_request.url),
        headers=httpcore_request.headers,
        extensions=httpcore_request.extensions
    )

def to_httpcore_request(httpx_request: httpx.Request) -> httpcore.Request:
    return httpcore.Request(
        httpx_request.method,
        str(httpx_request.url),
        headers=httpx_request.headers.raw,
        extensions=httpx_request.extensions
    )

