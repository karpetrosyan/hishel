from __future__ import annotations

import calendar
import time
import typing as tp
from email.utils import formatdate, parsedate_tz
from pathlib import Path
from typing import AsyncIterator, Iterable, Iterator

HEADERS_ENCODING = "iso-8859-1"

T = tp.TypeVar("T")


def parse_date(date: str) -> tp.Optional[int]:
    expires = parsedate_tz(date)
    if expires is None:
        return None
    timestamp = calendar.timegm(expires[:6])
    return timestamp


def sleep(seconds: tp.Union[int, float]) -> None:
    time.sleep(seconds)


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


async def make_async_iterator(
    iterable: Iterable[bytes],
) -> AsyncIterator[bytes]:
    for item in iterable:
        yield item


def filter_mapping(mapping: tp.Mapping[str, T], keys_to_exclude: tp.Iterable[str]) -> tp.Dict[str, T]:
    """
        Filter out specified keys from a string-keyed mapping using case-insensitive comparison.

        Args:
            mapping: The input mapping with string keys to filter.
            keys_to_exclude: An iterable of string keys to exclude (case-insensitive).

        Returns:
            A new dictionary with the specified keys excluded.

        Example:
    ```python
            original = {'a': 1, 'B': 2, 'c': 3}
            filtered = filter_mapping(original, ['b'])
            # filtered will be {'a': 1, 'c': 3}
    ```
    """
    exclude_set = {k.lower() for k in keys_to_exclude}
    return {k: v for k, v in mapping.items() if k.lower() not in exclude_set}


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


def ensure_cache_dict(base_path: Path | None = None) -> Path:
    _base_path = base_path if base_path is not None else Path(".cache/hishel")
    _gitignore_file = _base_path / ".gitignore"

    _base_path.mkdir(parents=True, exist_ok=True)

    if not _gitignore_file.is_file():
        with open(_gitignore_file, "w", encoding="utf-8") as f:
            f.write("# Automatically created by Hishel\n*")
    return _base_path


def generate_http_date() -> str:
    """
    Generate a Date header value for HTTP responses.
    Returns date in RFC 1123 format (required by HTTP/1.1).

    Example output: 'Sun, 26 Oct 2025 12:34:56 GMT'
    """
    return formatdate(timeval=None, localtime=False, usegmt=True)
