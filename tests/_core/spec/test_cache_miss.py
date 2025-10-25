"""
Comprehensive tests for the CacheMiss state.

Tests verify compliance with RFC 9111 Section 3: Storing Responses in Caches
https://www.rfc-editor.org/rfc/rfc9111.html#section-3

Test Categories:
---------------
1. Transition to StoreAndUse state (cacheable responses)
2. Transition to CouldNotBeStored state (non-cacheable responses)
3. Metadata flags and observability
4. Edge cases and RFC 9111 compliance
"""

from datetime import datetime, timedelta
from typing import Dict, Optional

import pytest

from hishel import Request, Response
from hishel._core._headers import Headers
from hishel._core._spec import (
    HEURISTICALLY_CACHEABLE_STATUS_CODES,
    CacheMiss,
    CacheOptions,
    CouldNotBeStored,
    StoreAndUse,
)

# =============================================================================
# Test Fixtures and Helpers
# =============================================================================


@pytest.fixture
def default_options() -> CacheOptions:
    """Default cache options (shared cache)."""
    return CacheOptions(shared=True, supported_methods=["GET", "HEAD"], allow_stale=False)


@pytest.fixture
def private_cache_options() -> CacheOptions:
    """Private cache options (like a browser cache)."""
    return CacheOptions(shared=False, supported_methods=["GET", "HEAD"], allow_stale=False)


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


# =============================================================================
# Test Suite 1: Transition to StoreAndUse (Cacheable Responses)
# =============================================================================


class TestTransitionToStoreAndUse:
    """
    Tests for successful storage transitions.

    StoreAndUse occurs when:
    - All RFC 9111 Section 3 storage requirements are met
    - Response contains explicit caching directives or is heuristically cacheable
    """

    def test_response_with_max_age_is_stored(self, default_options: CacheOptions) -> None:
        """
        Test: Response with max-age directive is stored.

        RFC 9111 Section 5.2.2.1: max-age Response Directive
        "The max-age response directive indicates that the response is to be
        considered stale after its age is greater than the specified number of seconds."

        max-age is the most common explicit caching directive.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        response = create_response(headers={"cache-control": "max-age=3600"})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, StoreAndUse)
        assert response.metadata.get("hishel_stored") is True
        assert response.metadata.get("hishel_from_cache") is False

    def test_response_with_expires_header_is_stored(self, default_options: CacheOptions) -> None:
        """
        Test: Response with Expires header is stored.

        RFC 9111 Section 5.3: Expires
        "The Expires header field gives the date/time after which the response
        is considered stale."

        Expires is an older but still valid caching mechanism.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        future_date = (datetime.utcnow() + timedelta(hours=1)).strftime("%a, %d %b %Y %H:%M:%S GMT")
        response = create_response(headers={"expires": future_date})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, StoreAndUse)
        assert response.metadata.get("hishel_stored") is True

    def test_response_with_public_directive_is_stored(self, default_options: CacheOptions) -> None:
        """
        Test: Response with public directive is stored.

        RFC 9111 Section 5.2.2.9: public Response Directive
        "The public response directive indicates that a cache MAY store the
        response even if it would otherwise be prohibited."

        public explicitly marks a response as cacheable.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        response = create_response(headers={"cache-control": "public"})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, StoreAndUse)
        assert response.metadata.get("hishel_stored") is True

    def test_response_with_s_maxage_is_stored_in_shared_cache(self, default_options: CacheOptions) -> None:
        """
        Test: Response with s-maxage is stored in shared cache.

        RFC 9111 Section 5.2.2.10: s-maxage Response Directive
        "The s-maxage response directive indicates that, for a shared cache,
        the maximum age specified by this directive overrides the maximum age
        specified by either the max-age directive or the Expires header field."

        s-maxage is specific to shared caches (proxies, CDNs).
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        response = create_response(headers={"cache-control": "s-maxage=7200"})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, StoreAndUse)
        assert response.metadata.get("hishel_stored") is True

    def test_private_response_stored_in_private_cache(self, private_cache_options: CacheOptions) -> None:
        """
        Test: Response with private directive is stored in private cache.

        RFC 9111 Section 5.2.2.7: private Response Directive
        "The unqualified private response directive... indicates that... a
        private cache MAY store the response."

        Private caches (browser caches) can store private responses.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=private_cache_options)

        response = create_response(headers={"cache-control": "private, max-age=3600"})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, StoreAndUse)
        assert response.metadata.get("hishel_stored") is True

    @pytest.mark.parametrize("status_code", HEURISTICALLY_CACHEABLE_STATUS_CODES)
    def test_heuristically_cacheable_status_codes_are_stored(
        self,
        default_options: CacheOptions,
        status_code: int,
    ) -> None:
        """
        Test: Responses with heuristically cacheable status codes are stored.

        RFC 9111 Section 4.2.2: Calculating Heuristic Freshness
        "a cache MAY assign a heuristic expiration time when an explicit time
        is not specified"

        Certain status codes are defined as cacheable even without explicit
        caching directives:
        200, 203, 204, 300, 301, 308, 404, 405, 410, 414, 501
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        # Response with heuristically cacheable status, no explicit caching directives
        response = create_response(status_code=status_code)

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, StoreAndUse)
        assert response.metadata.get("hishel_stored") is True

    def test_response_after_revalidation_marked_correctly(self, default_options: CacheOptions) -> None:
        """
        Test: Response received after revalidation is marked with metadata.

        The after_revalidation flag tracks whether this cache miss occurred
        during a revalidation attempt, which is important for observability.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(
            request=request,
            options=default_options,
            after_revalidation=True,  # This was a revalidation attempt
        )

        response = create_response(headers={"cache-control": "max-age=3600"})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, StoreAndUse)
        assert response.metadata.get("hishel_revalidated") is True

    def test_response_with_multiple_caching_directives(self, default_options: CacheOptions) -> None:
        """
        Test: Response with multiple caching directives is stored.

        Real-world responses often include multiple caching directives.
        The response should be stored if at least one valid directive is present.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        response = create_response(
            headers={
                "cache-control": "public, max-age=3600, s-maxage=7200",
                "expires": (datetime.utcnow() + timedelta(hours=2)).strftime("%a, %d %b %Y %H:%M:%S GMT"),
            }
        )

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, StoreAndUse)


# =============================================================================
# Test Suite 2: Transition to CouldNotBeStored (Non-Cacheable Responses)
# =============================================================================


class TestTransitionToCouldNotBeStored:
    """
    Tests for failed storage transitions.

    CouldNotBeStored occurs when:
    - One or more RFC 9111 Section 3 storage requirements fail
    - Response explicitly prohibits caching
    """

    def test_unsupported_method_cannot_be_stored(self, default_options: CacheOptions) -> None:
        """
        Test: Response to unsupported method cannot be stored.

        RFC 9111 Section 3, paragraph 2.1:
        "the request method is understood by the cache"

        By default, only GET and HEAD are supported for caching.
        """
        # Arrange
        # POST is not in supported_methods
        request = create_request(method="POST")
        cache_miss = CacheMiss(request=request, options=default_options)

        response = create_response(headers={"cache-control": "max-age=3600"})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, CouldNotBeStored)
        assert response.metadata.get("hishel_stored") is False

    @pytest.mark.parametrize("status_code", [100, 101, 102, 103])
    def test_informational_status_codes_cannot_be_stored(
        self,
        default_options: CacheOptions,
        status_code: int,
    ) -> None:
        """
        Test: 1xx informational responses cannot be stored.

        RFC 9111 Section 3, paragraph 2.2:
        "the response status code is final (see Section 15 of [HTTP])"

        1xx status codes are informational and not final responses.
        They indicate the request is still being processed.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        response = create_response(status_code=status_code, headers={"cache-control": "max-age=3600"})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, CouldNotBeStored)
        assert response.metadata.get("hishel_stored") is False

    @pytest.mark.parametrize("status_code", [206, 304])
    def test_special_status_codes_cannot_be_stored(
        self,
        default_options: CacheOptions,
        status_code: int,
    ) -> None:
        """
        Test: 206 and 304 status codes cannot be stored (simplified implementation).

        RFC 9111 Section 3, paragraph 2.3:
        "if the response status code is 206 or 304, or the must-understand cache
        directive is present: the cache understands the response status code"

        206 Partial Content: Requires special handling for range requests
        304 Not Modified: Used for conditional requests, updates existing cache

        This implementation marks them as not understood for simplicity.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        response = create_response(status_code=status_code, headers={"cache-control": "max-age=3600"})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, CouldNotBeStored)

    def test_no_store_directive_prevents_storage(self, default_options: CacheOptions) -> None:
        """
        Test: no-store directive prevents storage.

        RFC 9111 Section 5.2.2.5: no-store Response Directive
        "The no-store response directive indicates that a cache MUST NOT store
        any part of either the immediate request or the response"

        no-store is the strongest cache prevention directive.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        response = create_response(headers={"cache-control": "no-store"})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, CouldNotBeStored)
        assert response.metadata.get("hishel_stored") is False

    def test_private_directive_prevents_storage_in_shared_cache(self, default_options: CacheOptions) -> None:
        """
        Test: private directive prevents storage in shared cache.

        RFC 9111 Section 5.2.2.7: private Response Directive
        "The unqualified private response directive indicates that a shared
        cache MUST NOT store the response"

        Shared caches (proxies, CDNs) cannot store private responses.
        """
        # Arrange
        request = create_request()
        # default_options is a shared cache
        cache_miss = CacheMiss(request=request, options=default_options)

        response = create_response(headers={"cache-control": "private, max-age=3600"})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, CouldNotBeStored)
        assert response.metadata.get("hishel_stored") is False

    def test_authorization_header_prevents_storage_in_shared_cache(self, default_options: CacheOptions) -> None:
        """
        Test: Authorization header prevents storage in shared cache.

        RFC 9111 Section 3.5: Caching Authenticated Responses
        "A shared cache MUST NOT use a cached response to a request with an
        Authorization header field unless... a response directive is present
        that explicitly allows shared caching"

        Requests with Authorization often contain user-specific data.
        """
        # Arrange
        request = create_request(headers={"authorization": "Bearer token123"})
        # default_options is a shared cache
        cache_miss = CacheMiss(request=request, options=default_options)

        response = create_response(headers={"cache-control": "max-age=3600"})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, CouldNotBeStored)

    def test_response_without_caching_metadata_and_non_cacheable_status(self, default_options: CacheOptions) -> None:
        """
        Test: Response without caching metadata and non-cacheable status cannot be stored.

        RFC 9111 Section 3, paragraph 2.7:
        "the response contains at least one of the following:
         - a public response directive
         - a private response directive (if cache is not shared)
         - an Expires header field
         - a max-age response directive
         - an s-maxage response directive (if cache is shared)
         - a status code that is defined as heuristically cacheable"

        Without explicit caching directives or a heuristically cacheable status,
        the response cannot be stored.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        # 201 Created is not heuristically cacheable
        response = create_response(status_code=201)

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, CouldNotBeStored)
        assert response.metadata.get("hishel_stored") is False

    def test_response_with_no_store_overrides_other_directives(self, default_options: CacheOptions) -> None:
        """
        Test: no-store overrides other caching directives.

        RFC 9111 Section 5.2.2.5: no-store Response Directive
        no-store is the strongest directive and must be honored even if
        other caching directives are present.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        # Response has both max-age and no-store
        response = create_response(headers={"cache-control": "max-age=3600, no-store"})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, CouldNotBeStored)


# =============================================================================
# Test Suite 3: Metadata and Observability
# =============================================================================


class TestMetadataAndObservability:
    """
    Tests for metadata flags that provide observability into cache behavior.
    """

    def test_metadata_flags_set_on_stored_response(self, default_options: CacheOptions) -> None:
        """
        Test: Correct metadata flags are set when response is stored.

        Metadata flags help track the lifecycle and behavior of cached responses.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        response = create_response(headers={"cache-control": "max-age=3600"})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, StoreAndUse)
        assert response.metadata.get("hishel_spec_ignored") is False
        assert response.metadata.get("hishel_from_cache") is False
        assert response.metadata.get("hishel_stored") is True

    def test_metadata_flags_set_on_not_stored_response(self, default_options: CacheOptions) -> None:
        """
        Test: Correct metadata flags are set when response cannot be stored.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        response = create_response(headers={"cache-control": "no-store"})

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, CouldNotBeStored)
        assert response.metadata.get("hishel_spec_ignored") is False
        assert response.metadata.get("hishel_from_cache") is False
        assert response.metadata.get("hishel_stored") is False

    def test_revalidation_flag_set_when_after_revalidation(self, default_options: CacheOptions) -> None:
        """
        Test: hishel_revalidated flag is set when after_revalidation is True.

        This helps track which responses were obtained through revalidation
        vs initial cache misses.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options, after_revalidation=True)

        response = create_response(headers={"cache-control": "max-age=3600"})

        # Act
        cache_miss.next(response)

        # Assert
        assert response.metadata.get("hishel_revalidated") is True

    def test_revalidation_flag_not_set_when_not_after_revalidation(self, default_options: CacheOptions) -> None:
        """
        Test: hishel_revalidated flag is not set for normal cache misses.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options, after_revalidation=False)

        response = create_response(headers={"cache-control": "max-age=3600"})

        # Act
        cache_miss.next(response)

        # Assert
        assert response.metadata.get("hishel_revalidated") is False


# =============================================================================
# Test Suite 4: Edge Cases and Cache Type Differences
# =============================================================================


class TestEdgeCasesAndCacheTypes:
    """
    Tests for edge cases and differences between shared and private caches.
    """

    def test_shared_cache_vs_private_cache_with_private_directive(self) -> None:
        """
        Test: private directive behavior differs between shared and private caches.

        RFC 9111 Section 5.2.2.7: private Response Directive
        - Shared cache: MUST NOT store
        - Private cache: MAY store
        """
        request = create_request()
        response = create_response(headers={"cache-control": "private, max-age=3600"})

        # Test with shared cache
        shared_options = CacheOptions(shared=True, supported_methods=["GET", "HEAD"])
        cache_miss_shared = CacheMiss(request=request, options=shared_options)
        next_state_shared = cache_miss_shared.next(response)
        assert isinstance(next_state_shared, CouldNotBeStored)

        # Test with private cache
        private_options = CacheOptions(shared=False, supported_methods=["GET", "HEAD"])
        cache_miss_private = CacheMiss(request=request, options=private_options)

        # Create fresh response for private cache test
        response_private = create_response(headers={"cache-control": "private, max-age=3600"})
        next_state_private = cache_miss_private.next(response_private)
        assert isinstance(next_state_private, StoreAndUse)

    def test_s_maxage_only_applies_to_shared_cache(self) -> None:
        """
        Test: s-maxage directive only provides caching metadata for shared caches.

        RFC 9111 Section 5.2.2.10: s-maxage Response Directive
        "The s-maxage response directive indicates that, for a shared cache..."

        For private caches, s-maxage alone is not sufficient.
        """
        request = create_request()

        # Response with only s-maxage (no other caching directives)
        response_shared = create_response(
            status_code=201,  # Not heuristically cacheable
            headers={"cache-control": "s-maxage=3600"},
        )

        response_private = create_response(
            status_code=201,  # Not heuristically cacheable
            headers={"cache-control": "s-maxage=3600"},
        )

        # Test with shared cache - should be stored
        shared_options = CacheOptions(shared=True, supported_methods=["GET", "HEAD"])
        cache_miss_shared = CacheMiss(request=request, options=shared_options)
        next_state_shared = cache_miss_shared.next(response_shared)
        assert isinstance(next_state_shared, StoreAndUse)

        # Test with private cache - should NOT be stored (s-maxage doesn't apply)
        private_options = CacheOptions(shared=False, supported_methods=["GET", "HEAD"])
        cache_miss_private = CacheMiss(request=request, options=private_options)
        next_state_private = cache_miss_private.next(response_private)
        assert isinstance(next_state_private, CouldNotBeStored)

    def test_options_propagated_to_next_state(self, default_options: CacheOptions) -> None:
        """
        Test: Cache options are propagated to the next state.
        """
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        # Test StoreAndUse
        response_storable = create_response(headers={"cache-control": "max-age=3600"})
        next_state_store = cache_miss.next(response_storable)
        assert next_state_store.options == default_options

        # Test CouldNotBeStored
        response_not_storable = create_response(headers={"cache-control": "no-store"})
        next_state_not_store = cache_miss.next(response_not_storable)
        assert next_state_not_store.options == default_options

    def test_response_with_no_cache_control_header(self, default_options: CacheOptions) -> None:
        """
        Test: Response without Cache-Control header.

        Without Cache-Control, the response can still be cached if it has
        other caching metadata (Expires) or is heuristically cacheable.
        """
        # Arrange
        request = create_request()
        cache_miss = CacheMiss(request=request, options=default_options)

        # Heuristically cacheable status, no cache-control
        response = create_response(status_code=200)

        # Act
        next_state = cache_miss.next(response)

        # Assert
        assert isinstance(next_state, StoreAndUse)
