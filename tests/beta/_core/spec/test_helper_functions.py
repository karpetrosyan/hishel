"""
Comprehensive tests for cache helper functions.

Tests verify compliance with various sections of RFC 9111
https://www.rfc-editor.org/rfc/rfc9111.html

Test Categories:
---------------
1. vary_headers_match - RFC 9111 Section 4.1
2. get_freshness_lifetime - RFC 9111 Section 4.2.1
3. allowed_stale - RFC 9111 Section 4.2.4
4. get_heuristic_freshness - RFC 9111 Section 4.2.2
5. get_age - RFC 9111 Section 4.2.3
6. make_conditional_request - RFC 9111 Section 4.3.1
7. exclude_unstorable_headers - RFC 9111 Section 3.1
8. refresh_response_headers - RFC 9111 Section 3.2
"""

import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional

import pytest

from hishel.beta import CompletePair, PairMeta, Request, Response
from hishel.beta._core._headers import Headers
from hishel.beta._core._spec import (
    allowed_stale,
    exclude_unstorable_headers,
    get_age,
    get_freshness_lifetime,
    get_heuristic_freshness,
    make_conditional_request,
    refresh_response_headers,
    vary_headers_match,
)

# =============================================================================
# Test Helpers
# =============================================================================


def create_request(
    method: str = "GET",
    url: str = "https://example.com/resource",
    headers: Optional[Dict[str, str]] = None,
) -> Request:
    """Helper to create a request."""
    return Request(
        method=method,
        url=url,
        headers=Headers(headers or {}),
        metadata={},
    )


def create_response(
    status_code: int = 200,
    headers: Optional[Dict[str, str]] = None,
) -> Response:
    """Helper to create a response."""
    return Response(
        status_code=status_code,
        headers=Headers(headers or {}),
        metadata={},
    )


def create_pair(
    request: Optional[Request] = None,
    response: Optional[Response] = None,
) -> CompletePair:
    """Helper to create a request-response pair."""
    return CompletePair(
        id=uuid.uuid4(),
        request=request or create_request(),
        response=response or create_response(),
        meta=PairMeta(),
        cache_key=b"test-cache-key",
    )


# =============================================================================
# Test Suite 1: vary_headers_match
# =============================================================================


class TestVaryHeadersMatch:
    """
    Tests for vary_headers_match function.

    RFC 9111 Section 4.1: Calculating Cache Keys
    """

    def test_no_vary_header_always_matches(self) -> None:
        """
        Test: Responses without Vary header match any request.

        RFC 9111 Section 4.1:
        Without a Vary header, the response doesn't vary based on request headers.
        """
        # Arrange
        request1 = create_request(headers={"accept": "application/json"})
        request2 = create_request(headers={"accept": "application/xml"})

        response = create_response()  # No Vary header
        pair = create_pair(request=request1, response=response)

        # Act & Assert
        assert vary_headers_match(request2, pair) is True

    def test_vary_header_with_matching_values(self) -> None:
        """
        Test: Matching Vary header values allow cache reuse.

        RFC 9111 Section 4.1:
        "all the presented request header fields nominated by that Vary field
        value match those fields in the original request"
        """
        # Arrange
        headers = {"accept": "application/json"}
        request1 = create_request(headers=headers)
        request2 = create_request(headers=headers)  # Same headers

        response = create_response(headers={"vary": "Accept"})
        pair = create_pair(request=request1, response=response)

        # Act & Assert
        assert vary_headers_match(request2, pair) is True

    def test_vary_header_with_non_matching_values(self) -> None:
        """
        Test: Non-matching Vary header values prevent cache reuse.
        """
        # Arrange
        request1 = create_request(headers={"accept": "application/json"})
        request2 = create_request(headers={"accept": "application/xml"})

        response = create_response(headers={"vary": "Accept"})
        pair = create_pair(request=request1, response=response)

        # Act & Assert
        assert vary_headers_match(request2, pair) is False

    def test_vary_star_always_fails(self) -> None:
        """
        Test: Vary: * always fails to match.

        RFC 9111 Section 4.1:
        "A stored response with a Vary header field value containing a member
        '*' always fails to match."
        """
        # Arrange
        request1 = create_request(headers={"accept": "application/json"})
        request2 = create_request(headers={"accept": "application/json"})

        response = create_response(headers={"vary": "*"})
        pair = create_pair(request=request1, response=response)

        # Act & Assert
        assert vary_headers_match(request2, pair) is False

    def test_vary_multiple_headers_all_must_match(self) -> None:
        """
        Test: With multiple Vary headers, all must match.

        RFC 9111 Section 4.1:
        All nominated headers must match for the response to be reusable.
        """
        # Arrange
        headers1 = {"accept": "application/json", "accept-encoding": "gzip"}
        headers2 = {
            "accept": "application/json",
            "accept-encoding": "gzip",  # All match
        }
        headers3 = {
            "accept": "application/json",
            "accept-encoding": "br",  # One doesn't match
        }

        request1 = create_request(headers=headers1)
        request2 = create_request(headers=headers2)
        request3 = create_request(headers=headers3)

        response = create_response(headers={"vary": "Accept, Accept-Encoding"})
        pair = create_pair(request=request1, response=response)

        # Act & Assert
        assert vary_headers_match(request2, pair) is True  # All match
        assert vary_headers_match(request3, pair) is False  # One differs

    def test_vary_with_missing_header_in_both_requests(self) -> None:
        """
        Test: Missing headers in both requests are considered matching.

        RFC 9111 Section 4.1:
        "If... a header field is absent from a request, it can only match
        another request if it is also absent there."
        """
        # Arrange
        request1 = create_request(headers={})  # No Accept-Language
        request2 = create_request(headers={})  # No Accept-Language

        response = create_response(headers={"vary": "Accept-Language"})
        pair = create_pair(request=request1, response=response)

        # Act & Assert
        assert vary_headers_match(request2, pair) is True

    def test_vary_with_header_present_in_one_request_only(self) -> None:
        """
        Test: Header present in one request but not the other is non-matching.
        """
        # Arrange
        request1 = create_request(headers={"accept-language": "en-US"})
        request2 = create_request(headers={})  # No Accept-Language

        response = create_response(headers={"vary": "Accept-Language"})
        pair = create_pair(request=request1, response=response)

        # Act & Assert
        assert vary_headers_match(request2, pair) is False


# =============================================================================
# Test Suite 2: get_freshness_lifetime
# =============================================================================


class TestGetFreshnessLifetime:
    """
    Tests for get_freshness_lifetime function.

    RFC 9111 Section 4.2.1: Calculating Freshness Lifetime
    """

    def test_max_age_directive(self) -> None:
        """
        Test: max-age directive provides freshness lifetime.

        RFC 9111 Section 5.2.2.1: max-age Response Directive
        """
        # Arrange
        response = create_response(headers={"cache-control": "max-age=3600"})

        # Act
        lifetime = get_freshness_lifetime(response, is_cache_shared=True)

        # Assert
        assert lifetime == 3600

    def test_s_maxage_overrides_max_age_for_shared_cache(self) -> None:
        """
        Test: s-maxage overrides max-age for shared caches.

        RFC 9111 Section 5.2.2.10: s-maxage Response Directive
        "for a shared cache, the maximum age specified by this directive
        overrides the maximum age specified by either the max-age directive
        or the Expires header field"
        """
        # Arrange
        response = create_response(headers={"cache-control": "max-age=3600, s-maxage=7200"})

        # Act
        shared_lifetime = get_freshness_lifetime(response, is_cache_shared=True)
        private_lifetime = get_freshness_lifetime(response, is_cache_shared=False)

        # Assert
        assert shared_lifetime == 7200  # s-maxage for shared
        assert private_lifetime == 3600  # max-age for private

    def test_expires_header_provides_freshness(self) -> None:
        """
        Test: Expires header provides freshness lifetime.

        RFC 9111 Section 5.3: Expires
        """
        # Arrange
        now = datetime.utcnow()
        expires = (now + timedelta(hours=2)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

        response = create_response(headers={"expires": expires, "date": date})

        # Act
        lifetime = get_freshness_lifetime(response, is_cache_shared=True)

        # Assert
        assert lifetime is not None
        # Should be approximately 2 hours (7200 seconds)
        assert 7190 <= lifetime <= 7210  # Allow small timing variance

    def test_max_age_takes_precedence_over_expires(self) -> None:
        """
        Test: max-age takes precedence over Expires.

        RFC 9111 Section 5.2.2.1:
        max-age is evaluated before Expires in the priority order.
        """
        # Arrange
        expires = (datetime.utcnow() + timedelta(hours=2)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        response = create_response(headers={"cache-control": "max-age=3600", "expires": expires})

        # Act
        lifetime = get_freshness_lifetime(response, is_cache_shared=True)

        # Assert
        assert lifetime == 3600  # max-age, not Expires

    def test_heuristic_freshness_when_no_explicit_expiration(self) -> None:
        """
        Test: Heuristic freshness is used when no explicit expiration exists.

        RFC 9111 Section 4.2.2: Calculating Heuristic Freshness
        """
        # Arrange
        last_modified = (datetime.utcnow() - timedelta(days=10)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        response = create_response(headers={"last-modified": last_modified})

        # Act
        lifetime = get_freshness_lifetime(response, is_cache_shared=True)

        # Assert
        assert lifetime is not None
        # Should be ~10% of 10 days = 1 day = 86400 seconds
        assert 80000 <= lifetime <= 90000

    def test_no_freshness_info_returns_none(self) -> None:
        """
        Test: Returns None when no freshness information is available.
        """
        # Arrange
        response = create_response()  # No caching headers

        # Act
        lifetime = get_freshness_lifetime(response, is_cache_shared=True)

        # Assert
        assert lifetime is None


# =============================================================================
# Test Suite 3: allowed_stale
# =============================================================================


class TestAllowedStale:
    """
    Tests for allowed_stale function.

    RFC 9111 Section 4.2.4: Serving Stale Responses
    """

    def test_allow_stale_option_false_disallows_stale(self) -> None:
        """
        Test: Configuration disallows serving stale responses.

        RFC 9111 Section 4.2.4:
        "A cache MUST NOT generate a stale response unless... doing so is
        explicitly permitted by the client or origin server"
        """
        # Arrange
        response = create_response(headers={"cache-control": "max-age=3600"})

        # Act
        result = allowed_stale(response, allow_stale_option=False)

        # Assert
        assert result is False

    def test_no_cache_directive_prevents_serving_stale(self) -> None:
        """
        Test: no-cache directive prevents serving stale responses.

        RFC 9111 Section 5.2.2.4: no-cache Response Directive
        """
        # Arrange
        response = create_response(headers={"cache-control": "max-age=3600, no-cache"})

        # Act
        result = allowed_stale(response, allow_stale_option=True)

        # Assert
        assert result is False

    def test_must_revalidate_prevents_serving_stale(self) -> None:
        """
        Test: must-revalidate directive prevents serving stale responses.

        RFC 9111 Section 5.2.2.2: must-revalidate Response Directive
        "once the response has become stale, a cache MUST NOT reuse that
        response to satisfy another request until it has been successfully
        validated by the origin"
        """
        # Arrange
        response = create_response(headers={"cache-control": "max-age=3600, must-revalidate"})

        # Act
        result = allowed_stale(response, allow_stale_option=True)

        # Assert
        assert result is False

    def test_allowed_stale_with_permissive_configuration(self) -> None:
        """
        Test: Stale responses allowed with permissive configuration.
        """
        # Arrange
        response = create_response(headers={"cache-control": "max-age=3600"})

        # Act
        result = allowed_stale(response, allow_stale_option=True)

        # Assert
        assert result is True


# =============================================================================
# Test Suite 4: get_heuristic_freshness
# =============================================================================


class TestGetHeuristicFreshness:
    """
    Tests for get_heuristic_freshness function.

    RFC 9111 Section 4.2.2: Calculating Heuristic Freshness
    """

    def test_heuristic_freshness_from_last_modified(self) -> None:
        """
        Test: Heuristic freshness calculated as 10% of age since Last-Modified.

        RFC 9111 Section 4.2.2:
        "caches are encouraged to use a heuristic expiration value that is no
        more than some fraction of the interval since that time. A typical
        setting of this fraction might be 10%."
        """
        # Arrange
        # Resource last modified 10 days ago
        last_modified = (datetime.utcnow() - timedelta(days=10)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        response = create_response(headers={"last-modified": last_modified})

        # Act
        freshness = get_heuristic_freshness(response)

        # Assert
        # 10% of 10 days = 1 day = 86400 seconds
        assert freshness is not None
        assert 80000 <= freshness <= 90000  # Allow timing variance

    def test_heuristic_freshness_capped_at_one_week(self) -> None:
        """
        Test: Heuristic freshness is capped at one week maximum.

        RFC 9111 Section 4.2.2:
        Conservative maximum to avoid excessive staleness.
        """
        # Arrange
        # Resource last modified 1000 days ago (would be 100 days * 0.1 = 10 days)
        last_modified = (datetime.utcnow() - timedelta(days=1000)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        response = create_response(headers={"last-modified": last_modified})

        # Act
        freshness = get_heuristic_freshness(response)

        # Assert
        ONE_WEEK = 604_800
        assert freshness == ONE_WEEK

    def test_no_last_modified_returns_none(self) -> None:
        """
        Test: Returns None when Last-Modified header is absent.
        """
        # Arrange
        response = create_response()  # No Last-Modified

        # Act
        freshness = get_heuristic_freshness(response)

        # Assert
        assert freshness is None


# =============================================================================
# Test Suite 5: get_age
# =============================================================================


class TestGetAge:
    """
    Tests for get_age function.

    RFC 9111 Section 4.2.3: Calculating Age
    """

    def test_age_calculation_from_date_header(self) -> None:
        """
        Test: Age is calculated from Date header.

        RFC 9111 Section 4.2.3:
        "A response's 'age' is the time that has passed since it was generated
        by, or successfully validated with, the origin server."
        """
        # Arrange
        # Response from 1 hour ago
        date = (datetime.utcnow() - timedelta(hours=1)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        response = create_response(headers={"date": date})

        # Act
        age = get_age(response)

        # Assert
        # Should be approximately 3600 seconds (1 hour)
        assert 3590 <= age <= 3610

    def test_age_is_zero_without_date_header(self) -> None:
        """
        Test: Age is 0 when Date header is missing.

        RFC 9110 Section 6.6.1: Date
        "A recipient with a clock that receives a response with an invalid Date
        header field value MAY replace that value with the time that response
        was received."
        """
        # Arrange
        response = create_response()  # No Date header

        # Act
        age = get_age(response)

        # Assert
        assert age == 0

    def test_age_is_zero_for_future_date(self) -> None:
        """
        Test: Age is 0 when Date is in the future (clock skew protection).
        """
        # Arrange
        # Date 1 hour in the future
        future_date = (datetime.utcnow() + timedelta(hours=1)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        response = create_response(headers={"date": future_date})

        # Act
        age = get_age(response)

        # Assert
        assert age == 0  # max(0, now - future) = 0


# =============================================================================
# Test Suite 6: make_conditional_request
# =============================================================================


class TestMakeConditionalRequest:
    """
    Tests for make_conditional_request function.

    RFC 9111 Section 4.3.1: Sending a Validation Request
    """

    def test_adds_if_none_match_from_etag(self) -> None:
        """
        Test: If-None-Match is added when response has ETag.

        RFC 9111 Section 4.3.1:
        "MUST send the relevant entity tags (using If-Match, If-None-Match, or
        If-Range) if the entity tags were provided in the stored response(s)
        being validated."
        """
        # Arrange
        request = create_request()
        response = create_response(headers={"etag": '"abc123"'})

        # Act
        conditional = make_conditional_request(request, response)

        # Assert
        assert "if-none-match" in conditional.headers
        assert conditional.headers["if-none-match"] == '"abc123"'

    def test_adds_if_modified_since_from_last_modified(self) -> None:
        """
        Test: If-Modified-Since is added when response has Last-Modified.

        RFC 9111 Section 4.3.1:
        "SHOULD send the Last-Modified value (using If-Modified-Since)"
        """
        # Arrange
        request = create_request()
        response = create_response(headers={"last-modified": "Mon, 01 Jan 2024 00:00:00 GMT"})

        # Act
        conditional = make_conditional_request(request, response)

        # Assert
        assert "if-modified-since" in conditional.headers
        assert conditional.headers["if-modified-since"] == "Mon, 01 Jan 2024 00:00:00 GMT"

    def test_adds_both_validators_when_available(self) -> None:
        """
        Test: Both If-None-Match and If-Modified-Since are added when available.

        RFC 9111 Section 4.3.1:
        Both validators should be sent if available for maximum compatibility.
        """
        # Arrange
        request = create_request()
        response = create_response(headers={"etag": '"abc123"', "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT"})

        # Act
        conditional = make_conditional_request(request, response)

        # Assert
        assert "if-none-match" in conditional.headers
        assert "if-modified-since" in conditional.headers

    def test_preserves_original_request_headers(self) -> None:
        """
        Test: Original request headers are preserved.
        """
        # Arrange
        request = create_request(headers={"accept": "application/json", "authorization": "Bearer token"})
        response = create_response(headers={"etag": '"abc123"'})

        # Act
        conditional = make_conditional_request(request, response)

        # Assert
        assert conditional.headers["accept"] == "application/json"
        assert conditional.headers["authorization"] == "Bearer token"
        assert "if-none-match" in conditional.headers

    def test_no_validators_returns_unchanged_request(self) -> None:
        """
        Test: Request is unchanged when response has no validators.
        """
        # Arrange
        request = create_request(headers={"accept": "application/json"})
        response = create_response()  # No ETag or Last-Modified

        # Act
        conditional = make_conditional_request(request, response)

        # Assert
        assert "if-none-match" not in conditional.headers
        assert "if-modified-since" not in conditional.headers
        assert conditional.headers["accept"] == "application/json"


# =============================================================================
# Test Suite 7: exclude_unstorable_headers
# =============================================================================


class TestExcludeUnstorableHeaders:
    """
    Tests for exclude_unstorable_headers function.

    RFC 9111 Section 3.1: Storing Header and Trailer Fields
    """

    @pytest.mark.parametrize(
        "header",
        [
            "connection",
            "keep-alive",
            "proxy-connection",
            "transfer-encoding",
            "upgrade",
            "te",
            "proxy-authenticate",
            "proxy-authorization",
        ],
    )
    def test_connection_specific_headers_excluded(self, header: str):
        """
        Test: Connection-specific headers are excluded.

        RFC 9110 Section 7.6.1: Connection-Specific Header Fields
        """
        # Arrange
        response = create_response(
            headers={header: "value", "cache-control": "max-age=3600", "content-type": "application/json"}
        )

        # Act
        filtered = exclude_unstorable_headers(response, is_cache_shared=True)

        # Assert
        assert header not in filtered.headers
        assert "cache-control" in filtered.headers
        assert "content-type" in filtered.headers

    def test_no_cache_directive_with_field_names(self) -> None:
        """
        Test: Headers listed in no-cache directive are excluded.

        RFC 9111 Section 5.2.2.4: no-cache Response Directive
        'no-cache="Set-Cookie"' means exclude Set-Cookie from cache.
        """
        # Arrange
        response = create_response(
            headers={
                "cache-control": 'no-cache="Set-Cookie"',
                "set-cookie": "session=abc123",
                "content-type": "application/json",
            }
        )

        # Act
        filtered = exclude_unstorable_headers(response, is_cache_shared=True)

        # Assert
        assert "set-cookie" not in filtered.headers
        assert "content-type" in filtered.headers

    def test_private_directive_with_field_names_in_shared_cache(self) -> None:
        """
        Test: Headers listed in private directive are excluded from shared cache.

        RFC 9111 Section 5.2.2.7: private Response Directive
        'private="Authorization"' means shared caches must exclude Authorization.
        """
        # Arrange
        response = create_response(
            headers={
                "cache-control": 'private="Authorization"',
                "authorization": "Bearer token",
                "content-type": "application/json",
            }
        )

        # Act
        shared_filtered = exclude_unstorable_headers(response, is_cache_shared=True)
        private_filtered = exclude_unstorable_headers(response, is_cache_shared=False)

        # Assert
        # Shared cache: Authorization excluded
        assert "authorization" not in shared_filtered.headers
        # Private cache: Authorization kept (private directive doesn't apply)
        assert "authorization" in private_filtered.headers

    def test_normal_headers_preserved(self) -> None:
        """
        Test: Normal cacheable headers are preserved.
        """
        # Arrange
        response = create_response(
            headers={
                "content-type": "application/json",
                "cache-control": "max-age=3600",
                "etag": '"abc123"',
                "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT",
            }
        )

        # Act
        filtered = exclude_unstorable_headers(response, is_cache_shared=True)

        # Assert
        assert "content-type" in filtered.headers
        assert "cache-control" in filtered.headers
        assert "etag" in filtered.headers
        assert "last-modified" in filtered.headers


# =============================================================================
# Test Suite 8: refresh_response_headers
# =============================================================================


class TestRefreshResponseHeaders:
    """
    Tests for refresh_response_headers function.

    RFC 9111 Section 3.2: Updating Stored Header Fields
    """

    def test_updates_cache_control_from_304(self) -> None:
        """
        Test: Cache-Control is updated from 304 response.

        RFC 9111 Section 3.2:
        "the cache MUST add each header field in the provided response to the
        stored response, replacing field values that are already present"
        """
        # Arrange
        stored = create_response(headers={"cache-control": "max-age=3600", "content-type": "application/json"})
        revalidation = create_response(status_code=304, headers={"cache-control": "max-age=7200"})

        # Act
        refreshed = refresh_response_headers(stored, revalidation)

        # Assert
        assert refreshed.headers["cache-control"] == "max-age=7200"

    def test_preserves_content_type_from_stored_response(self) -> None:
        """
        Test: Content-Type is NOT updated from 304 response.

        RFC 9111 Section 3.2:
        "Header fields that provide metadata about the message content and/or
        the selected representation (e.g., Content-Encoding, Content-Type,
        Content-Range) MUST NOT be updated"
        """
        # Arrange
        stored = create_response(headers={"content-type": "application/json", "cache-control": "max-age=3600"})
        revalidation = create_response(
            status_code=304,
            headers={
                "content-type": "text/plain",  # Should be ignored
                "cache-control": "max-age=7200",
            },
        )

        # Act
        refreshed = refresh_response_headers(stored, revalidation)

        # Assert
        assert refreshed.headers["content-type"] == "application/json"  # Preserved
        assert refreshed.headers["cache-control"] == "max-age=7200"  # Updated

    def test_preserves_content_encoding_from_stored_response(self) -> None:
        """
        Test: Content-Encoding is NOT updated from 304 response.
        """
        # Arrange
        stored = create_response(headers={"content-encoding": "gzip", "content-type": "application/json"})
        revalidation = create_response(
            status_code=304,
            headers={
                "content-encoding": "br",  # Should be ignored
                "cache-control": "max-age=7200",
            },
        )

        # Act
        refreshed = refresh_response_headers(stored, revalidation)

        # Assert
        assert refreshed.headers["content-encoding"] == "gzip"  # Preserved

    def test_preserves_content_range_from_stored_response(self) -> None:
        """
        Test: Content-Range is NOT updated from 304 response.
        """
        # Arrange
        stored = create_response(
            headers={"content-range": "bytes 0-1023/2048", "content-type": "application/octet-stream"}
        )
        revalidation = create_response(
            status_code=304,
            headers={
                "content-range": "bytes 1024-2047/2048",  # Should be ignored
                "cache-control": "max-age=7200",
            },
        )

        # Act
        refreshed = refresh_response_headers(stored, revalidation)

        # Assert
        assert refreshed.headers["content-range"] == "bytes 0-1023/2048"  # Preserved

    def test_updates_date_and_etag_from_304(self) -> None:
        """
        Test: Non-content headers like Date and ETag are updated.
        """
        # Arrange
        stored = create_response(
            headers={"date": "Mon, 01 Jan 2024 00:00:00 GMT", "etag": '"old123"', "content-type": "application/json"}
        )
        revalidation = create_response(
            status_code=304, headers={"date": "Mon, 01 Jan 2024 12:00:00 GMT", "etag": '"new456"'}
        )

        # Act
        refreshed = refresh_response_headers(stored, revalidation)

        # Assert
        assert refreshed.headers["date"] == "Mon, 01 Jan 2024 12:00:00 GMT"
        assert refreshed.headers["etag"] == '"new456"'
        assert refreshed.headers["content-type"] == "application/json"

    def test_excludes_unstorable_headers_after_merge(self) -> None:
        """
        Test: Unstorable headers are excluded after merging.

        Connection-specific headers in the 304 response should not be cached.
        """
        # Arrange
        stored = create_response(headers={"content-type": "application/json"})
        revalidation = create_response(
            status_code=304,
            headers={
                "cache-control": "max-age=7200",
                "connection": "keep-alive",  # Should be excluded
                "keep-alive": "timeout=5",  # Should be excluded
            },
        )

        # Act
        refreshed = refresh_response_headers(stored, revalidation)

        # Assert
        assert "cache-control" in refreshed.headers
        assert "connection" not in refreshed.headers
        assert "keep-alive" not in refreshed.headers
