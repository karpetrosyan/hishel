"""
Comprehensive tests for the NeedRevalidation state.

Tests verify compliance with RFC 9111 Section 4.3: Validation
https://www.rfc-editor.org/rfc/rfc9111.html#section-4.3

Test Categories:
---------------
1. 304 Not Modified responses (freshening)
2. 2xx Success responses (new content)
3. 5xx Server Error responses
4. Validator matching strategies
5. Edge cases and error handling
"""

import uuid
from typing import Dict, Optional

import pytest

from hishel.beta import CompletePair, PairMeta, Request, Response
from hishel.beta._core._headers import Headers
from hishel.beta._core._spec import (
    CacheMiss,
    CacheOptions,
    CouldNotBeStored,
    InvalidatePairs,
    NeedRevalidation,
    NeedToBeUpdated,
    StoreAndUse,
)

# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


@pytest.fixture
def default_options() -> CacheOptions:
    """Default cache options."""
    return CacheOptions(shared=True, supported_methods=["GET", "HEAD"], allow_stale=False)


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
    pair_id: Optional[uuid.UUID] = None,
) -> CompletePair:
    """Helper to create a request-response pair."""
    return CompletePair(
        id=pair_id or uuid.uuid4(),
        request=request or create_request(),
        response=response or create_response(),
        meta=PairMeta(),
        cache_key=b"test-cache-key",
    )


# =============================================================================
# Test Suite 1: 304 Not Modified Responses (Freshening)
# =============================================================================


class TestNotModifiedResponses:
    """
    Tests for 304 Not Modified responses that freshen cached responses.

    RFC 9111 Section 4.3.4: Freshening Stored Responses Upon Validation
    """

    def test_304_with_matching_strong_etag_freshens_response(self, default_options: CacheOptions) -> None:
        """
        Test: 304 response with matching strong ETag freshens cached response.

        RFC 9111 Section 4.3.4:
        "If the 304 response contains a strong entity tag: the stored responses
        with the same strong entity tag."

        Strong ETags indicate exact byte-for-byte match.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request(headers={"if-none-match": '"abc123"'})

        # Cached response with matching ETag
        cached_response = create_response(
            headers={"etag": '"abc123"', "cache-control": "max-age=3600", "date": "Mon, 01 Jan 2024 00:00:00 GMT"}
        )
        cached_pair = create_pair(request=original_request, response=cached_response)

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair],
            options=default_options,
        )

        # 304 response with same ETag and fresh metadata
        revalidation_response = create_response(
            status_code=304,
            headers={
                "etag": '"abc123"',
                "cache-control": "max-age=7200",  # New max-age
                "date": "Mon, 01 Jan 2024 12:00:00 GMT",  # New date
            },
        )

        # Act
        next_state = need_revalidation.next(revalidation_response)

        # Assert
        assert isinstance(next_state, NeedToBeUpdated)
        assert len(next_state.updating_pairs) == 1
        # Response should be updated with new cache-control
        updated_response = next_state.updating_pairs[0].response
        assert "cache-control" in updated_response.headers

    def test_304_with_weak_etag_uses_last_modified_fallback(self, default_options: CacheOptions) -> None:
        """
        Test: 304 with weak ETag falls back to Last-Modified matching.

        RFC 9110 Section 8.8.3: ETag
        Weak ETags (W/"...") indicate semantic equivalence but not byte-identity.
        They're not reliable for caching decisions, so we fall back to Last-Modified.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request()

        # Cached response with Last-Modified
        cached_response = create_response(
            headers={"last-modified": "Mon, 01 Jan 2024 00:00:00 GMT", "cache-control": "max-age=3600"}
        )
        cached_pair = create_pair(request=original_request, response=cached_response)

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair],
            options=default_options,
        )

        # 304 response with weak ETag (ignored) and matching Last-Modified
        revalidation_response = create_response(
            status_code=304,
            headers={
                "etag": 'W/"abc123"',  # Weak ETag - ignored
                "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT",
                "cache-control": "max-age=7200",
            },
        )

        # Act
        next_state = need_revalidation.next(revalidation_response)

        # Assert
        assert isinstance(next_state, NeedToBeUpdated)
        assert len(next_state.updating_pairs) == 1

    def test_304_with_matching_last_modified_freshens_response(self, default_options: CacheOptions) -> None:
        """
        Test: 304 response with matching Last-Modified freshens cached response.

        RFC 9111 Section 4.3.4:
        "If the 304 response contains a Last-Modified value: the stored responses
        with the same Last-Modified value."

        Last-Modified is used when ETag is not available.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request(headers={"if-modified-since": "Mon, 01 Jan 2024 00:00:00 GMT"})

        # Cached response with Last-Modified
        cached_response = create_response(
            headers={"last-modified": "Mon, 01 Jan 2024 00:00:00 GMT", "cache-control": "max-age=3600"}
        )
        cached_pair = create_pair(request=original_request, response=cached_response)

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair],
            options=default_options,
        )

        # 304 response with same Last-Modified
        revalidation_response = create_response(
            status_code=304, headers={"last-modified": "Mon, 01 Jan 2024 00:00:00 GMT", "cache-control": "max-age=7200"}
        )

        # Act
        next_state = need_revalidation.next(revalidation_response)

        # Assert
        assert isinstance(next_state, NeedToBeUpdated)
        assert len(next_state.updating_pairs) == 1

    def test_304_with_single_cached_response_and_no_validators(self, default_options: CacheOptions) -> None:
        """
        Test: 304 with no validators but single cached response freshens it.

        RFC 9111 Section 4.3.4:
        "If there is only a single stored response: that response."

        When only one response is cached and server says "not modified",
        we can safely assume that response is valid.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request()

        # Cached response without validators
        cached_response = create_response(headers={"cache-control": "max-age=3600"})
        cached_pair = create_pair(request=original_request, response=cached_response)

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair],  # Only one pair
            options=default_options,
        )

        # 304 response without validators
        revalidation_response = create_response(status_code=304, headers={"cache-control": "max-age=7200"})

        # Act
        next_state = need_revalidation.next(revalidation_response)

        # Assert
        assert isinstance(next_state, NeedToBeUpdated)
        assert len(next_state.updating_pairs) == 1

    def test_304_with_multiple_responses_and_no_validators_invalidates_all(self, default_options: CacheOptions) -> None:
        """
        Test: 304 with no validators and multiple responses invalidates all.

        RFC 9111 Section 4.3.4:
        When multiple responses are cached but the 304 has no validators,
        we cannot determine which response is valid. Conservative approach
        is to invalidate all and treat as cache miss.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request()

        # Multiple cached responses without validators
        cached_pair_1 = create_pair(
            request=original_request, response=create_response(headers={"cache-control": "max-age=3600"})
        )
        cached_pair_2 = create_pair(
            request=original_request, response=create_response(headers={"cache-control": "max-age=1800"})
        )

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair_1, cached_pair_2],
            options=default_options,
        )

        # 304 response without validators
        revalidation_response = create_response(status_code=304, headers={"cache-control": "max-age=7200"})

        # Act
        next_state = need_revalidation.next(revalidation_response)

        # Assert
        # Should invalidate all and result in cache miss
        assert isinstance(next_state, InvalidatePairs)
        assert len(next_state.pair_ids) == 2
        assert isinstance(next_state.next_state, CacheMiss)

    def test_304_with_non_matching_etag_invalidates_response(self, default_options: CacheOptions) -> None:
        """
        Test: 304 with non-matching ETag invalidates cached response.

        If the 304's ETag doesn't match the cached response's ETag,
        the cached response is outdated and should be invalidated.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request()

        # Cached response with old ETag
        cached_response = create_response(headers={"etag": '"old123"', "cache-control": "max-age=3600"})
        cached_pair = create_pair(request=original_request, response=cached_response)

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair],
            options=default_options,
        )

        # 304 response with different ETag
        revalidation_response = create_response(
            status_code=304, headers={"etag": '"new456"', "cache-control": "max-age=7200"}
        )

        # Act
        next_state = need_revalidation.next(revalidation_response)

        # Assert
        assert isinstance(next_state, InvalidatePairs)
        assert len(next_state.pair_ids) == 1
        assert isinstance(next_state.next_state, CacheMiss)

    def test_304_with_multiple_responses_freshens_matching_invalidates_others(
        self, default_options: CacheOptions
    ) -> None:
        """
        Test: 304 with multiple cached responses freshens matching, invalidates others.

        When multiple responses are cached with different ETags, only the one
        matching the 304's ETag should be freshened. Others should be invalidated.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request()

        # Two cached responses with different ETags
        cached_pair_1 = create_pair(
            request=original_request,
            response=create_response(headers={"etag": '"match123"', "cache-control": "max-age=3600"}),
        )
        cached_pair_2 = create_pair(
            request=original_request,
            response=create_response(headers={"etag": '"nomatch456"', "cache-control": "max-age=3600"}),
        )

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair_1, cached_pair_2],
            options=default_options,
        )

        # 304 response matches first cached response's ETag
        revalidation_response = create_response(
            status_code=304, headers={"etag": '"match123"', "cache-control": "max-age=7200"}
        )

        # Act
        next_state = need_revalidation.next(revalidation_response)

        # Assert
        assert isinstance(next_state, InvalidatePairs)
        assert len(next_state.pair_ids) == 1  # One invalidated
        assert isinstance(next_state.next_state, NeedToBeUpdated)
        assert len(next_state.next_state.updating_pairs) == 1  # One freshened


# =============================================================================
# Test Suite 2: 2xx Success Responses (New Content)
# =============================================================================


class TestSuccessResponses:
    """
    Tests for 2xx success responses indicating the resource has changed.

    RFC 9111 Section 4.3.3, paragraph 2
    """

    @pytest.mark.parametrize("status_code", [200, 201, 202, 203, 204, 206])
    def test_2xx_response_invalidates_old_pairs_and_stores_new(
        self, default_options: CacheOptions, status_code: int
    ) -> None:
        """
        Test: 2xx response invalidates old cached pairs and stores new response.

        RFC 9111 Section 4.3.3:
        "A full response (i.e., one containing content) indicates that none of
        the stored responses nominated in the conditional request are suitable.
        Instead, the cache MUST use the full response to satisfy the request."

        2xx means the resource has changed - use the new response.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request()

        # Old cached pairs (will be invalidated)
        cached_pair_1 = create_pair(
            response=create_response(headers={"etag": '"old1"', "cache-control": "max-age=3600"})
        )
        cached_pair_2 = create_pair(
            response=create_response(headers={"etag": '"old2"', "cache-control": "max-age=3600"})
        )

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair_1, cached_pair_2],
            options=default_options,
        )

        # New response with different content
        new_response = create_response(
            status_code=status_code, headers={"etag": '"new123"', "cache-control": "max-age=7200"}
        )

        # Act
        next_state = need_revalidation.next(new_response)

        # Assert
        assert isinstance(next_state, InvalidatePairs)
        # First pair is invalidated
        assert len(next_state.pair_ids) == 1
        assert next_state.pair_ids[0] == cached_pair_1.id

        # Next state should be StoreAndUse or CouldNotBeStored
        inner_state = next_state.next_state
        assert isinstance(inner_state, (StoreAndUse, CouldNotBeStored))

    def test_200_response_marks_as_after_revalidation(self, default_options: CacheOptions) -> None:
        """
        Test: 200 response during revalidation is marked with after_revalidation flag.

        This helps track that the new response was obtained during a revalidation
        attempt rather than an initial cache miss.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request()

        cached_pair = create_pair()

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair],
            options=default_options,
        )

        # New response
        new_response = create_response(status_code=200, headers={"cache-control": "max-age=3600"})

        # Act
        next_state = need_revalidation.next(new_response)

        # Assert
        assert isinstance(next_state, InvalidatePairs)
        inner_state = next_state.next_state
        assert isinstance(inner_state, StoreAndUse)
        # Response should be marked as revalidated
        assert new_response.metadata.get("hishel_revalidated") is True

    def test_2xx_reuses_last_pair_id_for_new_response(self, default_options: CacheOptions) -> None:
        """
        Test: 2xx response reuses the last pair's ID for storing the new response.

        The implementation invalidates all pairs except the last, then reuses
        the last pair's ID for the new response.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request()

        pair_1_id = uuid.uuid4()
        pair_2_id = uuid.uuid4()

        cached_pair_1 = create_pair(pair_id=pair_1_id)
        cached_pair_2 = create_pair(pair_id=pair_2_id)

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair_1, cached_pair_2],
            options=default_options,
        )

        # New response
        new_response = create_response(status_code=200, headers={"cache-control": "max-age=3600"})

        # Act
        next_state = need_revalidation.next(new_response)

        # Assert
        assert isinstance(next_state, InvalidatePairs)
        # Only first pair is invalidated
        assert pair_1_id in next_state.pair_ids
        assert pair_2_id not in next_state.pair_ids

        # Second pair's ID should be reused
        inner_state = next_state.next_state
        assert isinstance(inner_state, StoreAndUse)
        assert inner_state.pair_id == pair_2_id


# =============================================================================
# Test Suite 3: 5xx Server Error Responses
# =============================================================================


class TestServerErrorResponses:
    """
    Tests for 5xx server error responses during revalidation.

    RFC 9111 Section 4.3.3, paragraph 3
    """

    @pytest.mark.parametrize("status_code", [500, 502, 503, 504])
    def test_5xx_response_invalidates_and_forwards_error(self, default_options: CacheOptions, status_code: int) -> None:
        """
        Test: 5xx response invalidates cached pairs and forwards the error.

        RFC 9111 Section 4.3.3:
        "However, if a cache receives a 5xx (Server Error) response while
        attempting to validate a response, it can either forward this response
        to the requesting client or act as if the server failed to respond."

        This implementation chooses to forward the error response.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request()

        cached_pair = create_pair()

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair],
            options=default_options,
        )

        # Server error response
        error_response = create_response(
            status_code=status_code,
            headers={"cache-control": "no-store"},  # Errors typically not cacheable
        )

        # Act
        next_state = need_revalidation.next(error_response)

        # Assert
        assert isinstance(next_state, InvalidatePairs)
        inner_state = next_state.next_state
        # Error might not be stored (depends on cacheability)
        assert isinstance(inner_state, (StoreAndUse, CouldNotBeStored))

    def test_503_service_unavailable_handled_like_2xx(self, default_options: CacheOptions) -> None:
        """
        Test: 503 Service Unavailable is handled the same as 2xx responses.

        The current implementation treats 5xx the same as 2xx: invalidate old
        pairs and attempt to cache the error response.

        Alternative implementations might serve stale content on 5xx errors.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request()

        pair_1 = create_pair()
        pair_2 = create_pair()

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[pair_1, pair_2],
            options=default_options,
        )

        # 503 error
        error_response = create_response(status_code=503, headers={"retry-after": "60"})

        # Act
        next_state = need_revalidation.next(error_response)

        # Assert
        # Same behavior as 2xx
        assert isinstance(next_state, InvalidatePairs)
        assert len(next_state.pair_ids) == 1  # First pair invalidated


# =============================================================================
# Test Suite 4: Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """
    Tests for edge cases and error conditions.
    """

    def test_unexpected_status_code_raises_error(self, default_options: CacheOptions) -> None:
        """
        Test: Unexpected status codes during revalidation raise RuntimeError.

        Valid revalidation responses: 304, 2xx, 5xx
        Other status codes (1xx, 3xx, 4xx) are unexpected and indicate a problem.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request()
        cached_pair = create_pair()

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair],
            options=default_options,
        )

        # Unexpected 3xx redirect
        redirect_response = create_response(status_code=301, headers={"location": "https://example.com/moved"})

        # Act & Assert
        with pytest.raises(RuntimeError, match="Unexpected response status code"):
            need_revalidation.next(redirect_response)

    @pytest.mark.parametrize("status_code", [100, 101, 400, 401, 403, 404])
    def test_other_unexpected_status_codes_raise_error(self, default_options: CacheOptions, status_code: int) -> None:
        """
        Test: Various unexpected status codes raise RuntimeError.

        1xx informational, 3xx redirects, and 4xx client errors
        should not occur during normal revalidation.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request()
        cached_pair = create_pair()

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair],
            options=default_options,
        )

        unexpected_response = create_response(status_code=status_code)

        # Act & Assert
        with pytest.raises(RuntimeError):
            need_revalidation.next(unexpected_response)

    def test_options_propagated_to_next_states(self, default_options: CacheOptions) -> None:
        """
        Test: Cache options are propagated to all next states.
        """
        original_request = create_request()
        conditional_request = create_request()
        cached_pair = create_pair()

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair],
            options=default_options,
        )

        # Test with 304
        response_304 = create_response(status_code=304, headers={"cache-control": "max-age=3600"})
        next_state_304 = need_revalidation.next(response_304)
        assert next_state_304.options == default_options

        # Test with 200
        response_200 = create_response(status_code=200, headers={"cache-control": "max-age=3600"})
        # Create new instance for second test
        need_revalidation_2 = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair],
            options=default_options,
        )
        next_state_200 = need_revalidation_2.next(response_200)
        assert next_state_200.options == default_options

    def test_original_request_preserved_in_next_states(self, default_options: CacheOptions) -> None:
        """
        Test: Original request is preserved through state transitions.

        The original request (without conditional headers) is important for
        creating new cache entries if needed.
        """
        # Arrange
        original_request = create_request(url="https://example.com/test")
        conditional_request = create_request(url="https://example.com/test", headers={"if-none-match": '"abc123"'})
        cached_pair = create_pair()

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[cached_pair],
            options=default_options,
        )

        # Test with 304
        response_304 = create_response(status_code=304)
        next_state = need_revalidation.next(response_304)

        if isinstance(next_state, NeedToBeUpdated):
            assert next_state.original_request == original_request
        elif isinstance(next_state, InvalidatePairs):
            if isinstance(next_state.next_state, NeedToBeUpdated):
                assert next_state.next_state.original_request == original_request

    def test_empty_revalidating_pairs_handled_gracefully(self, default_options: CacheOptions) -> None:
        """
        Test: Empty revalidating_pairs list is handled without errors.

        This shouldn't happen in normal operation, but the code should
        handle it gracefully if it does.
        """
        # Arrange
        original_request = create_request()
        conditional_request = create_request()

        need_revalidation = NeedRevalidation(
            request=conditional_request,
            original_request=original_request,
            revalidating_pairs=[],  # Empty list
            options=default_options,
        )

        # 304 response with no pairs to freshen
        response_304 = create_response(status_code=304)

        # Act
        next_state = need_revalidation.next(response_304)

        # Assert
        # Should result in cache miss since no responses to freshen
        assert isinstance(next_state, CacheMiss)
