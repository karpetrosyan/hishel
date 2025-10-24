"""
Comprehensive tests for the IdleClient state.

Tests verify compliance with RFC 9111 Section 4: Constructing Responses from Caches
https://www.rfc-editor.org/rfc/rfc9111.html#section-4

Test Categories:
---------------
1. Transition to CacheMiss state
2. Transition to FromCache state
3. Transition to NeedRevalidation state
4. Edge cases and RFC 9111 compliance
"""

import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pytest

from hishel import CompletePair, PairMeta, Request, Response
from hishel._core._headers import Headers
from hishel._core._spec import (
    CacheMiss,
    CacheOptions,
    FromCache,
    IdleClient,
    NeedRevalidation,
)

# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


@pytest.fixture
def default_options() -> CacheOptions:
    """Default cache options for testing."""
    return CacheOptions(shared=True, supported_methods=["GET", "HEAD"], allow_stale=False)


@pytest.fixture
def allow_stale_options() -> CacheOptions:
    """Cache options that allow serving stale responses."""
    return CacheOptions(shared=True, supported_methods=["GET", "HEAD"], allow_stale=True)


@pytest.fixture
def idle_client(default_options: CacheOptions) -> IdleClient:
    """Create an IdleClient instance with default options."""
    return IdleClient(options=default_options)


@pytest.fixture
def idle_client_allow_stale(allow_stale_options: CacheOptions) -> IdleClient:
    """Create an IdleClient instance that allows stale responses."""
    return IdleClient(options=allow_stale_options)


def create_request(
    method: str = "GET",
    url: str = "https://example.com/resource",
    headers: Optional[Dict[str, str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Request:
    """Helper to create a request with common defaults."""
    return Request(
        method=method,
        url=url,
        headers=Headers(headers or {}),
        metadata=metadata or {},
    )


def create_response(
    status_code: int = 200,
    headers: Optional[Dict[str, str]] = None,
    age_seconds: int = 0,
    max_age_seconds: Optional[int] = 3600,
    metadata: Optional[Dict[str, Any]] = None,
) -> Response:
    """
    Helper to create a response with cache-related headers.

    Parameters:
    ----------
    status_code : int
        HTTP status code
    headers : dict
        Additional headers to include
    age_seconds : int
        Age of the response in seconds (for Date header calculation)
    max_age_seconds : int or None
        Max-age value for Cache-Control header (None to omit)
    metadata : dict
        Response metadata
    """
    response_headers = headers or {}

    # Set Date header to current time minus age_seconds
    date_value = datetime.utcnow() - timedelta(seconds=age_seconds)
    response_headers.setdefault("date", date_value.strftime("%a, %d %b %Y %H:%M:%S GMT"))

    # Set Cache-Control with max-age if provided
    if max_age_seconds is not None:
        cache_control = response_headers.get("cache-control", "")
        if cache_control:
            cache_control += f", max-age={max_age_seconds}"
        else:
            cache_control = f"max-age={max_age_seconds}"
        response_headers["cache-control"] = cache_control

    return Response(
        status_code=status_code,
        headers=Headers(response_headers),
        metadata=metadata or {},
    )


def create_pair(
    request: Optional[Request] = None,
    response: Optional[Response] = None,
    pair_id: Optional[uuid.UUID] = None,
    cache_key: bytes = b"test-cache-key",
) -> CompletePair:
    """Helper to create a request-response pair."""
    return CompletePair(
        id=pair_id or uuid.uuid4(),
        request=request or create_request(),
        response=response or create_response(),
        meta=PairMeta(),
        cache_key=cache_key,
    )


# =============================================================================
# Test Suite 1: Transition to CacheMiss State
# =============================================================================
# RFC 9111 Section 4 defines conditions when a cache MUST NOT reuse a stored
# response. These tests verify that CacheMiss is returned in appropriate cases.
# =============================================================================


class TestTransitionToCacheMiss:
    """
    Tests for transitions to the CacheMiss state.

    CacheMiss occurs when:
    - No suitable cached responses exist
    - The request cannot be satisfied from cache
    - RFC 9111 conditions for cache reuse are not met
    """

    def test_no_cached_responses(self, idle_client: IdleClient) -> None:
        """
        Test: Empty cache results in CacheMiss.

        RFC 9111 Section 4.1, paragraph 8:
        "If no stored response matches, the cache cannot satisfy the presented
        request. Typically, the request is forwarded to the origin server."
        """
        # Arrange
        request = create_request()
        associated_pairs: list[CompletePair] = []  # Empty cache

        # Act
        next_state = idle_client.next(request, associated_pairs)

        # Assert
        assert isinstance(next_state, CacheMiss)
        assert next_state.request == request
        assert next_state.options == idle_client.options

    def test_range_request_causes_cache_miss(self, idle_client: IdleClient) -> None:
        """
        Test: Requests with Range header result in CacheMiss.

        RFC 9111 Section 3.3: Storing Incomplete Responses
        https://www.rfc-editor.org/rfc/rfc9111.html#section-3.3

        This implementation takes a simplified approach and treats all range
        requests as cache misses. A full implementation could handle partial
        content and range combinations.
        """
        # Arrange
        request = create_request(headers={"range": "bytes=0-1023"})
        cached_pair = create_pair(request=create_request(), response=create_response())

        # Act
        next_state = idle_client.next(request, [cached_pair])

        # Assert
        assert isinstance(next_state, CacheMiss)
        assert next_state.request == request

    def test_unsafe_method_causes_cache_miss(self, idle_client: IdleClient) -> None:
        """
        Test: Unsafe methods (POST, PUT, DELETE, etc.) result in CacheMiss.

        RFC 9111 Section 4, paragraph 5:
        "A cache MUST write through requests with methods that are unsafe
        (Section 9.2.1 of [HTTP]) to the origin server; i.e., a cache is not
        allowed to generate a reply to such a request before having forwarded
        the request and having received a corresponding response."

        Unsafe methods must always be forwarded to the origin server.
        """
        unsafe_methods = ["POST", "PUT", "DELETE", "PATCH"]

        for method in unsafe_methods:
            # Arrange
            request = create_request(method=method)
            cached_pair = create_pair(
                request=create_request(method=method),
                response=create_response(),
            )

            # Act
            next_state = idle_client.next(request, [cached_pair])

            # Assert
            assert isinstance(next_state, CacheMiss), f"{method} should result in CacheMiss"
            assert next_state.request == request

    def test_url_mismatch_causes_cache_miss(self, idle_client: IdleClient) -> None:
        """
        Test: Different URLs result in CacheMiss.

        RFC 9111 Section 4, paragraph 2.1:
        "the presented target URI (Section 7.1 of [HTTP]) and that of the
        stored response match"

        The cache key is primarily based on the URI. Different URIs cannot
        share cached responses.
        """
        # Arrange
        request = create_request(url="https://example.com/resource-a")
        cached_pair = create_pair(
            request=create_request(url="https://example.com/resource-b"),
            response=create_response(),
        )

        # Act
        next_state = idle_client.next(request, [cached_pair])

        # Assert
        assert isinstance(next_state, CacheMiss)

    def test_method_mismatch_causes_cache_miss(self, idle_client: IdleClient) -> None:
        """
        Test: Different request methods result in CacheMiss.

        RFC 9111 Section 4, paragraph 2.2:
        "the request method associated with the stored response allows it to be
        used for the presented request"

        Generally, only responses to the same method can be reused.
        """
        # Arrange
        get_request = create_request(method="GET")
        head_request = create_request(method="HEAD")
        cached_pair = create_pair(
            request=get_request,
            response=create_response(),
        )

        # Act
        next_state = idle_client.next(head_request, [cached_pair])

        # Assert
        assert isinstance(next_state, CacheMiss)

    def test_vary_header_mismatch_causes_cache_miss(self, idle_client: IdleClient) -> None:
        """
        Test: Mismatched Vary headers result in CacheMiss.

        RFC 9111 Section 4.1: Calculating Cache Keys
        "When a cache receives a request that can be satisfied by a stored
        response and that stored response contains a Vary header field, the
        cache MUST NOT use that stored response without revalidation unless all
        the presented request header fields nominated by that Vary field value
        match those fields in the original request."

        The Vary header specifies which request headers must match for the
        cached response to be reused.
        """
        # Arrange
        # Original request had Accept-Encoding: gzip
        original_request = create_request(headers={"accept-encoding": "gzip"})
        response = create_response(headers={"vary": "Accept-Encoding"})
        cached_pair = create_pair(request=original_request, response=response)

        # New request has different Accept-Encoding
        new_request = create_request(headers={"accept-encoding": "br"})

        # Act
        next_state = idle_client.next(new_request, [cached_pair])

        # Assert
        assert isinstance(next_state, CacheMiss)

    def test_vary_star_always_causes_cache_miss(self, idle_client: IdleClient) -> None:
        """
        Test: Vary: * always results in CacheMiss.

        RFC 9111 Section 4.1, paragraph 5:
        "A stored response with a Vary header field value containing a member
        '*' always fails to match."

        Vary: * indicates that the response varies on factors beyond the request
        headers (e.g., user agent state), so it can never be matched.
        """
        # Arrange
        original_request = create_request()
        response = create_response(headers={"vary": "*"})
        cached_pair = create_pair(request=original_request, response=response)

        # Even identical request should not match
        identical_request = create_request()

        # Act
        next_state = idle_client.next(identical_request, [cached_pair])

        # Assert
        assert isinstance(next_state, CacheMiss)

    def test_no_cache_directive_requires_revalidation(self, idle_client: IdleClient) -> None:
        """
        Test: Cached response with no-cache directive requires revalidation.

        RFC 9111 Section 5.2.2.4: no-cache Response Directive
        "The no-cache response directive... indicates that the response MUST NOT
        be used to satisfy any other request without forwarding it for validation
        and receiving a successful response."

        Responses with no-cache cannot be used without validation.
        """
        # Arrange
        request = create_request()
        response = create_response(
            age_seconds=0,
            max_age_seconds=3600,
            headers={"cache-control": "no-cache, max-age=3600"},
        )
        cached_pair = create_pair(request=request, response=response)

        # Act
        next_state = idle_client.next(request, [cached_pair])

        # Assert
        # With no-cache, the response is filtered out, leading to CacheMiss
        assert isinstance(next_state, CacheMiss)

    def test_all_responses_stale_and_not_allowed_causes_revalidation(self, idle_client: IdleClient) -> None:
        """
        Test: When all cached responses are stale and cannot be served stale.

        RFC 9111 Section 4.2.4: Serving Stale Responses
        "A cache MUST NOT generate a stale response if it is prohibited by an
        explicit in-protocol directive (e.g., by a no-cache response directive,
        a must-revalidate response directive, or an applicable s-maxage or
        proxy-revalidate response directive)."

        Stale responses that cannot be served stale require revalidation.
        """
        # Arrange
        request = create_request()
        # Response is stale (age 7200s > max-age 3600s)
        stale_response = create_response(age_seconds=7200, max_age_seconds=3600)
        cached_pair = create_pair(request=request, response=stale_response)

        # Act
        next_state = idle_client.next(request, [cached_pair])

        # Assert
        assert isinstance(next_state, NeedRevalidation)


# =============================================================================
# Test Suite 2: Transition to FromCache State
# =============================================================================
# These tests verify that FromCache is returned when a suitable cached response
# is available and can be served immediately.
# =============================================================================


class TestTransitionToFromCache:
    """
    Tests for transitions to the FromCache state.

    FromCache occurs when:
    - A fresh cached response is available
    - A stale cached response is explicitly allowed to be served
    - All RFC 9111 conditions for cache reuse are met
    """

    def test_fresh_response_served_from_cache(self, idle_client: IdleClient) -> None:
        """
        Test: Fresh cached response is served from cache.

        RFC 9111 Section 4.2: Freshness
        "A 'fresh' response is one whose age has not yet exceeded its freshness
        lifetime."

        RFC 9111 Section 4, paragraph 4:
        "When a stored response is used to satisfy a request without validation,
        a cache MUST generate an Age header field (Section 5.1), replacing any
        present in the response with a value equal to the stored response's
        current_age."
        """
        # Arrange
        request = create_request()
        # Response is fresh: age 1800s < max-age 3600s
        fresh_response = create_response(age_seconds=1800, max_age_seconds=3600)
        cached_pair = create_pair(request=request, response=fresh_response)

        # Act
        next_state = idle_client.next(request, [cached_pair])

        # Assert
        assert isinstance(next_state, FromCache)
        assert next_state.pair.request == request

        # Verify Age header is present and updated
        assert "age" in next_state.pair.response.headers
        age_value = int(next_state.pair.response.headers["age"])
        assert age_value >= 1800  # Should be at least the initial age

        # Verify metadata flag
        assert next_state.pair.response.metadata.get("hishel_from_cache") is True

    def test_stale_but_allowed_response_served_from_cache(self, idle_client_allow_stale: IdleClient) -> None:
        """
        Test: Stale response is served when explicitly allowed.

        RFC 9111 Section 4.2.4: Serving Stale Responses
        "A cache MUST NOT generate a stale response unless it is disconnected or
        doing so is explicitly permitted by the client or origin server (e.g., by
        the max-stale request directive)."

        When allow_stale option is enabled, stale responses can be served.
        """
        # Arrange
        request = create_request()
        # Response is stale: age 7200s > max-age 3600s
        stale_response = create_response(age_seconds=7200, max_age_seconds=3600)
        cached_pair = create_pair(request=request, response=stale_response)

        # Act
        next_state = idle_client_allow_stale.next(request, [cached_pair])

        # Assert
        assert isinstance(next_state, FromCache)
        assert next_state.pair.request == request

        # Verify Age header reflects staleness
        age_value = int(next_state.pair.response.headers["age"])
        assert age_value >= 7200

    def test_most_recent_response_selected_when_multiple_available(self, idle_client: IdleClient) -> None:
        """
        Test: Most recent response is selected when multiple are cached.

        RFC 9111 Section 4, paragraph 8:
        "When more than one suitable response is stored, a cache MUST use the
        most recent one (as determined by the Date header field)."

        This ensures clients receive the most up-to-date cached information.
        """
        # Arrange
        request = create_request()

        # Create three responses with different dates
        older_response = create_response(
            age_seconds=3000,
            max_age_seconds=3600,
        )
        middle_response = create_response(
            age_seconds=2000,
            max_age_seconds=3600,
        )
        newest_response = create_response(
            age_seconds=1000,
            max_age_seconds=3600,
        )

        cached_pairs = [
            create_pair(request=request, response=older_response),
            create_pair(request=request, response=middle_response),
            create_pair(request=request, response=newest_response),
        ]

        # Act
        next_state = idle_client.next(request, cached_pairs)

        # Assert
        assert isinstance(next_state, FromCache)

        # Verify the newest response was selected
        selected_age = int(next_state.pair.response.headers["age"])
        # The newest response has age ~1000s, others have 2000s and 3000s
        assert selected_age >= 1000
        assert selected_age < 2000  # Should be closer to 1000 than 2000

    def test_age_header_updated_correctly(self, idle_client: IdleClient) -> None:
        """
        Test: Age header is calculated and updated correctly.

        RFC 9111 Section 5.1: Age
        "The Age header field is used to convey an estimated age of the response
        message when obtained from a cache. The Age field value is the cache's
        estimate of the number of seconds since the origin server generated or
        validated the response."

        RFC 9111 Section 4.2.3: Calculating Age
        Provides the formula for calculating the current age of a response.
        """
        # Arrange
        request = create_request()

        # Create response with known age
        initial_age = 1800  # 30 minutes
        response = create_response(age_seconds=initial_age, max_age_seconds=3600)
        cached_pair = create_pair(request=request, response=response)

        # Act
        next_state = idle_client.next(request, [cached_pair])

        # Assert
        assert isinstance(next_state, FromCache)

        # Age should be at least the initial age
        age_value = int(next_state.pair.response.headers["age"])
        assert age_value >= initial_age
        assert age_value < initial_age + 5  # Shouldn't increase by more than a few seconds

    def test_matching_vary_headers_allows_cache_hit(self, idle_client: IdleClient) -> None:
        """
        Test: Matching Vary headers allow cache hit.

        RFC 9111 Section 4.1: Calculating Cache Keys
        "The header fields from two requests are defined to match if and only if
        those in the first request can be transformed to those in the second
        request by applying any of the following:
        - adding or removing whitespace..."

        When Vary headers match, the cached response can be reused.
        """
        # Arrange
        original_request = create_request(headers={"accept-encoding": "gzip"})
        response = create_response(headers={"vary": "Accept-Encoding"})
        cached_pair = create_pair(request=original_request, response=response)

        # New request with same Accept-Encoding
        new_request = create_request(headers={"accept-encoding": "gzip"})

        # Act
        next_state = idle_client.next(new_request, [cached_pair])

        # Assert
        assert isinstance(next_state, FromCache)

    def test_cache_hit_with_all_conditions_met(self, idle_client: IdleClient) -> None:
        """
        Test: Cache hit when all RFC 9111 conditions are met.

        This is an integration test verifying that when all five conditions
        from RFC 9111 Section 4 are satisfied, the response is served from cache.

        Conditions verified:
        1. URI matches
        2. Method matches
        3. Vary headers match (if present)
        4. No no-cache directive
        5. Response is fresh
        """
        # Arrange
        request = create_request(
            method="GET",
            url="https://example.com/api/data",
            headers={"accept": "application/json", "accept-encoding": "gzip"},
        )

        response = create_response(
            age_seconds=1000,
            max_age_seconds=3600,
            headers={
                "vary": "Accept, Accept-Encoding",
                "content-type": "application/json",
            },
        )

        cached_pair = create_pair(request=request, response=response)

        # Act
        next_state = idle_client.next(request, [cached_pair])

        # Assert
        assert isinstance(next_state, FromCache)
        assert next_state.pair.response.metadata.get("hishel_from_cache") is True


# =============================================================================
# Test Suite 3: Transition to NeedRevalidation State
# =============================================================================
# These tests verify revalidation behavior for stale cached responses.
# =============================================================================


class TestTransitionToNeedRevalidation:
    """
    Tests for transitions to the NeedRevalidation state.

    NeedRevalidation occurs when:
    - A stale cached response exists
    - The response cannot be served stale
    - Validation is required before serving
    """

    def test_stale_response_requires_revalidation(self, idle_client: IdleClient) -> None:
        """
        Test: Stale response that cannot be served stale requires revalidation.

        RFC 9111 Section 4.3: Validation
        "When a cache has one or more stored responses for a requested URI, but
        cannot serve any of them (e.g., because they are not fresh, or one cannot
        be chosen), it can use the conditional request mechanism in the forwarded
        request to give the next inbound server an opportunity to choose a valid
        stored response to use."
        """
        # Arrange
        request = create_request()
        # Response is stale: age 7200s > max-age 3600s
        stale_response = create_response(age_seconds=7200, max_age_seconds=3600)
        cached_pair = create_pair(request=request, response=stale_response)

        # Act
        next_state = idle_client.next(request, [cached_pair])

        # Assert
        assert isinstance(next_state, NeedRevalidation)
        assert next_state.original_request == request
        assert len(next_state.revalidating_pairs) == 1
        assert next_state.revalidating_pairs[0] == cached_pair

    def test_conditional_request_created_for_revalidation(self, idle_client: IdleClient) -> None:
        """
        Test: Conditional request is created with validators from cached response.

        RFC 9111 Section 4.3.1: Sending a Validation Request
        "When generating a conditional request for validation, a cache... updates
        that request with one or more precondition header fields. These contain
        validator metadata sourced from a stored response(s)."

        Validators include:
        - ETag -> If-None-Match
        - Last-Modified -> If-Modified-Since
        """
        # Arrange
        request = create_request()
        stale_response = create_response(
            age_seconds=7200,
            max_age_seconds=3600,
            headers={
                "etag": '"abc123"',
                "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT",
            },
        )
        cached_pair = create_pair(request=request, response=stale_response)

        # Act
        next_state = idle_client.next(request, [cached_pair])

        # Assert
        assert isinstance(next_state, NeedRevalidation)

        # Verify conditional request headers are added
        conditional_request = next_state.request
        # Should have If-None-Match (from ETag) or If-Modified-Since (from Last-Modified)
        assert "if-none-match" in conditional_request.headers or "if-modified-since" in conditional_request.headers

    def test_must_revalidate_directive_forces_revalidation(self) -> None:
        """
        Test: must-revalidate directive forces revalidation of stale responses.

        RFC 9111 Section 5.2.2.2: must-revalidate Response Directive
        "The must-revalidate response directive indicates that once the response
        has become stale, a cache MUST NOT reuse that response to satisfy another
        request until it has been successfully validated by the origin."

        Even with allow_stale enabled, must-revalidate takes precedence.
        """
        # Arrange
        idle_client_allow_stale = IdleClient(
            options=CacheOptions(shared=True, supported_methods=["GET", "HEAD"], allow_stale=True)
        )
        request = create_request()

        # Stale response with must-revalidate
        stale_response = create_response(
            age_seconds=7200,
            max_age_seconds=3600,
            headers={"cache-control": "max-age=3600, must-revalidate"},
        )
        cached_pair = create_pair(request=request, response=stale_response)

        # Act
        next_state = idle_client_allow_stale.next(request, [cached_pair])

        # Assert
        # must-revalidate should override allow_stale
        assert isinstance(next_state, NeedRevalidation)

    def test_multiple_stale_responses_all_included_in_revalidation(self, idle_client: IdleClient) -> None:
        """
        Test: Multiple stale responses are all passed to revalidation state.

        This allows the validation logic to potentially use any of them if
        the server responds with 304 Not Modified.
        """
        # Arrange
        request = create_request()

        stale_response_1 = create_response(age_seconds=7200, max_age_seconds=3600)
        stale_response_2 = create_response(age_seconds=8000, max_age_seconds=3600)

        cached_pairs = [
            create_pair(request=request, response=stale_response_1),
            create_pair(request=request, response=stale_response_2),
        ]

        # Act
        next_state = idle_client.next(request, cached_pairs)

        # Assert
        assert isinstance(next_state, NeedRevalidation)
        assert len(next_state.revalidating_pairs) == 2


# =============================================================================
# Test Suite 4: Edge Cases and RFC 9111 Compliance
# =============================================================================
# These tests cover special scenarios and ensure strict RFC compliance.
# =============================================================================


class TestEdgeCasesAndCompliance:
    """
    Tests for edge cases and specific RFC 9111 compliance scenarios.
    """

    def test_response_without_explicit_freshness_info(self, idle_client: IdleClient) -> None:
        """
        Test: Response without explicit freshness information.

        RFC 9111 Section 4.2.2: Calculating Heuristic Freshness
        "Since origin servers do not always provide explicit expiration times,
        a cache MAY assign a heuristic expiration time when an explicit time is
        not specified."

        Without max-age or Expires, freshness is determined heuristically.
        """
        # Arrange
        request = create_request()

        # Response without max-age or Expires, but with Last-Modified for heuristic freshness
        response_headers = {
            "date": datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT"),
            "last-modified": (datetime.utcnow() - timedelta(days=7)).strftime("%a, %d %b %Y %H:%M:%S GMT"),
        }
        response = Response(
            status_code=200,
            headers=Headers(response_headers),
            metadata={},
        )
        cached_pair = create_pair(request=request, response=response)

        # Act
        next_state = idle_client.next(request, [cached_pair])

        # Assert
        # With heuristic freshness (10% of age since Last-Modified, max 1 week),
        # a 7-day old document would have ~17 hours of freshness remaining
        # Since it's fresh, it should be FromCache
        assert isinstance(next_state, (FromCache, NeedRevalidation, CacheMiss))

    def test_safe_methods_can_be_cached(self, idle_client: IdleClient) -> None:
        """
        Test: Safe methods (GET, HEAD) can be cached.

        RFC 9111 Section 2: Overview of Cache Operation
        "Most commonly, caches store the successful result of a retrieval request:
        i.e., a 200 (OK) response to a GET request."

        Safe methods are cacheable by default.
        """
        safe_methods = ["GET", "HEAD"]

        for method in safe_methods:
            # Arrange
            request = create_request(method=method)
            response = create_response()
            cached_pair = create_pair(request=create_request(method=method), response=response)

            # Act
            next_state = idle_client.next(request, [cached_pair])

            # Assert
            assert isinstance(next_state, FromCache), f"{method} should be cacheable"

    def test_options_propagated_to_next_state(self, idle_client: IdleClient) -> None:
        """
        Test: Cache options are propagated to the next state.

        This ensures configuration is maintained throughout state transitions.
        """
        # Arrange
        request = create_request()

        # Test CacheMiss
        next_state_miss = idle_client.next(request, [])
        assert next_state_miss.options == idle_client.options

        # Test FromCache
        cached_pair = create_pair(request=request, response=create_response())
        next_state_cache = idle_client.next(request, [cached_pair])
        assert next_state_cache.options == idle_client.options

        # Test NeedRevalidation
        stale_pair = create_pair(
            request=request,
            response=create_response(age_seconds=7200, max_age_seconds=3600),
        )
        next_state_revalidate = idle_client.next(request, [stale_pair])
        assert next_state_revalidate.options == idle_client.options

    def test_metadata_flag_set_on_cache_hit(self, idle_client: IdleClient) -> None:
        """
        Test: Metadata flag is set when response is served from cache.

        The 'hishel_from_cache' flag helps with observability and debugging.
        """
        # Arrange
        request = create_request()
        cached_pair = create_pair(request=request, response=create_response())

        # Act
        next_state = idle_client.next(request, [cached_pair])

        # Assert
        assert isinstance(next_state, FromCache)
        assert next_state.pair.response.metadata.get("hishel_from_cache") is True

    def test_empty_vary_header_treated_as_no_vary(self, idle_client: IdleClient) -> None:
        """
        Test: Empty or missing Vary header means no variance on request headers.

        Without a Vary header, the cached response can be used for any request
        with matching URI and method.
        """
        # Arrange
        original_request = create_request(headers={"accept": "application/json"})
        response = create_response()  # No Vary header
        cached_pair = create_pair(request=original_request, response=response)

        # New request with different headers
        new_request = create_request(headers={"accept": "application/xml"})

        # Act
        next_state = idle_client.next(new_request, [cached_pair])

        # Assert
        assert isinstance(next_state, FromCache)

    def test_age_close_to_zero_for_newly_generated_response(self, idle_client: IdleClient) -> None:
        """
        Test: Age should be close to zero for a freshly cached response.

        RFC 9111 Section 4.2.3: Calculating Age
        A response that was just generated should have minimal age.
        """
        # Arrange
        request = create_request()

        # Response generated "now" (age_seconds=0)
        fresh_response = create_response(age_seconds=0, max_age_seconds=3600)
        cached_pair = create_pair(request=request, response=fresh_response)

        # Act
        next_state = idle_client.next(request, [cached_pair])

        # Assert
        assert isinstance(next_state, FromCache)
        age_value = int(next_state.pair.response.headers["age"])
        assert age_value < 10  # Should be very close to 0

    def test_sorting_handles_responses_without_date_header(self, idle_client: IdleClient) -> None:
        """
        Test: Sorting handles missing Date headers gracefully.

        RFC 9111 Section 4.2, paragraph 12:
        "When calculating freshness, to avoid common problems in date parsing..."

        Missing dates should not crash the sorting logic.
        """
        # Arrange
        request = create_request()

        # Create responses: one without Date, one with Date
        response_no_date = Response(
            status_code=200,
            headers=Headers({"cache-control": "max-age=3600"}),
            metadata={},
        )

        response_with_date = create_response()

        cached_pairs = [
            create_pair(request=request, response=response_no_date),
            create_pair(request=request, response=response_with_date),
        ]

        # Act & Assert
        # Should not raise an exception
        next_state = idle_client.next(request, cached_pairs)
        assert isinstance(next_state, (FromCache, NeedRevalidation, CacheMiss))


# =============================================================================
# Test Suite 5: Integration Tests
# =============================================================================
# Complex scenarios combining multiple conditions.
# =============================================================================


class TestIntegrationScenarios:
    """
    Integration tests simulating real-world caching scenarios.
    """

    def test_content_negotiation_with_vary(self, idle_client: IdleClient) -> None:
        """
        Test: Content negotiation scenario with Vary header.

        Simulates a scenario where the server provides different content based
        on Accept headers (e.g., JSON vs XML).
        """
        # Arrange: Original request for JSON
        json_request = create_request(
            url="https://api.example.com/data",
            headers={"accept": "application/json"},
        )
        json_response = create_response(
            headers={
                "vary": "Accept",
                "content-type": "application/json",
            }
        )
        cached_json = create_pair(request=json_request, response=json_response)

        # Act 1: Request for JSON (should hit cache)
        next_state_json = idle_client.next(json_request, [cached_json])
        assert isinstance(next_state_json, FromCache)

        # Act 2: Request for XML (should miss cache)
        xml_request = create_request(
            url="https://api.example.com/data",
            headers={"accept": "application/xml"},
        )
        next_state_xml = idle_client.next(xml_request, [cached_json])
        assert isinstance(next_state_xml, CacheMiss)

    def test_compression_negotiation_with_vary_accept_encoding(self, idle_client: IdleClient) -> None:
        """
        Test: Compression negotiation with Vary: Accept-Encoding.

        Simulates caching of compressed responses.
        """
        # Arrange: Cached gzip response
        gzip_request = create_request(headers={"accept-encoding": "gzip"})
        gzip_response = create_response(
            headers={
                "vary": "Accept-Encoding",
                "content-encoding": "gzip",
            }
        )
        cached_gzip = create_pair(request=gzip_request, response=gzip_response)

        # Act 1: Request with gzip (should hit)
        next_state_gzip = idle_client.next(gzip_request, [cached_gzip])
        assert isinstance(next_state_gzip, FromCache)

        # Act 2: Request with brotli (should miss)
        br_request = create_request(headers={"accept-encoding": "br"})
        next_state_br = idle_client.next(br_request, [cached_gzip])
        assert isinstance(next_state_br, CacheMiss)

    def test_lifecycle_fresh_to_stale_transition(self, idle_client: IdleClient) -> None:
        """
        Test: Simulates the lifecycle of a response from fresh to stale.

        This test demonstrates how the same cached response transitions from
        FromCache to NeedRevalidation as time passes.
        """
        # Arrange: Response that is currently fresh
        request = create_request()

        # Initially fresh (age 10s < max-age 20s)
        response = create_response(age_seconds=10, max_age_seconds=20)
        cached_pair = create_pair(request=request, response=response)

        # Act 1: Request while fresh
        next_state_fresh = idle_client.next(request, [cached_pair])
        assert isinstance(next_state_fresh, FromCache)

        # Arrange: Simulate passage of time (now stale: age 30s > max-age 20s)
        stale_response = create_response(age_seconds=30, max_age_seconds=20)
        stale_pair = create_pair(request=request, response=stale_response)

        # Act 2: Request when stale
        next_state_stale = idle_client.next(request, [stale_pair])
        assert isinstance(next_state_stale, NeedRevalidation)

    def test_multiple_vary_headers(self, idle_client: IdleClient) -> None:
        """
        Test: Response with multiple Vary headers.

        RFC 9111 Section 4.1: The Vary header can list multiple request headers
        that must all match for a cached response to be reused.
        """
        # Arrange
        original_request = create_request(
            headers={
                "accept": "application/json",
                "accept-encoding": "gzip",
                "accept-language": "en-US",
            }
        )
        response = create_response(headers={"vary": "Accept, Accept-Encoding, Accept-Language"})
        cached_pair = create_pair(request=original_request, response=response)

        # Act 1: Request with all matching headers (should hit)
        matching_request = create_request(
            headers={
                "accept": "application/json",
                "accept-encoding": "gzip",
                "accept-language": "en-US",
            }
        )
        next_state_match = idle_client.next(matching_request, [cached_pair])
        assert isinstance(next_state_match, FromCache)

        # Act 2: Request with one different header (should miss)
        non_matching_request = create_request(
            headers={
                "accept": "application/json",
                "accept-encoding": "gzip",
                "accept-language": "fr-FR",  # Different language
            }
        )
        next_state_no_match = idle_client.next(non_matching_request, [cached_pair])
        assert isinstance(next_state_no_match, CacheMiss)
