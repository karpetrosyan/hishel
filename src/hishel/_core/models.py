from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import (
    AsyncIterator,
    Iterator,
)

from hishel._core._headers import Headers


@dataclass
class Request:
    method: str
    url: str
    headers: Headers = field(default_factory=lambda: Headers({}))


@dataclass
class Response:
    status_code: int
    headers: Headers = field(default_factory=lambda: Headers({}))
    stream: Iterator[bytes] | AsyncIterator[bytes] | None = None


@dataclass
class Entry:
    id: uuid.UUID
    request: Request
    response: Response
