from __future__ import annotations

from time import time
from typing import (
    AsyncIterable,
    Iterable,
    Literal,
    TypeAlias,
    TypeVar,
    Union,
    overload,
)

from anyio import from_thread

UnixTimestamp: TypeAlias = int
UnixTimestampFloat: TypeAlias = float

T = TypeVar("T")


@overload
def get_unix_timestamp_seconds(
    type: Literal["int"] = "int",
) -> UnixTimestamp: ...


@overload
def get_unix_timestamp_seconds(
    type: Literal["float"],
) -> UnixTimestampFloat: ...


def get_unix_timestamp_seconds(
    type: Literal["int"] | Literal["float"] = "int",
) -> Union[UnixTimestamp, UnixTimestampFloat]:
    if type == "float":
        return time()

    return int(time())


async def iterable_to_async_iterable(
    iterable: Iterable[bytes],
) -> AsyncIterable[bytes]:
    """Convert a synchronous iterable to an asynchronous iterable."""
    for item in iterable:
        yield item


def iterable_to_iterable(
    iterable: Iterable[bytes],
) -> Iterable[bytes]:
    return iterable


def async_iterable_to_iterable(iterable: AsyncIterable[bytes]) -> Iterable[bytes]:
    iterator = iterable.__aiter__()

    while True:
        try:
            chunk = from_thread.run(iterator.__anext__)
        except StopAsyncIteration:
            break

        yield chunk


def assert_present(val: T | None) -> T:
    if val is None:
        raise ValueError("Expected non-None value")
    return val
