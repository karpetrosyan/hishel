from __future__ import annotations

import abc
import typing as t
from dataclasses import dataclass, field
from typing import Generic

from hishel import Request, Response
from hishel._core._spec import (
    CacheOptions,
)

logger = __import__("logging").getLogger(__name__)

T = t.TypeVar("T", Request, Response)


class CachePolicy(abc.ABC):
    use_body_key: bool = False
    """Whether to include request body in cache key calculation."""


class BaseFilter(abc.ABC, Generic[T]):
    @abc.abstractmethod
    def needs_body(self) -> bool:
        pass

    @abc.abstractmethod
    def apply(self, item: T, body: bytes | None) -> bool:
        pass


@dataclass
class SpecificationPolicy(CachePolicy):
    """
    Caching policy that respects HTTP caching specification.
    """

    cache_options: CacheOptions = field(default_factory=CacheOptions)


@dataclass
class FilterPolicy(CachePolicy):
    """
    Caching policy that applies user-defined filtering logic.
    """

    request_filters: list[BaseFilter[Request]] = field(default_factory=list)
    response_filters: list[BaseFilter[Response]] = field(default_factory=list)
