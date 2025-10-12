"""
This module contains tests for Section 3 of RFC 9111
(Storing responses in caches) and all its sub-sections (3.x.x).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import replace
from typing import Any, Dict, Iterator, Optional

import pytest
from inline_snapshot import snapshot

from hishel.beta import (
    CacheMiss,
    CacheOptions,
    CompletePair,
    CouldNotBeStored,
    PairMeta,
    Request,
    Response,
    StoreAndUse,
)
from hishel.beta._core._headers import Headers


def create_fresh_pair(
    method: str = "GET",
    url: str = "https://example.com",
    response_headers: Optional[dict[str, str]] = None,
    request_headers: Optional[dict[str, str]] = None,
    response_status_code: int = 200,
    response_stream: Optional[Iterator[bytes]] = None,
) -> CompletePair:
    default_response_headers = {"Date": "Mon, 01 Jan 2024 00:00:00 GMT"}

    return CompletePair(
        id=uuid.uuid4(),
        request=Request(
            method=method,
            url=url,
            headers=Headers(request_headers) if request_headers is not None else Headers({}),
        ),
        response=Response(
            status_code=response_status_code,
            headers=Headers(default_response_headers)
            if response_headers is None
            else Headers({**default_response_headers, **response_headers}),
            stream=response_stream or iter([]),
        ),
        meta=PairMeta(created_at=time.time()),
        extra={},
        cache_key=b"test",
    )


class TestStoringResponsesInCaches:
    """
    Tests for Section 3 of RFC 9111 (Storing responses in caches)

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-storing-responses-in-caches
    """

    def test_simple_cachable_response(self) -> None:
        fresh_pair = create_fresh_pair()

        state = CacheMiss(
            pair_id=fresh_pair.id,
            request=fresh_pair.request,
            options=CacheOptions(),
        ).next(
            response=fresh_pair.response,
        )

        assert isinstance(state, StoreAndUse)

    def test_supported_methods_option(self, caplog: Any) -> None:
        fresh_pair = create_fresh_pair()

        with caplog.at_level("DEBUG"):
            state = CacheMiss(
                pair_id=fresh_pair.id,
                options=CacheOptions(
                    supported_methods=["OPTIONS"],
                ),
                request=fresh_pair.request,
            ).next(
                response=fresh_pair.response,
            )

        assert caplog.record_tuples == [
            (
                "hishel.core.spec",
                10,
                "Cannot store the response because the request method is not understood "
                "by the cache.See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.1.1",
            )
        ]

        assert isinstance(state, CouldNotBeStored)

    def test_not_final_response(self, caplog: Any) -> None:
        fresh_pair = create_fresh_pair()

        with caplog.at_level("DEBUG"):
            state = CacheMiss(
                pair_id=fresh_pair.id,
                request=fresh_pair.request,
                options=CacheOptions(),
            ).next(
                response=replace(fresh_pair, response=replace(fresh_pair.response, status_code=101)).response,
            )

        assert caplog.record_tuples == [
            (
                "hishel.core.spec",
                10,
                "Cannot store the response because the response status code (101) is "
                "not final. See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.2.1",
            )
        ]
        assert isinstance(state, CouldNotBeStored)

    def test_dont_understand(self, caplog: Any) -> None:
        fresh_pair = create_fresh_pair()

        with caplog.at_level("DEBUG"):
            state = CacheMiss(
                pair_id=fresh_pair.id,
                request=fresh_pair.request,
                options=CacheOptions(),
            ).next(
                response=replace(fresh_pair, response=replace(fresh_pair.response, status_code=304)).response,
            )

        assert caplog.record_tuples == snapshot(
            [
                (
                    "hishel.core.spec",
                    10,
                    "Cannot store the response because the cache does not understand how to cache the response.See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.3.2",
                )
            ]
        )
        assert isinstance(state, CouldNotBeStored)

    def test_no_store(self, caplog: Any) -> None:
        fresh_pair = create_fresh_pair()

        with caplog.at_level("DEBUG"):
            state = CacheMiss(
                pair_id=fresh_pair.id,
                request=fresh_pair.request,
                options=CacheOptions(),
            ).next(
                response=replace(
                    fresh_pair, response=replace(fresh_pair.response, headers=Headers({"Cache-Control": "no-store"}))
                ).response,
            )

        assert caplog.record_tuples == [
            (
                "hishel.core.spec",
                10,
                "Cannot store the response because the no-store cache directive is "
                "present in the response.See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.4.1",
            )
        ]
        assert isinstance(state, CouldNotBeStored)

    def test_private_response(self, caplog: Any) -> None:
        fresh_pair = create_fresh_pair()

        with caplog.at_level("DEBUG"):
            state = CacheMiss(
                pair_id=fresh_pair.id,
                options=CacheOptions(shared=True),
                request=fresh_pair.request,
            ).next(
                response=replace(
                    fresh_pair, response=replace(fresh_pair.response, headers=Headers({"Cache-Control": "private"}))
                ).response,
            )

        assert caplog.record_tuples == [
            (
                "hishel.core.spec",
                10,
                "Cannot store the response because the `private` response directive does not allow "
                "shared caches to store it. See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.5.1",
            )
        ]
        assert isinstance(state, CouldNotBeStored)

    def test_public_authorized_response(self, caplog: Any) -> None:
        fresh_pair = create_fresh_pair()

        with caplog.at_level("DEBUG"):
            state = CacheMiss(
                pair_id=fresh_pair.id,
                options=CacheOptions(shared=True),
                request=replace(fresh_pair.request, headers=Headers({"Authorization": "Bearer 12345"})),
            ).next(fresh_pair.response)

        assert caplog.record_tuples == snapshot(
            [
                (
                    "hishel.core.spec",
                    10,
                    "Cannot store the response because the cache is shared and the request contains an Authorization "
                    "header field. See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.6.1",
                )
            ]
        )
        assert isinstance(state, CouldNotBeStored)

    @pytest.mark.parametrize(
        "is_shared, response_kwargs",
        [
            pytest.param(
                False,
                {
                    "headers": Headers({"Cache-Control": "public"}),
                },
                id="contains a public response directive",
            ),
            pytest.param(
                False,
                {
                    "headers": Headers({"Cache-Control": "public"}),
                },
                id="a private response directive, if the cache is not shared",
            ),
            pytest.param(
                False,
                {
                    "headers": Headers({"Expires": str(int(time.time()))}),
                },
                id="an Expires header field",
            ),
            pytest.param(
                False,
                {
                    "headers": Headers({"Cache-Control": "max-age=3600"}),
                },
                id="a max-age response directive",
            ),
            pytest.param(
                True,
                {
                    "headers": Headers({"Cache-Control": "s-maxage=3600"}),
                },
                id="a s-maxage response directive with shared cache",
            ),
            pytest.param(
                False,
                {
                    "status_code": 404,
                },
                id="a heuristically cacheable status code",
            ),
        ],
    )
    def test_contains_required_components(self, caplog: Any, is_shared: bool, response_kwargs: Dict[str, Any]) -> None:
        """
        See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.7.1
        """
        fresh_pair = create_fresh_pair()

        fresh_pair = replace(
            fresh_pair,
            response=replace(
                fresh_pair.response,
                status_code=208,  # something that is not heuristically cacheable
            ),
        )

        with caplog.at_level("DEBUG"):
            state = CacheMiss(
                pair_id=fresh_pair.id,
                request=fresh_pair.request,
                options=CacheOptions(),
            ).next(
                response=replace(fresh_pair, response=replace(fresh_pair.response, headers=Headers({}))).response,
            )

        assert caplog.record_tuples == [
            (
                "hishel.core.spec",
                10,
                "Cannot store the response because it does not contain any of the required components. "
                "See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.7.1",
            )
        ]
        assert isinstance(state, CouldNotBeStored)

        with_required_component = replace(
            fresh_pair,
            response=replace(
                fresh_pair.response,
                **response_kwargs,
            ),
        )

        state = CacheMiss(
            pair_id=fresh_pair.id,
            request=fresh_pair.request,
            options=CacheOptions(),
        ).next(
            response=with_required_component.response,
        )

        assert isinstance(state, StoreAndUse)


def test_storing_header_and_trailer_fields() -> None:
    """
    Tests for Section 3.1 of RFC 9111 (Storing responses in caches)

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-storing-header-and-trailer-
    """

    # Test excluding standard unstorable headers
    fresh_pair = create_fresh_pair(
        response_headers={
            "Keep-Alive": "timeout=5",
            "TE": "trailers",
            "Transfer-Encoding": "chunked",
            "Upgrade": "websocket",
            "Proxy-Connection": "keep-alive",
            "Proxy-Authenticate": "Basic",
            "Proxy-Authorization": "Basic xyz",
            "Content-Type": "text/plain",
            "Cache-Control": "max-age=3600",
        }
    )

    state = CacheMiss(pair_id=fresh_pair.id, request=fresh_pair.request, options=CacheOptions()).next(
        response=fresh_pair.response
    )

    assert isinstance(state, StoreAndUse)
    assert "keep-alive" not in state.response.headers
    assert "te" not in state.response.headers
    assert "transfer-encoding" not in state.response.headers
    assert "upgrade" not in state.response.headers
    assert "proxy-connection" not in state.response.headers
    assert "proxy-authenticate" not in state.response.headers
    assert "proxy-authorization" not in state.response.headers
    assert "content-type" in state.response.headers
    assert "cache-control" in state.response.headers

    # Test excluding no-cache fields
    fresh_pair = create_fresh_pair(
        response_headers={
            "Cache-Control": 'no-cache="Content-Type, ETag"',
            "Content-Type": "text/plain",
            "ETag": "abc123",
            "Last-Modified": "Wed, 21 Oct 2015 07:28:00 GMT",
        }
    )

    state = CacheMiss(pair_id=fresh_pair.id, request=fresh_pair.request, options=CacheOptions()).next(
        response=fresh_pair.response
    )

    assert isinstance(state, StoreAndUse)
    assert "content-type" not in state.response.headers
    assert "etag" not in state.response.headers
    assert "last-modified" in state.response.headers

    # Test excluding private fields in shared cache
    fresh_pair = create_fresh_pair(
        response_headers={
            "Cache-Control": 'private="Set-Cookie, Authorization"',
            "Set-Cookie": "id=123",
            "Authorization": "Bearer xyz",
            "Content-Type": "text/plain",
        }
    )

    state = CacheMiss(pair_id=fresh_pair.id, request=fresh_pair.request, options=CacheOptions(shared=True)).next(
        response=fresh_pair.response
    )

    assert isinstance(state, StoreAndUse)
    assert "set-cookie" not in state.response.headers
    assert "authorization" not in state.response.headers
    assert "content-type" in state.response.headers
