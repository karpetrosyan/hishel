from __future__ import annotations

import calendar
import time
import typing as tp
from email.utils import parsedate_tz
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
