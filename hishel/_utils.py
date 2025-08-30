import calendar
import hashlib
import time
import typing as tp
from email.utils import parsedate_tz
from typing import AsyncIterable, AsyncIterator, Iterable, Iterator, Optional

import anyio
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


async def asleep(seconds: tp.Union[int, float]) -> None:
    await anyio.sleep(seconds)


def sleep(seconds: tp.Union[int, float]) -> None:
    time.sleep(seconds)


def float_seconds_to_int_milliseconds(seconds: float) -> int:
    return int(seconds * 1000)


def islice(
    iterable: Iterable[bytes], start: int, stop: Optional[int] = None, step: int = 1
) -> Iterator[bytes]:  # pragma: nocover
    """
    Returns an iterator over elements from `iterable` from `start` to `stop` (exclusive),
    taking every `step`-th element.
    """
    if start < 0 or (stop is not None and stop < 0):
        raise ValueError("Negative indices not supported in this simple islice")
    if step <= 0:
        raise ValueError("Step must be positive")

    it = iter(iterable)

    # Skip until start
    for _ in range(start):
        try:
            next(it)
        except StopIteration:
            return  # iterable shorter than start, nothing to yield

    index = start
    while stop is None or index < stop:
        try:
            value = next(it)
        except StopIteration:
            return
        yield value
        # Skip `step-1` items
        for _ in range(step - 1):
            try:
                next(it)
            except StopIteration:
                return
        index += step


async def aislice(
    async_iterable: AsyncIterable[bytes], start: int, stop: Optional[int] = None, step: int = 1
) -> AsyncIterator[bytes]:  # pragma: nocover
    """
    Async version of islice: yields items from `async_iterable` starting at `start`,
    stopping before `stop`, taking every `step`-th item.
    """
    if start < 0 or (stop is not None and stop < 0):
        raise ValueError("Negative indices not supported")
    if step <= 0:
        raise ValueError("Step must be positive")

    it = async_iterable.__aiter__()

    # Skip first `start` items
    for _ in range(start):
        try:
            await it.__anext__()
        except StopAsyncIteration:
            return  # iterable shorter than start

    index = start
    while stop is None or index < stop:
        try:
            value = await it.__anext__()
        except StopAsyncIteration:
            return
        yield value

        # Skip step-1 items
        for _ in range(step - 1):
            try:
                await it.__anext__()
            except StopAsyncIteration:
                return
        index += step


def chain(*iterables: tp.Iterable[T]) -> tp.Iterable[T]:  # pragma: nocover
    for it in iterables:
        for item in it:
            yield item


async def async_chain(*iterables: tp.AsyncIterable[T]) -> tp.AsyncIterable[T]:  # pragma: nocover
    for it in iterables:
        async for item in it:
            yield item


def partition(iterable: tp.Iterable[T], predicate: tp.Callable[[T], bool]) -> tp.Tuple[tp.List[T], tp.List[T]]:
    matching, non_matching = [], []
    for item in iterable:
        if predicate(item):
            matching.append(item)
        else:
            non_matching.append(item)
    return matching, non_matching
