from __future__ import annotations

from typing import cast

import msgpack

from hishel._core._headers import Headers
from hishel._core.models import Request, Response


def pack(request: Request, response: Response, /) -> bytes:
    return cast(
        bytes,
        msgpack.packb(
            {
                "request": {
                    "method": request.method,
                    "url": request.url,
                    "headers": request.headers._headers,
                },
                "response": {
                    "status_code": response.status_code,
                    "headers": response.headers._headers,
                },
            }
        ),
    )


def unpack(value: bytes, /) -> tuple[Request, Response]:
    data = msgpack.unpackb(value)
    return (
        Request(
            method=data["request"]["method"],
            url=data["request"]["url"],
            headers=Headers(data["request"]["headers"]),
        ),
        Response(
            status_code=data["response"]["status_code"],
            headers=Headers(data["response"]["headers"]),
        ),
    )
