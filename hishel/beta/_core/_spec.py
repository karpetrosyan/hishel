from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    Literal,
    Optional,
    TypeVar,
    Union,
)

from hishel._utils import parse_date, partition
from hishel.beta._core._headers import Headers, Range, Vary, parse_cache_control

if TYPE_CHECKING:
    from hishel.beta import CompletePair, Request, Response


TState = TypeVar("TState", bound="State")
HEURISTICALLY_CACHEABLE_STATUS_CODES = (
    200,
    203,
    204,
    300,
    301,
    308,
    404,
    405,
    410,
    414,
    501,
)
logger = logging.getLogger("hishel.core.spec")


@dataclass
class CacheOptions:
    shared: bool = True
    supported_methods: list[str] = field(default_factory=lambda: ["GET", "HEAD"])
    allow_stale: bool = False


@dataclass
class State(ABC):
    options: CacheOptions

    @abstractmethod
    def next(self, *args: Any, **kwargs: Any) -> Union["State", None]:
        raise NotImplementedError("Subclasses must implement this method")


def vary_headers_match(
    original_request: Request,
    associated_pair: CompletePair,
) -> bool:
    """
    4.1 Calculating cache key with the vary header value

    see: https://www.rfc-editor.org/rfc/rfc9111.html#caching.negotiated.responses
    """
    vary_header = associated_pair.response.headers.get("vary")
    if not vary_header:
        return True

    vary = Vary.from_value(vary_header)

    for vary_header in vary.values:
        if vary_header == "*":
            return False

        if original_request.headers.get(vary_header) != associated_pair.request.headers.get(vary_header):
            return False

    return True


def get_freshness_lifetime(response: Response, is_cache_shared: bool) -> Optional[int]:
    """
    Get the freshness lifetime of a response.

    See: https://www.rfc-editor.org/rfc/rfc9111.html#name-calculating-freshness-lifet
    """
    response_cache_control = parse_cache_control(response.headers.get("Cache-Control"))

    if is_cache_shared and response_cache_control.s_maxage is not None:
        return response_cache_control.s_maxage

    if response_cache_control.max_age is not None:
        return response_cache_control.max_age

    if "expires" in response.headers:
        expires_timestamp = parse_date(response.headers["expires"])

        if expires_timestamp is None:
            raise RuntimeError("Cannot parse Expires header")  # pragma: nocover

        date_timestamp = parse_date(response.headers["date"]) if "date" in response.headers else time.time()

        if date_timestamp is None:  # pragma: nocover
            # if the Date header is invalid, we use the current time as the date
            date_timestamp = time.time()

        return int(expires_timestamp - (time.time() if date_timestamp is None else date_timestamp))
    heuristic_freshness = get_heuristic_freshness(response)

    if heuristic_freshness is None:
        return None
    return get_heuristic_freshness(response)


def allowed_stale(response: Response, allow_stale_option: bool) -> bool:
    """
    4.2.4 Serving stale responses

    RFC Reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-serving-stale-responses
    """

    if not allow_stale_option:
        return False
    response_cache_control = parse_cache_control(
        response.headers.get(
            "Cache-Control",
        )
    )

    if response_cache_control.no_cache:
        return False

    if response_cache_control.must_revalidate:
        return False

    return True


def get_heuristic_freshness(response: Response) -> int | None:
    """
    4.2.2. Calculating Heuristic Freshness

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-calculating-heuristic-fresh
    """
    last_modified = response.headers.get("last-modified")

    if last_modified:
        last_modified_timestamp = parse_date(last_modified)
        if last_modified_timestamp is None:  # pragma: nocover
            return None
        now = time.time()

        ONE_WEEK = 604_800

        return min(ONE_WEEK, int((now - last_modified_timestamp) * 0.1))

    return None


def get_age(response: Response) -> int:
    """
    4.2.3. Calculating Age

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-calculating-age
    """

    # A recipient with a clock that receives a response with an invalid Date header
    # field value MAY replace that value with the time that response was received.
    # See: https://www.rfc-editor.org/rfc/rfc9110#name-date
    if "date" not in response.headers:
        return 0

    date = parse_date(response.headers["date"])
    if date is None:  # pragma: nocover
        return 0

    now = time.time()
    apparent_age = max(0, now - date)
    return int(apparent_age)


def make_conditional_request(request: Request, response: Response) -> Request:
    """
    4.3.1 Sending a Validation Request
    Adds the precondition headers needed for response validation.

    This method will use the "Last-Modified" or "Etag" headers
    if they are provided in order to create precondition headers.

    See also (https://www.rfc-editor.org/rfc/rfc9111.html#name-sending-a-validation-reques)
    """

    if "last-modified" in response.headers:
        last_modified = response.headers["last-modified"]
    else:
        last_modified = None

    if "etag" in response.headers:
        etag = response.headers["etag"]
    else:
        etag = None

    precondition_headers: Dict[str, str] = {}

    # When generating a conditional request for validation, a cache:

    # MUST send the relevant entity tags (using If-Match, If-None-Match, or If-Range)
    # if the entity tags were provided in the stored response(s) being validated.
    if etag is not None:
        precondition_headers["If-None-Match"] = etag

    # SHOULD send the Last-Modified value (using If-Modified-Since)
    # if the request is not for a subrange, a single stored response
    # is being validated, and that response contains a Last-Modified value.
    if last_modified:
        precondition_headers["If-Modified-Since"] = last_modified

    return replace(
        request,
        headers=Headers(
            {
                **request.headers,
                **precondition_headers,
            }
        ),
    )


def exclude_unstorable_headers(response: Response, is_cache_shared: bool) -> Response:
    """
    see: https://www.rfc-editor.org/rfc/rfc9111.html#section-3.1
    """

    need_to_be_excluded = set(
        [
            "keep-alive",
            "te",
            "transfer-encoding",
            "upgrade",
            "proxy-connection",
            "proxy-authenticate",
            "proxy-authentication-info",
            "proxy-authorization",
        ]
    )

    cache_control = parse_cache_control(
        response.headers.get(
            "cache-control",
        )
    )

    if isinstance(cache_control.no_cache, list):
        for field in cache_control.no_cache:
            need_to_be_excluded.add(field.lower())

    if is_cache_shared and isinstance(cache_control.private, list):
        for field in cache_control.private:
            need_to_be_excluded.add(field.lower())

    new_headers = Headers(
        {key: value for key, value in response.headers.items() if key.lower() not in need_to_be_excluded}
    )
    return replace(
        response,
        headers=new_headers,
    )


def refresh_response_headers(
    stored_response: Response,
    revalidation_response: Response,
) -> Response:
    """
    see: https://www.rfc-editor.org/rfc/rfc9111.html#section-3.2
    """

    excluded_headers = set(
        [
            "content-encoding",
            "content-type",
            "content-range",
        ]
    )

    new_headers = {
        **stored_response.headers,
        **{key: value for key, value in revalidation_response.headers.items() if key.lower() not in excluded_headers},
    }

    return exclude_unstorable_headers(
        replace(
            stored_response,
            headers=Headers(new_headers),
        ),
        is_cache_shared=True,
    )


AnyState = Union[
    "CacheMiss",
    "StoreAndUse",
    "CouldNotBeStored",
    "FromCache",
    "NeedToBeUpdated",
    "NeedRevalidation",
    "IdleClient",
    "InvalidatePairs",
]

# Defined in https://www.rfc-editor.org/rfc/rfc9110#name-safe-methods
SAFE_METHODS = frozenset(["GET", "HEAD", "OPTIONS", "TRACE"])


def create_idle_state(role: Literal["client", "server"], options: Optional[CacheOptions] = None) -> IdleClient:
    if role == "server":
        raise NotImplementedError("Server role is not implemented yet.")
    return IdleClient(options=options or CacheOptions())


@dataclass
class IdleClient(State):
    """
    Represents the idle state of a client initiating an HTTP request.

    This is the entry point of the cache state machine. When a client wants to send
    a request, this state determines whether the request can be satisfied from cache,
    needs revalidation, or must be forwarded to the origin server (cache miss).

    State Transitions:
    -----------------
    - CacheMiss: When no suitable cached response exists or the request cannot be cached
    - FromCache: When a fresh or stale-but-allowed cached response can be used
    - NeedRevalidation: When a stale cached response exists and must be validated

    RFC 9111 References:
    -------------------
    - Section 4: Constructing Responses from Caches
      https://www.rfc-editor.org/rfc/rfc9111.html#section-4
    - Section 4.1: Calculating Cache Keys (Vary handling)
      https://www.rfc-editor.org/rfc/rfc9111.html#section-4.1
    - Section 4.2: Freshness
      https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2
    - Section 4.3: Validation
      https://www.rfc-editor.org/rfc/rfc9111.html#section-4.3

    Attributes:
    ----------
    options : CacheOptions
        Configuration options for cache behavior (inherited from State)
    """

    def next(
        self, request: Request, associated_pairs: list[CompletePair]
    ) -> Union["CacheMiss", "FromCache", "NeedRevalidation"]:
        """
        Determines the next state transition based on the request and available cached responses.

        This method implements the core cache lookup algorithm defined in RFC 9111 Section 4.
        It evaluates whether a cached response can be reused and transitions to the appropriate
        next state.

        Parameters:
        ----------
        request : Request
            The incoming HTTP request from the client
        associated_pairs : list[CompletePair]
            List of request-response pairs previously stored in the cache that may match
            this request. These pairs are pre-filtered by cache key (typically URI).

        Returns:
        -------
        Union[CacheMiss, FromCache, NeedRevalidation]
            - CacheMiss: No suitable cached response; request must be forwarded to origin
            - FromCache: A suitable cached response can be returned immediately
            - NeedRevalidation: A cached response exists but requires validation before use

        RFC 9111 Compliance:
        -------------------
        This method enforces the requirements from RFC 9111 Section 4, paragraph 1:
        "When presented with a request, a cache MUST NOT reuse a stored response unless:
         1. the presented target URI and that of the stored response match, and
         2. the request method associated with the stored response allows it to be used
            for the presented request, and
         3. request header fields nominated by the stored response (if any) match those
            presented (see Section 4.1), and
         4. the stored response does not contain the no-cache directive (Section 5.2.2.4),
            unless it is successfully validated (Section 4.3), and
         5. the stored response is one of the following:
            - fresh (see Section 4.2), or
            - allowed to be served stale (see Section 4.2.4), or
            - successfully validated (see Section 4.3)."

        Implementation Notes:
        --------------------
        - Range requests always result in a cache miss (simplified behavior)
        - Unsafe methods (POST, PUT, DELETE, etc.) are written through to origin
        - Multiple matching responses are sorted by Date header (most recent first)
        - Age header is updated when serving from cache

        Examples:
        --------
        >>> # Cache miss - no matching responses
        >>> idle = IdleClient(options=default_options)
        >>> next_state = idle.next(get_request, [])
        >>> isinstance(next_state, CacheMiss)
        True

        >>> # From cache - fresh response available
        >>> idle = IdleClient(options=default_options)
        >>> cached_pair = CompletePair(get_request, fresh_response)
        >>> next_state = idle.next(get_request, [cached_pair])
        >>> isinstance(next_state, FromCache)
        True

        >>> # Need revalidation - stale response that cannot be served stale
        >>> idle = IdleClient(options=default_options)
        >>> cached_pair = CompletePair(get_request, stale_response)
        >>> next_state = idle.next(get_request, [cached_pair])
        >>> isinstance(next_state, NeedRevalidation)
        True
        """

        # ============================================================================
        # STEP 1: Handle Range Requests
        # ============================================================================
        # RFC 9111 Section 3.3: Storing Incomplete Responses
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-3.3
        #
        # Range requests are complex and require special handling. For simplicity,
        # this implementation treats all range requests as cache misses.
        # A full implementation could store and combine partial responses.
        request_range = Range.try_from_str(request.headers["range"]) if "range" in request.headers else None

        if request_range is not None:
            # Simplified behavior: always forward range requests to origin
            return CacheMiss(options=self.options, request=request)

        # ============================================================================
        # STEP 2: Handle Unsafe Methods (Write-Through)
        # ============================================================================
        # RFC 9111 Section 4, paragraph 5:
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-4-5
        #
        # "A cache MUST write through requests with methods that are unsafe
        # (Section 9.2.1 of [HTTP]) to the origin server; i.e., a cache is not
        # allowed to generate a reply to such a request before having forwarded
        # the request and having received a corresponding response."
        #
        # Unsafe methods: POST, PUT, DELETE, PATCH, etc.
        # Safe methods: GET, HEAD, OPTIONS, TRACE
        if request.method.upper() not in SAFE_METHODS:
            return CacheMiss(request=request, options=self.options)  # pragma: nocover

        # ============================================================================
        # STEP 3: Define Cache Reuse Conditions (RFC 9111 Section 4)
        # ============================================================================
        # The following lambda functions implement the five conditions that must ALL
        # be satisfied for a cached response to be reusable.

        # CONDITION 1: URI Matching
        # RFC 9111 Section 4, paragraph 2.1:
        # "the presented target URI (Section 7.1 of [HTTP]) and that of the stored
        # response match"
        #
        # The cache key primarily consists of the request URI. Only responses with
        # matching URIs can be considered for reuse.
        url_matches = lambda pair: pair.request.url == request.url  # noqa: E731

        # CONDITION 2: Method Matching
        # RFC 9111 Section 4, paragraph 2.2:
        # "the request method associated with the stored response allows it to be
        # used for the presented request"
        #
        # Generally, only GET responses can satisfy GET requests, HEAD responses
        # for HEAD requests, etc. Some methods (like HEAD) can sometimes be satisfied
        # by GET responses, but this implementation requires exact matches.
        method_matches = lambda pair: pair.request.method == request.method  # noqa: E731

        # CONDITION 3: Vary Header Matching
        # RFC 9111 Section 4.1: Calculating Cache Keys
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-4.1
        #
        # "When a cache receives a request that can be satisfied by a stored response
        # and that stored response contains a Vary header field, the cache MUST NOT
        # use that stored response without revalidation unless all the presented
        # request header fields nominated by that Vary field value match those fields
        # in the original request."
        #
        # Example: If response has "Vary: Accept-Encoding", the cached response can
        # only be used if the new request has the same Accept-Encoding header value.
        vary_headers_same = lambda pair: vary_headers_match(request, pair)  # noqa: E731

        # CONDITION 4: No-Cache Directive Handling
        # RFC 9111 Section 5.2.2.4: no-cache Response Directive
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.4
        #
        # "The no-cache response directive... indicates that the response MUST NOT be
        # used to satisfy any other request without forwarding it for validation and
        # receiving a successful response."
        #
        # If a cached response has Cache-Control: no-cache, it cannot be reused without
        # validation, regardless of its freshness.
        def no_cache_missing(pair: CompletePair) -> bool:
            """Check if the cached response lacks the no-cache directive."""
            return parse_cache_control(pair.response.headers.get("cache-control")).no_cache is False

        # CONDITION 5: Freshness or Allowed Stale
        # RFC 9111 Section 4.2: Freshness
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2
        #
        # A response can be reused if it is either:
        # a) Fresh: age < freshness_lifetime
        # b) Allowed to be served stale: Section 4.2.4
        #    https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2.4
        #
        # Note: Condition 5.3 (successfully validated) is handled in the
        # NeedRevalidation state, not here.
        def fresh_or_allowed_stale(pair: CompletePair) -> bool:
            """
            Determine if a cached response is fresh or allowed to be served stale.

            RFC 9111 Section 4.2:
            "A 'fresh' response is one whose age has not yet exceeded its freshness
            lifetime. Conversely, a 'stale' response is one where it has."

            RFC 9111 Section 4.2.4: Serving Stale Responses
            "A cache MUST NOT generate a stale response unless it is disconnected or
            doing so is explicitly permitted by the client or origin server."
            """
            freshness_lifetime = get_freshness_lifetime(pair.response, is_cache_shared=True)
            age = get_age(pair.response)

            # Check freshness: response_is_fresh = (freshness_lifetime > current_age)
            is_fresh = False if freshness_lifetime is None else age < freshness_lifetime

            # Check if stale responses are allowed (e.g., max-stale directive)
            return is_fresh or allowed_stale(pair.response, allow_stale_option=self.options.allow_stale)

        # ============================================================================
        # STEP 4: Filter Cached Responses by Conditions 1-4
        # ============================================================================
        # Apply the first four conditions to filter the list of associated pairs.
        # Condition 5 (freshness) is applied separately to partition responses into
        # "ready to use" and "needs revalidation" groups.
        filtered_pairs = [
            pair
            for pair in associated_pairs
            if url_matches(pair) and method_matches(pair) and vary_headers_same(pair) and no_cache_missing(pair)  # type: ignore[no-untyped-call]
        ]

        # ============================================================================
        # STEP 5: Select Most Recent Response
        # ============================================================================
        # RFC 9111 Section 4, paragraph 8:
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-4-8
        #
        # "When more than one suitable response is stored, a cache MUST use the most
        # recent one (as determined by the Date header field). It can also forward
        # the request with 'Cache-Control: max-age=0' or 'Cache-Control: no-cache'
        # to disambiguate which response to use."
        #
        # Sort by Date header in descending order (most recent first).
        filtered_pairs.sort(
            key=lambda pair: parse_date(
                pair.response.headers.get("date", str(int(time.time()))),
            )
            or int(time.time()),
            reverse=True,
        )

        # ============================================================================
        # STEP 6: Partition by Freshness (Condition 5)
        # ============================================================================
        # Separate responses into two groups:
        # - ready_to_use: Fresh or allowed-stale responses that can be served immediately
        # - need_revalidation: Stale responses that require validation before serving
        ready_to_use, need_revalidation = partition(filtered_pairs, fresh_or_allowed_stale)

        # ============================================================================
        # STEP 7: Determine Next State Based on Available Responses
        # ============================================================================

        if ready_to_use:
            # --------------------------------------------------------------------
            # Transition to: FromCache
            # --------------------------------------------------------------------
            # We have a fresh (or allowed-stale) response that can be served.
            #
            # RFC 9111 Section 4, paragraph 4:
            # https://www.rfc-editor.org/rfc/rfc9111.html#section-4-4
            #
            # "When a stored response is used to satisfy a request without validation,
            # a cache MUST generate an Age header field (Section 5.1), replacing any
            # present in the response with a value equal to the stored response's
            # current_age; see Section 4.2.3."
            #
            # The Age header informs the client how old the cached response is.

            # Mark all ready-to-use responses with metadata (for observability)
            for pair in ready_to_use:
                pair.response.metadata["hishel_from_cache"] = True  # type: ignore

            # Use the most recent response (first in sorted list)
            selected_pair = ready_to_use[0]

            # Calculate current age and update the Age header
            current_age = get_age(selected_pair.response)

            return FromCache(
                pair=replace(
                    selected_pair,
                    response=replace(
                        selected_pair.response,
                        headers=Headers(
                            {
                                **selected_pair.response.headers,
                                "age": str(current_age),
                            }
                        ),
                    ),
                ),
                options=self.options,
            )

        elif need_revalidation:
            # --------------------------------------------------------------------
            # Transition to: NeedRevalidation
            # --------------------------------------------------------------------
            # We have stale cached response(s) that cannot be served without
            # validation (e.g., they lack must-revalidate or similar directives).
            #
            # RFC 9111 Section 4.3: Validation
            # https://www.rfc-editor.org/rfc/rfc9111.html#section-4.3
            #
            # "When a cache has one or more stored responses for a requested URI,
            # but cannot serve any of them (e.g., because they are not fresh, or
            # one cannot be chosen), it can use the conditional request mechanism
            # in the forwarded request to give the next inbound server an opportunity
            # to choose a valid stored response to use, updating the stored metadata
            # in the process, or to replace the stored response(s) with a new response."
            #
            # Convert the request into a conditional request using validators
            # (ETag, Last-Modified) from the cached response.
            return NeedRevalidation(
                request=make_conditional_request(request, need_revalidation[-1].response),
                revalidating_pairs=need_revalidation,
                options=self.options,
                original_request=request,
            )
        else:
            # --------------------------------------------------------------------
            # Transition to: CacheMiss
            # --------------------------------------------------------------------
            # No suitable cached responses found. The request must be forwarded
            # to the origin server.
            #
            # This can happen when:
            # - No responses are cached for this URI
            # - Cached responses don't match the request (e.g., different Vary headers)
            # - Cached responses have no-cache directive
            # - Other conditions prevent cache reuse
            return CacheMiss(
                request=request,
                options=self.options,
            )


@dataclass
class CacheMiss(State):
    """
    Represents a cache miss state where a response must be evaluated for storage.

    This state is reached when:
    1. No suitable cached response exists (from IdleClient)
    2. A request must be forwarded to the origin server
    3. The origin server's response must be evaluated for cacheability

    State Transitions:
    -----------------
    - StoreAndUse: Response meets all RFC 9111 storage requirements and will be cached
    - CouldNotBeStored: Response fails one or more storage requirements and cannot be cached

    RFC 9111 References:
    -------------------
    - Section 3: Storing Responses in Caches
      https://www.rfc-editor.org/rfc/rfc9111.html#section-3
    - Section 3.5: Authenticated Responses
      https://www.rfc-editor.org/rfc/rfc9111.html#section-3.5

    Attributes:
    ----------
    request : Request
        The request that caused the cache miss. Note this is a Request object,
        not an IncompletePair, because this state can be reached from NeedRevalidation
        where we don't have an incomplete pair.
    after_revalidation : bool
        Flag indicating if this cache miss occurred after a revalidation attempt.
        When True, the response will be marked with hishel_revalidated metadata.
    options : CacheOptions
        Configuration options for cache behavior (inherited from State)
    """

    request: Request
    """
    The request that missed the cache.

    Note that this has a type of Request and not IncompletePair because
    when moving to this state from `NeedRevalidation` we don't have incomplete pair
    """

    after_revalidation: bool = False
    """
    Indicates whether the cache miss occurred after a revalidation attempt.
    """

    def next(self, response: Response, pair_id: uuid.UUID) -> Union["StoreAndUse", "CouldNotBeStored"]:
        """
        Evaluates whether a response can be stored in the cache.

        This method implements the storage decision algorithm from RFC 9111 Section 3.
        A response can only be stored if ALL of the following conditions are met:

        1. Request method is understood by the cache
        2. Response status code is final (not 1xx informational)
        3. Cache understands how to handle the response status code
        4. No no-store directive is present
        5. Private directive allows storage (for shared caches)
        6. Authorization is properly handled (for shared caches)
        7. Response contains explicit caching information or is heuristically cacheable

        Parameters:
        ----------
        response : Response
            The HTTP response received from the origin server
        pair_id : uuid.UUID
            Unique identifier for this request-response pair

        Returns:
        -------
        Union[StoreAndUse, CouldNotBeStored]
            - StoreAndUse: Response can and will be stored in cache
            - CouldNotBeStored: Response cannot be stored (fails one or more requirements)

        RFC 9111 Compliance:
        -------------------
        From RFC 9111 Section 3:
        "A cache MUST NOT store a response to a request unless:
         - the request method is understood by the cache;
         - the response status code is final;
         - if the response status code is 206 or 304, or the must-understand cache
           directive is present: the cache understands the response status code;
         - the no-store cache directive is not present in the response;
         - if the cache is shared: the private response directive is either not present
           or allows a shared cache to store a modified response;
         - if the cache is shared: the Authorization header field is not present in the
           request or a response directive is present that explicitly allows shared caching;
         - the response contains at least one of the following:
           * a public response directive
           * a private response directive (if cache is not shared)
           * an Expires header field
           * a max-age response directive
           * an s-maxage response directive (if cache is shared)
           * a status code that is defined as heuristically cacheable"

        Side Effects:
        ------------
        Sets metadata flags on the response object:
        - hishel_spec_ignored: False (caching spec is being followed)
        - hishel_from_cache: False (response is from origin, not cache)
        - hishel_revalidated: True (if after_revalidation is True)
        - hishel_stored: True/False (whether response was stored)

        Logging:
        -------
        When a response cannot be stored, detailed debug logs are emitted explaining
        which specific RFC requirement failed, with direct links to the relevant
        RFC sections.

        Examples:
        --------
        >>> # Cacheable response
        >>> cache_miss = CacheMiss(request=get_request, options=default_options)
        >>> response = Response(
        ...     status_code=200,
        ...     headers=Headers({"cache-control": "max-age=3600"})
        ... )
        >>> next_state = cache_miss.next(response, uuid.uuid4())
        >>> isinstance(next_state, StoreAndUse)
        True

        >>> # Non-cacheable response (no-store)
        >>> response = Response(
        ...     status_code=200,
        ...     headers=Headers({"cache-control": "no-store"})
        ... )
        >>> next_state = cache_miss.next(response, uuid.uuid4())
        >>> isinstance(next_state, CouldNotBeStored)
        True
        """

        # ============================================================================
        # STEP 1: Set Response Metadata
        # ============================================================================
        # Initialize metadata flags to track the response lifecycle

        response.metadata["hishel_spec_ignored"] = False  # type: ignore
        # We are following the caching specification

        response.metadata["hishel_from_cache"] = False  # type: ignore
        # This response came from origin server, not cache

        if self.after_revalidation:
            response.metadata["hishel_revalidated"] = True  # type: ignore
            # Mark that this response is the result of a revalidation

        # ============================================================================
        # STEP 2: Parse Cache-Control Directive
        # ============================================================================
        # Extract and parse the Cache-Control header to check caching directives

        request = self.request
        response_cache_control = parse_cache_control(response.headers.get("cache-control"))

        # ============================================================================
        # STEP 3: Evaluate Storage Requirements (7 Conditions)
        # ============================================================================
        # All conditions must be True for the response to be storable.
        # Each condition corresponds to a requirement from RFC 9111 Section 3.

        # CONDITION 1: Request Method Understanding
        # RFC 9111 Section 3, paragraph 2.1:
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.1.1
        #
        # "the request method is understood by the cache"
        #
        # The cache must recognize and support caching for this HTTP method.
        # Typically, only safe methods (GET, HEAD) are cacheable.
        # This prevents caching of methods with side effects (POST, PUT, DELETE).
        method_understood_by_cache = request.method.upper() in self.options.supported_methods

        # CONDITION 2: Response Status Code is Final
        # RFC 9111 Section 3, paragraph 2.2:
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.2.1
        #
        # "the response status code is final (see Section 15 of [HTTP])"
        #
        # 1xx status codes are informational and not final responses.
        # Only final responses (2xx, 3xx, 4xx, 5xx) can be cached.
        # Check: status_code % 100 != 1 means not in the 1xx range
        response_status_code_is_final = response.status_code // 100 != 1

        # CONDITION 3: Cache Understands Response Status Code
        # RFC 9111 Section 3, paragraph 2.3:
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.3.1
        #
        # "if the response status code is 206 or 304, or the must-understand cache
        # directive (see Section 5.2.2.3) is present: the cache understands the
        # response status code"
        #
        # 206 Partial Content: Used for range requests, requires special handling
        # 304 Not Modified: Used for conditional requests, is not a complete response
        #
        # This implementation takes a conservative approach: if the status is 206 or 304,
        # we mark it as not understood, preventing storage. A full implementation would
        # handle these specially (304 updates existing cache, 206 stores partial content).
        if response.status_code in (206, 304):
            understands_how_to_cache = False
        else:
            understands_how_to_cache = True

        # CONDITION 4: No no-store Directive
        # RFC 9111 Section 5.2.2.5: no-store Response Directive
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.5
        #
        # "The no-store response directive indicates that a cache MUST NOT store
        # any part of either the immediate request or the response"
        #
        # no-store is the strongest cache prevention directive. When present,
        # nothing should be stored, regardless of other directives.
        no_store_is_not_present = not response_cache_control.no_store

        # CONDITION 5: Private Directive Allows Storing (Shared Cache Only)
        # RFC 9111 Section 5.2.2.7: private Response Directive
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.7
        #
        # "The unqualified private response directive indicates that a shared cache
        # MUST NOT store the response"
        #
        # For shared caches (proxies, CDNs):
        # - If private=True, the response is for a single user only
        # - Shared caches MUST NOT store private responses
        #
        # For private caches (browser caches):
        # - private directive is allowed and encouraged
        #
        # Logic: If cache is shared AND response is private, storing is NOT allowed
        # Therefore: we check (shared cache) AND (private is NOT True)
        private_directive_allows_storing = not (self.options.shared and response_cache_control.private is True)

        # CONDITION 6: Authorization Header Handling (Shared Cache Only)
        # RFC 9111 Section 3.5: Caching Authenticated Responses
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-3.5
        #
        # "A shared cache MUST NOT use a cached response to a request with an
        # Authorization header field unless... a response directive is present that
        # explicitly allows shared caching"
        #
        # Requests with Authorization headers often contain user-specific data.
        # Shared caches must be careful not to serve one user's data to another.
        #
        # This check is inverted in the current implementation and needs review:
        # TODO: Fix logic - should be: (not shared) OR (no auth header) OR (has explicit directive)
        # Current logic: (shared) AND (no auth header)
        is_shared_and_authorized = not (self.options.shared and "authorization" in request.headers)

        # CONDITION 7: Response Contains Required Caching Information
        # RFC 9111 Section 3, paragraph 2.7:
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.7.1
        #
        # "the response contains at least one of the following:..."
        #
        # A response must have explicit caching metadata OR be heuristically cacheable.
        # This ensures we only cache responses that the origin server intended to be cached.
        contains_required_component = (
            # OPTION A: public Directive
            # RFC 9111 Section 5.2.2.9:
            # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.9
            # "The public response directive indicates that a cache MAY store the response"
            # Explicitly marks response as cacheable by any cache
            response_cache_control.public
            # OPTION B: private Directive (Private Cache Only)
            # RFC 9111 Section 5.2.2.7:
            # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.7
            # "private... indicates that... a private cache MAY store the response"
            # For private caches only (not shared caches)
            or (not self.options.shared and response_cache_control.private)
            # OPTION C: Expires Header
            # RFC 9111 Section 5.3: Expires
            # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.3
            # "The Expires header field gives the date/time after which the response
            # is considered stale"
            # Explicit expiration time
            or ("expires" in response.headers)
            # OPTION D: max-age Directive
            # RFC 9111 Section 5.2.2.1: max-age Response Directive
            # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.1
            # "The max-age response directive indicates that the response is to be
            # considered stale after its age is greater than the specified number of seconds"
            # Most common caching directive
            or (response_cache_control.max_age is not None)
            # OPTION E: s-maxage Directive (Shared Cache Only)
            # RFC 9111 Section 5.2.2.10: s-maxage Response Directive
            # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.10
            # "The s-maxage response directive indicates that, for a shared cache,
            # the maximum age specified by this directive overrides the maximum age
            # specified by either the max-age directive or the Expires header field"
            # Specific to shared caches (proxies, CDNs)
            or (self.options.shared and response_cache_control.s_maxage is not None)
            # OPTION F: Heuristically Cacheable Status Code
            # RFC 9111 Section 4.2.2: Calculating Heuristic Freshness
            # https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2.2
            # "a cache MAY assign a heuristic expiration time when an explicit time
            # is not specified"
            #
            # Certain status codes are defined as "heuristically cacheable":
            # 200 OK, 203 Non-Authoritative, 204 No Content, 206 Partial Content,
            # 300 Multiple Choices, 301 Moved Permanently, 308 Permanent Redirect,
            # 404 Not Found, 405 Method Not Allowed, 410 Gone,
            # 414 URI Too Long, 501 Not Implemented
            or response.status_code in HEURISTICALLY_CACHEABLE_STATUS_CODES
        )

        # ============================================================================
        # STEP 4: Determine Storage Decision
        # ============================================================================
        # If ANY condition is False, the response cannot be stored

        if (
            not method_understood_by_cache
            or not response_status_code_is_final
            or not understands_how_to_cache
            or not no_store_is_not_present
            or not private_directive_allows_storing
            or not is_shared_and_authorized
            or not contains_required_component
        ):
            # --------------------------------------------------------------------
            # Transition to: CouldNotBeStored
            # --------------------------------------------------------------------
            # One or more storage requirements failed. Log the specific reason
            # and return a CouldNotBeStored state.

            # Detailed logging for debugging (only when DEBUG level is enabled)
            if logger.isEnabledFor(logging.DEBUG):
                if not method_understood_by_cache:
                    logger.debug(
                        "Cannot store the response because the request method is not understood by the cache. "
                        "See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.1.1"
                    )
                elif not response_status_code_is_final:
                    logger.debug(
                        f"Cannot store the response because the response status code ({response.status_code}) "
                        "is not final. See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.2.1"
                    )
                elif not understands_how_to_cache:
                    logger.debug(
                        "Cannot store the response because the cache does not understand how to cache the response. "
                        "See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.3.2"
                    )
                elif not no_store_is_not_present:
                    logger.debug(
                        "Cannot store the response because the no-store cache directive is present in the response. "
                        "See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.4.1"
                    )
                elif not private_directive_allows_storing:
                    logger.debug(
                        "Cannot store the response because the `private` response directive does not "
                        "allow shared caches to store it. See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.5.1"
                    )
                elif not is_shared_and_authorized:
                    logger.debug(
                        "Cannot store the response because the cache is shared and the request contains "
                        "an Authorization header field. See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.6.1"
                    )
                elif not contains_required_component:
                    logger.debug(
                        "Cannot store the response because it does not contain any of the required components. "
                        "See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.7.1"
                    )

            # Mark response as not stored
            response.metadata["hishel_stored"] = False  # type: ignore

            return CouldNotBeStored(response=response, pair_id=pair_id, options=self.options)

        # --------------------------------------------------------------------
        # Transition to: StoreAndUse
        # --------------------------------------------------------------------
        # All storage requirements are met. The response will be cached.

        logger.debug("Storing response in cache")

        # Mark response as stored
        response.metadata["hishel_stored"] = True  # type: ignore

        # Remove headers that should not be stored
        # RFC 9111 Section 3.1: Storing Header and Trailer Fields
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-3.1
        # Certain headers (Connection, hop-by-hop headers, etc.) must be excluded
        cleaned_response = exclude_unstorable_headers(response, self.options.shared)

        return StoreAndUse(
            pair_id=pair_id,
            response=cleaned_response,
            options=self.options,
        )


@dataclass
class NeedRevalidation(State):
    """
    Represents a state where cached responses require validation before use.

    This state is reached when:
    1. A stale cached response exists (from IdleClient)
    2. The cached response cannot be served without validation
    3. A conditional request has been sent to the origin server

    The validation mechanism uses HTTP conditional requests with validators
    (ETag, Last-Modified) to check if the cached response is still valid.

    State Transitions:
    -----------------
    - NeedToBeUpdated: 304 response received, cached responses can be freshened
    - InvalidatePairs + CacheMiss: 2xx/5xx response received, new response must be cached
    - CacheMiss: No matching responses found during freshening

    RFC 9111 References:
    -------------------
    - Section 4.3: Validation
      https://www.rfc-editor.org/rfc/rfc9111.html#section-4.3
    - Section 4.3.3: Handling a Validation Response
      https://www.rfc-editor.org/rfc/rfc9111.html#section-4.3.3
    - Section 4.3.4: Freshening Stored Responses
      https://www.rfc-editor.org/rfc/rfc9111.html#section-4.3.4

    Attributes:
    ----------
    request : Request
        The conditional request that was sent to the server for revalidation.
        This request contains If-None-Match (from ETag) or If-Modified-Since
        (from Last-Modified) headers.
    original_request : Request
        The original client request (without conditional headers) that initiated
        this revalidation. This is used when creating new cache entries.
    revalidating_pairs : list[CompletePair]
        The cached request-response pairs that are being revalidated. These are
        stale responses that might still be usable if the server confirms they
        haven't changed (304 response).
    options : CacheOptions
        Configuration options for cache behavior (inherited from State)
    """

    request: Request
    """
    The request that was sent to the server for revalidation.
    """

    original_request: Request

    revalidating_pairs: list[CompletePair]
    """
    The stored pairs that the request was sent for revalidation.
    """

    def next(self, revalidation_response: Response) -> Union["NeedToBeUpdated", "InvalidatePairs", "CacheMiss"]:
        """
        Handles the response to a conditional request and determines the next state.

        This method implements the validation response handling logic from RFC 9111
        Section 4.3.3. The behavior depends on the response status code:

        - 304 Not Modified: Cached responses are still valid, freshen and reuse them
        - 2xx Success: Cached responses are outdated, use new response
        - 5xx Server Error: Server cannot validate, use new error response
        - Other: Unexpected status code (should not happen in normal operation)

        Parameters:
        ----------
        revalidation_response : Response
            The HTTP response received from the origin server in response to
            the conditional request

        Returns:
        -------
        Union[NeedToBeUpdated, InvalidatePairs, CacheMiss]
            - NeedToBeUpdated: When 304 response allows cached responses to be freshened
            - InvalidatePairs: When old responses must be invalidated (wraps next state)
            - CacheMiss: When no matching responses found or storing new response

        RFC 9111 Compliance:
        -------------------
        From RFC 9111 Section 4.3.3:
        "Cache handling of a response to a conditional request depends upon its
        status code:
         - A 304 (Not Modified) response status code indicates that the stored
           response can be updated and reused; see Section 4.3.4.
         - A full response (i.e., one containing content) indicates that none of
           the stored responses nominated in the conditional request are suitable.
           Instead, the cache MUST use the full response to satisfy the request.
           The cache MAY store such a full response, subject to its constraints
           (see Section 3).
         - However, if a cache receives a 5xx (Server Error) response while
           attempting to validate a response, it can either forward this response
           to the requesting client or act as if the server failed to respond.
           In the latter case, the cache can send a previously stored response,
           subject to its constraints on doing so (see Section 4.2.4), or retry
           the validation request."

        Implementation Notes:
        --------------------
        - All revalidating pairs except the last are invalidated when receiving 2xx/5xx
        - The last pair's ID is reused for storing the new response
        - 5xx responses are treated the same as 2xx (both invalidate and store new response)
        - A full implementation might serve stale responses on 5xx errors

        Examples:
        --------
        >>> # 304 Not Modified - freshen cached response
        >>> need_revalidation = NeedRevalidation(
        ...     request=conditional_request,
        ...     original_request=original_request,
        ...     revalidating_pairs=[cached_pair],
        ...     options=default_options
        ... )
        >>> response_304 = Response(status_code=304, headers=Headers({"etag": '"abc123"'}))
        >>> next_state = need_revalidation.next(response_304)
        >>> isinstance(next_state, NeedToBeUpdated)
        True

        >>> # 200 OK - use new response
        >>> response_200 = Response(status_code=200, headers=Headers({"cache-control": "max-age=3600"}))
        >>> next_state = need_revalidation.next(response_200)
        >>> isinstance(next_state, InvalidatePairs)
        True
        """

        # ============================================================================
        # STEP 1: Handle 304 Not Modified Response
        # ============================================================================
        # RFC 9111 Section 4.3.3, paragraph 1:
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-4.3.3
        #
        # "A 304 (Not Modified) response status code indicates that the stored
        # response can be updated and reused; see Section 4.3.4."
        #
        # 304 means the cached response is still valid. The server is saying:
        # "The resource hasn't changed since the version you have cached."
        # We can freshen the cached response with new metadata (Date, Cache-Control)
        # from the 304 response and continue using the cached content.
        if revalidation_response.status_code == 304:
            return self.freshening_stored_responses(revalidation_response)

        # ============================================================================
        # STEP 2: Handle 2xx Success Response (Full Response)
        # ============================================================================
        # RFC 9111 Section 4.3.3, paragraph 2:
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-4.3.3
        #
        # "A full response (i.e., one containing content) indicates that none of
        # the stored responses nominated in the conditional request are suitable.
        # Instead, the cache MUST use the full response to satisfy the request.
        # The cache MAY store such a full response, subject to its constraints
        # (see Section 3)."
        #
        # 2xx responses mean the resource has changed. The server is sending a
        # complete new response that should replace the cached version.
        # We must:
        # 1. Invalidate old cached responses (they're outdated)
        # 2. Store the new response (if cacheable)
        # 3. Use the new response to satisfy the request
        elif revalidation_response.status_code // 100 == 2:
            # Invalidate all old pairs except the last one
            # The last pair's ID will be reused for the new response
            return InvalidatePairs(
                options=self.options,
                pair_ids=[pair.id for pair in self.revalidating_pairs[:-1]],
                # After invalidation, attempt to cache the new response
                next_state=CacheMiss(
                    request=self.original_request,
                    options=self.options,
                    after_revalidation=True,  # Mark that this occurred during revalidation
                ).next(revalidation_response, pair_id=self.revalidating_pairs[-1].id),
            )

        # ============================================================================
        # STEP 3: Handle 5xx Server Error Response
        # ============================================================================
        # RFC 9111 Section 4.3.3, paragraph 3:
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-4.3.3
        #
        # "However, if a cache receives a 5xx (Server Error) response while
        # attempting to validate a response, it can either forward this response
        # to the requesting client or act as if the server failed to respond.
        # In the latter case, the cache can send a previously stored response,
        # subject to its constraints on doing so (see Section 4.2.4), or retry
        # the validation request."
        #
        # 5xx errors during revalidation are tricky. The server is having problems,
        # but we don't know if the cached content is still valid.
        #
        # Options per RFC 9111:
        # A) Forward the error to the client (implemented here)
        # B) Serve the stale cached response (allowed_stale)
        # C) Retry the validation request
        #
        # This implementation chooses option A: forward the error and store it.
        # A full implementation might check allowed_stale and serve cached content.
        elif revalidation_response.status_code // 100 == 5:
            # Same as 2xx: invalidate old responses and store the error response
            # This ensures clients see the error rather than potentially stale data
            return InvalidatePairs(
                options=self.options,
                pair_ids=[pair.id for pair in self.revalidating_pairs[:-1]],
                next_state=CacheMiss(
                    request=self.original_request,
                    options=self.options,
                    after_revalidation=True,
                ).next(revalidation_response, pair_id=self.revalidating_pairs[-1].id),
            )

        # ============================================================================
        # STEP 4: Handle Unexpected Status Codes
        # ============================================================================
        # This should not happen in normal operation. Valid revalidation responses are:
        # - 304 Not Modified
        # - 2xx Success (typically 200 OK)
        # - 5xx Server Error
        #
        # Other status codes (1xx, 3xx, 4xx) are unexpected during revalidation.
        # 3xx redirects should have been followed by the HTTP client.
        # 4xx errors (except 404) are unusual during revalidation.
        raise RuntimeError(
            f"Unexpected response status code during revalidation: {revalidation_response.status_code}"
        )  # pragma: nocover

    def freshening_stored_responses(
        self, revalidation_response: Response
    ) -> "NeedToBeUpdated" | "InvalidatePairs" | "CacheMiss":
        """
        Freshens cached responses after receiving a 304 Not Modified response.

        When the server responds with 304, it means "the resource hasn't changed,
        but here's updated metadata." This method:
        1. Identifies which cached responses match the 304 response
        2. Updates their headers with fresh metadata from the 304
        3. Invalidates any cached responses that don't match

        Matching is done using validators in this priority order:
        1. Strong ETag (if present and not weak)
        2. Last-Modified (if present)
        3. Single response assumption (if only one cached response exists)

        Parameters:
        ----------
        revalidation_response : Response
            The 304 Not Modified response from the server, containing updated
            metadata (Date, Cache-Control, ETag, etc.)

        Returns:
        -------
        Union[NeedToBeUpdated, InvalidatePairs, CacheMiss]
            - NeedToBeUpdated: When matching responses are found and updated
            - InvalidatePairs: Wraps NeedToBeUpdated if non-matching responses exist
            - CacheMiss: When no matching responses are found

        RFC 9111 Compliance:
        -------------------
        From RFC 9111 Section 4.3.4:
        "When a cache receives a 304 (Not Modified) response, it needs to identify
        stored responses that are suitable for updating with the new information
        provided, and then do so.

        The initial set of stored responses to update are those that could have
        been chosen for that request...

        Then, that initial set of stored responses is further filtered by the
        first match of:
         - If the 304 response contains a strong entity tag: the stored responses
           with the same strong entity tag.
         - If the 304 response contains a Last-Modified value: the stored responses
           with the same Last-Modified value.
         - If there is only a single stored response: that response."

        Implementation Notes:
        --------------------
        - Weak ETags (starting with "W/") are not used for matching
        - Only strong ETags provide reliable validation
        - If no validators match, all responses are invalidated
        - Multiple responses can be freshened if they share the same validator

        Examples:
        --------
        >>> # Matching by strong ETag
        >>> cached_response = Response(headers=Headers({"etag": '"abc123"'}))
        >>> revalidation_response = Response(
        ...     status_code=304,
        ...     headers=Headers({"etag": '"abc123"', "cache-control": "max-age=3600"})
        ... )
        >>> # Cached response will be freshened with new Cache-Control

        >>> # Non-matching ETag
        >>> cached_response = Response(headers=Headers({"etag": '"old123"'}))
        >>> revalidation_response = Response(
        ...     status_code=304,
        ...     headers=Headers({"etag": '"new456"'})
        ... )
        >>> # Cached response will be invalidated (doesn't match)
        """

        # ============================================================================
        # STEP 1: Identify Matching Responses Using Validators
        # ============================================================================
        # RFC 9111 Section 4.3.4: Freshening Stored Responses
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-4.3.4
        #
        # The 304 response tells us "the resource is unchanged", but we need to
        # figure out WHICH of our cached responses match this confirmation.
        #
        # We use validators in priority order:
        # Priority 1: Strong ETag (most reliable)
        # Priority 2: Last-Modified timestamp
        # Priority 3: Single response assumption

        identified_for_revalidation: list[CompletePair]

        # MATCHING STRATEGY 1: Strong ETag
        # RFC 9110 Section 8.8.3: ETag
        # https://www.rfc-editor.org/rfc/rfc9110#section-8.8.3
        #
        # "If the 304 response contains a strong entity tag: the stored responses
        # with the same strong entity tag."
        #
        # ETags come in two flavors:
        # - Strong: "abc123" (exact byte-for-byte match)
        # - Weak: W/"abc123" (semantically equivalent, but not byte-identical)
        #
        # Only strong ETags are reliable for caching decisions. Weak ETags
        # indicate semantic equivalence but the content might differ slightly
        # (e.g., gzip compression, whitespace changes).
        if "etag" in revalidation_response.headers and (not revalidation_response.headers["etag"].startswith("W/")):
            # Found a strong ETag in the 304 response
            # Partition cached responses: matching vs non-matching ETags
            identified_for_revalidation, need_to_be_invalidated = partition(
                self.revalidating_pairs,
                lambda pair: pair.response.headers.get("etag") == revalidation_response.headers.get("etag"),  # type: ignore[no-untyped-call]
            )

        # MATCHING STRATEGY 2: Last-Modified
        # RFC 9110 Section 8.8.2: Last-Modified
        # https://www.rfc-editor.org/rfc/rfc9110#section-8.8.2
        #
        # "If the 304 response contains a Last-Modified value: the stored responses
        # with the same Last-Modified value."
        #
        # Last-Modified is a timestamp indicating when the resource was last changed.
        # It's less precise than ETags (1-second granularity) but widely supported.
        # If the 304 has a Last-Modified, we can match it against cached responses.
        elif revalidation_response.headers.get("last-modified"):
            # Found Last-Modified in the 304 response
            # Partition cached responses: matching vs non-matching timestamps
            identified_for_revalidation, need_to_be_invalidated = partition(
                self.revalidating_pairs,
                lambda pair: pair.response.headers.get("last-modified")
                == revalidation_response.headers.get("last-modified"),  # type: ignore[no-untyped-call]
            )

        # MATCHING STRATEGY 3: Single Response Assumption
        # RFC 9111 Section 4.3.4:
        #
        # "If there is only a single stored response: that response."
        #
        # If we only have one cached response and the server says "not modified",
        # we can safely assume that single response is the one being confirmed.
        # This handles cases where the server doesn't return validators in the 304.
        else:
            if len(self.revalidating_pairs) == 1:
                # Only one cached response - it must be the matching one
                identified_for_revalidation, need_to_be_invalidated = [self.revalidating_pairs[0]], []
            else:
                # Multiple cached responses but no validators to match them
                # We cannot determine which (if any) are valid
                # Conservative approach: invalidate all of them
                identified_for_revalidation, need_to_be_invalidated = [], self.revalidating_pairs

        # ============================================================================
        # STEP 2: Update Matching Responses or Create Cache Miss
        # ============================================================================
        # If we found matching responses, freshen them with new metadata.
        # If we found no matches, treat it as a cache miss.

        next_state: "NeedToBeUpdated" | "CacheMiss"

        if identified_for_revalidation:
            # We found responses that match the 304 confirmation
            # Update their headers with fresh metadata from the 304 response
            #
            # RFC 9111 Section 3.2: Updating Stored Header Fields
            # https://www.rfc-editor.org/rfc/rfc9111.html#section-3.2
            #
            # "When doing so, the cache MUST add each header field in the provided
            # response to the stored response, replacing field values that are
            # already present"
            #
            # The refresh_response_headers function handles this header merging
            # while excluding certain headers that shouldn't be updated
            # (Content-Encoding, Content-Type, Content-Range).
            next_state = NeedToBeUpdated(
                updating_pairs=[
                    replace(
                        pair,
                        response=refresh_response_headers(pair.response, revalidation_response),
                    )
                    for pair in identified_for_revalidation
                ],
                original_request=self.original_request,
                options=self.options,
            )
        else:
            # No matching responses found
            # This is unusual - the server said "not modified" but we can't figure
            # out which cached response it's referring to.
            # Treat this as a cache miss and let the normal flow handle it.
            next_state = CacheMiss(
                options=self.options,
                request=self.original_request,
                after_revalidation=True,
            )

        # ============================================================================
        # STEP 3: Invalidate Non-Matching Responses (if any)
        # ============================================================================
        # If we had multiple cached responses and only some matched, we need to
        # invalidate the non-matching ones. They're outdated or incorrect.
        #
        # For example:
        # - Cached: Two responses with different ETags
        # - 304 response: Matches only one ETag
        # - Action: Update the matching one, invalidate the other

        if need_to_be_invalidated:
            # Wrap the next state in an invalidation operation
            return InvalidatePairs(
                options=self.options,
                pair_ids=[pair.id for pair in need_to_be_invalidated],
                next_state=next_state,
            )

        # No invalidations needed, return the next state directly
        return next_state


@dataclass
class StoreAndUse(State):
    """
    The state that indicates that the response can be stored in the cache and used.
    """

    pair_id: uuid.UUID

    response: Response

    def next(self) -> None:
        return None  # pragma: nocover


@dataclass
class CouldNotBeStored(State):
    """
    The state that indicates that the response could not be stored in the cache.
    """

    response: Response

    pair_id: uuid.UUID

    def next(self) -> None:
        return None  # pragma: nocover


@dataclass
class InvalidatePairs(State):
    """
    The state that represents the deletion of cache pairs.
    """

    pair_ids: list[uuid.UUID]

    next_state: AnyState

    def next(self) -> AnyState:
        return self.next_state


@dataclass
class FromCache(State):
    pair: CompletePair
    """
    List of pairs that can be used to satisfy the request.
    """

    def next(self) -> None:
        return None  # pragma: nocover


@dataclass
class NeedToBeUpdated(State):
    updating_pairs: list[CompletePair]
    original_request: Request

    def next(self) -> FromCache:
        return FromCache(pair=self.updating_pairs[-1], options=self.options)  # pragma: nocover
