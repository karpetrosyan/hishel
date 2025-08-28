"""
This module contains tests for Section 4 of RFC 9111
(Constructing Responses from Caches) and all its sub-sections (4.x.x).
"""

from __future__ import annotations

import time
import uuid
from dataclasses import replace
from typing import Optional
from unittest.mock import ANY

from time_machine import travel

from hishel import (
    CacheMiss,
    CacheOptions,
    CompletePair,
    FromCache,
    IdleClient,
    NeedRevalidation,
    NeedToBeUpdated,
    Request,
    Response,
)
from hishel._core._spec import (
    UpdatePartials,
    allowed_stale,
    create_idle_state,
    get_age,
    get_freshness_lifetime,
    vary_headers_match,
)
from hishel._core.models import PairMeta


def create_fresh_pair(
    method: str = "GET",
    url: str = "https://example.com",
    response_headers: Optional[dict[str, str]] = None,
    request_headers: Optional[dict[str, str]] = None,
) -> CompletePair:
    default_response_headers = {"Date": "Mon, 01 Jan 2024 00:00:00 GMT"}
    return CompletePair(
        id=uuid.uuid4(),
        request=Request(
            method=method,
            url=url,
            raw_headers=request_headers if request_headers is not None else {},
            stream=[],
        ),
        response=Response(
            status_code=200,
            raw_headers=default_response_headers
            if response_headers is None
            else {**default_response_headers, **response_headers},
            stream=[],
        ),
        meta=PairMeta(created_at=time.time()),
        cache_key="example.com",
        complete_stream=True,
    )


class TestConstructingResponsesFromCache:
    """
    Tests for Section 4 of RFC 9111 (Constructing Responses from Caches)

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-constructing-responses-from
    """

    @travel("2024-01-01 00:00:00")
    def test_different_urls_are_filtered_out(self) -> None:
        """
        When presented with a request, a cache MUST NOT reuse a stored response unless:

        - the presented target URI (Section 7.1 of [HTTP]) and that of the stored response match, and
        """
        fresh_pair = create_fresh_pair()

        idle_state = create_idle_state("client")

        state = idle_state.next(
            request=replace(fresh_pair.request, url="https://example.com/other"),
            associated_pairs=[fresh_pair],
        )

        assert isinstance(state, UpdatePartials)
        assert isinstance(state.next(), CacheMiss)

    @travel("2024-01-01 00:00:00")
    def test_different_methods_are_filtered_out(self) -> None:
        """
        When presented with a request, a cache MUST NOT reuse a stored response unless:

        - the request method associated with the stored response allows it to be used for the presented request, and
        """
        fresh_pair = create_fresh_pair()

        idle_state = create_idle_state("client")

        state = idle_state.next(
            request=replace(fresh_pair.request, method="HEAD"),
            associated_pairs=[fresh_pair],
        )

        assert isinstance(state, UpdatePartials)
        assert isinstance(state.next(), CacheMiss)

    @travel("2024-01-01 00:00:00")
    def test_different_vary_headers_are_filtered_out(self) -> None:
        """
        When presented with a request, a cache MUST NOT reuse a stored response unless:

        - request header fields nominated by the stored response (if any) match those presented (see Section 4.1)
        """
        fresh_pair = create_fresh_pair(
            response_headers={"Vary": "Accept-Encoding"}, request_headers={"Accept-Encoding": "gzip"}
        )

        idle_state = create_idle_state("client")

        state = idle_state.next(
            request=replace(fresh_pair.request, raw_headers={"Accept-Encoding": "br"}),
            associated_pairs=[fresh_pair],
        )

        assert isinstance(state, UpdatePartials)
        assert isinstance(state.next(), CacheMiss)

    @travel("2024-01-01 00:00:00")
    def test_response_with_no_cache_control_is_filtered_out(self) -> None:
        """
        When presented with a request, a cache MUST NOT reuse a stored response unless:

        - the stored response does not contain the no-cache directive (Section 5.2.2.4),
        unless it is successfully validated (Section 4.3)
        """
        fresh_pair = create_fresh_pair(response_headers={"Cache-Control": "no-cache"})

        idle_state = create_idle_state("client")

        state = idle_state.next(
            request=fresh_pair.request,
            associated_pairs=[fresh_pair],
        )

        assert isinstance(state, UpdatePartials)
        assert isinstance(state.next(), CacheMiss)

    @travel("2024-01-01 00:00:00")
    def test_response_returned_from_cache_if_fresh(self) -> None:
        fresh_pair = create_fresh_pair(response_headers={"Cache-Control": "max-age=3600"})

        idle_state = create_idle_state("client")

        state = idle_state.next(
            request=fresh_pair.request,
            associated_pairs=[fresh_pair],
        )
        assert isinstance(state, UpdatePartials)
        next_state: CacheMiss | FromCache | NeedRevalidation = state.next()
        assert isinstance(next_state, FromCache)
        assert "age" in next_state.pair.response.headers

    @travel("2025-01-01 00:00:00")
    def test_stale_response_returned_from_cache(self) -> None:
        fresh_pair = create_fresh_pair(response_headers={"Cache-Control": "max-age=0"})

        idle_state = IdleClient(options=CacheOptions(allow_stale=True))

        state = idle_state.next(
            request=fresh_pair.request,
            associated_pairs=[fresh_pair],
        )

        assert isinstance(state, UpdatePartials)
        next_state = state.next()
        assert isinstance(next_state, FromCache)

    @travel("2025-01-01 00:00:00")
    def test_response_needs_revalidation_if_not_fresh(self) -> None:
        fresh_pair = create_fresh_pair(response_headers={"Cache-Control": "max-age=0"})

        idle_state = create_idle_state("client")

        state = idle_state.next(
            request=fresh_pair.request,
            associated_pairs=[fresh_pair],
        )

        assert isinstance(state, UpdatePartials)
        next_state = state.next()
        assert isinstance(next_state, NeedRevalidation)
        assert next_state.request == fresh_pair.request


class TestCalculatingFreshnessLifetime:
    """
    Tests for Section 4.2.1 of RFC 9111 (Calculating Freshness Lifetime)

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2.1
    """

    def test_shared_with_s_maxage(self) -> None:
        response = Response(status_code=200, stream=[], raw_headers={"Cache-Control": "s-maxage=3600"})

        assert get_freshness_lifetime(response, True) == 3600

    def test_shared_with_max_age(self) -> None:
        response = Response(status_code=200, stream=[], raw_headers={"Cache-Control": "max-age=3600"})

        assert get_freshness_lifetime(response, True) == 3600

    def test_with_expires_and_date(self) -> None:
        response = Response(
            status_code=200,
            stream=[],
            raw_headers={
                "Expires": "Wed, 21 Oct 2015 08:28:00 GMT",
                "Date": "Wed, 21 Oct 2015 07:28:00 GMT",
            },
        )

        assert get_freshness_lifetime(response, True) == 3600

    @travel("2015-10-21 6:00:00 GMT")
    def test_with_expires_without_date(self) -> None:
        response = Response(
            status_code=200,
            stream=[],
            raw_headers={
                "Expires": "Wed, 21 Oct 2015 7:00:00 GMT",
            },
        )

        assert get_freshness_lifetime(response, True) == 3600

    def test_heuristic(self) -> None:
        response = Response(
            status_code=200,
            stream=[],
            raw_headers={
                "Last-Modified": "Wed, 21 Oct 2015 07:00:00 GMT",
                "Date": "Wed, 21 Oct 2015 08:00:00 GMT",
            },
        )

        assert isinstance(get_freshness_lifetime(response, True), int)

    def test_no_freshness_info(self) -> None:
        response = Response(
            status_code=200,
            stream=[],
            raw_headers={},
        )

        assert get_freshness_lifetime(response, True) is None


class TestHandlingRevalidationResponse:
    """
    Tests for Section 4.3.3 of RFC 9111 (Handling a Validation Response)

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-handling-a-validation-respo
    """

    @travel("2024-01-01 00:00:00")
    def test_304_handled_correctly(self) -> None:
        fresh_pair = create_fresh_pair(response_headers={"etag": "12345"})
        state = NeedRevalidation(
            request=fresh_pair.request, revalidating_pairs=[fresh_pair], options=CacheOptions()
        ).next(
            replace(
                fresh_pair,
                response=replace(fresh_pair.response, status_code=304, raw_headers={"X-SomeHeader": "somevalue"}),
            ),
        )

        assert isinstance(state, NeedToBeUpdated)
        assert state.updating_pairs[0] == CompletePair(
            id=fresh_pair.id,
            request=Request(
                method="GET",
                url="https://example.com",
                stream=[],
            ),
            response=replace(
                fresh_pair.response, raw_headers={**fresh_pair.response.headers, "X-SomeHeader": "somevalue"}
            ),
            meta=PairMeta(created_at=ANY),
            cache_key="example.com",
            extra={},
            complete_stream=True,
        )

    def test_2xx_handled_correctly(self):
        fresh_pair = create_fresh_pair(response_headers={"etag": "12345"})
        state = NeedRevalidation(
            request=fresh_pair.request, revalidating_pairs=[fresh_pair], options=CacheOptions()
        ).next(
            replace(
                fresh_pair,
                response=replace(fresh_pair.response, status_code=200),
            )
        )

        assert isinstance(state, CacheMiss)

    def test_5xx_handled_correctly(self):
        fresh_pair = create_fresh_pair(response_headers={"etag": "12345"})
        state = NeedRevalidation(
            request=fresh_pair.request, revalidating_pairs=[fresh_pair], options=CacheOptions()
        ).next(
            replace(
                fresh_pair,
                response=replace(fresh_pair.response, status_code=500),
            )
        )

        assert isinstance(state, CacheMiss)


class TestSendingValidationRequest:
    """
    4.3.1. Sending a Validation Request

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-sending-a-validation-reques
    """


def test_sending_validation_request():
    """
    Tests for Section 4.3.1  of RFC 9111 (Sending a Validation Request)

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-sending-a-validation-reques
    """


class TestVaryHeadersMatch:
    """
    Tests for 4.1 Calculating cache key with the vary header value

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#caching.negotiated.responses
    """

    def test_vary_headers_match(self) -> None:
        fresh_pair = create_fresh_pair(
            response_headers={"Vary": "Accept-Encoding, User-Agent"},
            request_headers={"Accept-Encoding": "gzip", "User-Agent": "my-agent"},
        )

        original_request = Request(
            method="GET",
            url="https://example.com",
            raw_headers={"Accept-Encoding": "gzip", "User-Agent": "my-agent"},
            stream=[],
        )

        assert vary_headers_match(original_request, associated_pair=fresh_pair) is True

    def test_vary_containing_asterisk(self) -> None:
        fresh_pair = create_fresh_pair(
            response_headers={"Vary": "*"},
            request_headers={"Accept-Encoding": "gzip", "User-Agent": "my-agent"},
        )

        original_request = Request(
            method="GET",
            url="https://example.com",
            raw_headers={"Accept-Encoding": "gzip", "User-Agent": "my-agent"},
            stream=[],
        )

        assert vary_headers_match(original_request, associated_pair=fresh_pair) is False


class TestGetAge:
    """
    Tests for Section 4.2.3 of RFC 9111 (Calculating Age)

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-calculating-age
    """

    def test_without_date(self) -> None:
        response = Response(
            status_code=200,
            stream=[],
            raw_headers={},
        )

        assert get_age(response) == 0

    @travel("2015-10-21 09:00:00 GMT")
    def test_with_date(self) -> None:
        response = Response(
            status_code=200,
            stream=[],
            raw_headers={
                "Date": "Wed, 21 Oct 2015 08:00:00 GMT",
            },
        )

        assert get_age(response) == 3600


def test_allowed_stale() -> None:
    """
    Tests for Section 4.2.4 of RFC 9111 (Serving Stale Responses)

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-serving-stale-responses
    """
    assert allowed_stale(response=Response(status_code=200, stream=[], raw_headers={}), allow_stale_option=True) is True
    assert (
        allowed_stale(response=Response(status_code=200, stream=[], raw_headers={}), allow_stale_option=False) is False
    )
    assert (
        allowed_stale(
            response=Response(status_code=200, stream=[], raw_headers={"Cache-Control": "no-cache"}),
            allow_stale_option=True,
        )
        is False
    )
    assert (
        allowed_stale(
            response=Response(status_code=200, stream=[], raw_headers={"Cache-Control": "must-revalidate"}),
            allow_stale_option=True,
        )
        is False
    )
