from __future__ import annotations

import calendar
import typing as tp
from email.utils import parsedate_tz
from pathlib import Path
from typing import AsyncIterator, Iterable, Iterator

T = tp.TypeVar("T")


def parse_date(date: str) -> tp.Optional[int]:
    expires = parsedate_tz(date)
    if expires is None:
        return None
    timestamp = calendar.timegm(expires[:6])
    return timestamp


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


def make_sync_iterator(iterable: Iterable[bytes]) -> Iterator[bytes]:
    for item in iterable:
        yield item


def ensure_cache_dict(base_path: Path | None = None) -> Path:
    _base_path = base_path if base_path is not None else Path(".cache/hishel")
    _gitignore_file = _base_path / ".gitignore"

    _base_path.mkdir(parents=True, exist_ok=True)

    if not _gitignore_file.is_file():
        with open(_gitignore_file, "w", encoding="utf-8") as f:
            f.write("# Automatically created by Hishel\n*")
    return _base_path
