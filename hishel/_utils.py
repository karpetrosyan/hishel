from __future__ import annotations

import calendar
import hashlib
import time
import typing as tp
from email.utils import parsedate_tz
from typing import AsyncIterator, Generator, Iterable, Iterator, TypeVar

import httpcore
import httpx

HEADERS_ENCODING = "iso-8859-1"

T = tp.TypeVar("T")


class BaseClock:
    def now(self) -> int:
        raise NotImplementedError()


class Clock(BaseClock):
    def now(self) -> int:
        return int(time.time())


def normalized_url(url: tp.Union[httpcore.URL, str, bytes]) -> str:
    if isinstance(url, str):  # pragma: no cover
        return url

    if isinstance(url, bytes):  # pragma: no cover
        return url.decode("ascii")

    if isinstance(url, httpcore.URL):
        port = f":{url.port}" if url.port is not None else ""
        return f"{url.scheme.decode('ascii')}://{url.host.decode('ascii')}{port}{url.target.decode('ascii')}"
    assert False, "Invalid type for `normalized_url`"  # pragma: no cover


def get_safe_url(url: httpcore.URL) -> str:
    httpx_url = httpx.URL(bytes(url).decode("ascii"))

    schema = httpx_url.scheme
    host = httpx_url.host
    path = httpx_url.path

    return f"{schema}://{host}{path}"


def generate_key(request: httpcore.Request, body: bytes = b"") -> str:
    encoded_url = normalized_url(request.url).encode("ascii")

    key_parts = [request.method, encoded_url, body]

    # FIPs mode disables blake2 algorithm, use sha256 instead when not found.
    blake2b_hasher = None
    sha256_hasher = hashlib.sha256(usedforsecurity=False)
    try:
        blake2b_hasher = hashlib.blake2b(digest_size=16, usedforsecurity=False)
    except (ValueError, TypeError, AttributeError):
        pass

    hexdigest: str
    if blake2b_hasher:
        for part in key_parts:
            blake2b_hasher.update(part)

        hexdigest = blake2b_hasher.hexdigest()
    else:
        for part in key_parts:
            sha256_hasher.update(part)

        hexdigest = sha256_hasher.hexdigest()
    return hexdigest


def extract_header_values(
    headers: tp.List[tp.Tuple[bytes, bytes]],
    header_key: tp.Union[bytes, str],
    single: bool = False,
) -> tp.List[bytes]:
    if isinstance(header_key, str):
        header_key = header_key.encode(HEADERS_ENCODING)
    extracted_headers = []
    for key, value in headers:
        if key.lower() == header_key.lower():
            extracted_headers.append(value)
            if single:
                break
    return extracted_headers


def extract_header_values_decoded(
    headers: tp.List[tp.Tuple[bytes, bytes]], header_key: bytes, single: bool = False
) -> tp.List[str]:
    values = extract_header_values(headers=headers, header_key=header_key, single=single)
    return [value.decode(HEADERS_ENCODING) for value in values]


def header_presents(headers: tp.List[tp.Tuple[bytes, bytes]], header_key: bytes) -> bool:
    return bool(extract_header_values(headers, header_key, single=True))


def parse_date(date: str) -> tp.Optional[int]:
    expires = parsedate_tz(date)
    if expires is None:
        return None
    timestamp = calendar.timegm(expires[:6])
    return timestamp


def sleep(seconds: tp.Union[int, float]) -> None:
    time.sleep(seconds)


def float_seconds_to_int_milliseconds(seconds: float) -> int:
    return int(seconds * 1000)


def partition(iterable: tp.Iterable[T], predicate: tp.Callable[[T], bool]) -> tp.Tuple[tp.List[T], tp.List[T]]:
    """
    Partition an iterable into two lists: one for matching items and one for non-matching items.

    Args:
        iterable (tp.Iterable[T]): The input iterable to partition.
        predicate (tp.Callable[[T], bool]): A function that evaluates each item in the iterable.

    Returns:
        tp.Tuple[tp.List[T], tp.List[T]]: A tuple containing two lists: the first for matching items,
        and the second for non-matching items.
    Example:
        ```
        iterable = [1, 2, 3, 4, 5]
        is_even = lambda x: x % 2 == 0
        evens, odds = partition(iterable, is_even)
        ```
    """
    matching, non_matching = [], []
    for item in iterable:
        if predicate(item):
            matching.append(item)
        else:
            non_matching.append(item)
    return matching, non_matching


async def make_async_iterator(iterable: Iterable[bytes]) -> AsyncIterator[bytes]:
    for item in iterable:
        yield item


def make_sync_iterator(iterable: Iterable[bytes]) -> Iterator[bytes]:
    for item in iterable:
        yield item


def snake_to_header(text: str) -> str:
    """
    Convert snake_case string to Header-Case format.

    Args:
        text: Snake case string (e.g., "hishel_ttl")

    Returns:
        Header case string (e.g., "X-Hishel-Ttl")

    Examples:
        >>> snake_to_header("hishel_ttl")
        'X-Hishel-Ttl'
        >>> snake_to_header("cache_control")
        'X-Cache-Control'
        >>> snake_to_header("content_type")
        'X-Content-Type'
    """
    # Split by underscore, capitalize each word, join with dash, add X- prefix
    return "X-" + "-".join(word.capitalize() for word in text.split("_"))


_T = TypeVar("_T")


class GeneratorWithReturnValue:
    def __init__(
        self, gen: Generator[None, bytes | None, bytes], stream: AsyncIterator[bytes] | Iterator[bytes]
    ) -> None:
        self.gen = gen
        self.stream = stream
        self.value: bytes | None = None

    def __iter__(self) -> Iterator[bytes]:
        return self

    def __next__(self) -> bytes:
        assert isinstance(self.stream, Iterator)

        try:
            chunk = next(self.stream)
            self.gen.send(chunk)
        except StopIteration as exc:
            self.gen.send(None)
            self.value = exc.value
            raise
        return chunk

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self

    async def __anext__(self) -> bytes:
        assert isinstance(self.stream, AsyncIterator)
        try:
            chunk = await self.stream.__anext__()
            self.gen.send(chunk)
        except StopIteration as exc:
            self.gen.send(None)
            self.value = exc.value
            raise
        return chunk
