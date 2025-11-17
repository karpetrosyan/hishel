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
    Optional,
    TypeVar,
    Union,
)

from hishel._core._headers import Headers, Range, Vary, parse_cache_control
from hishel._core.models import ResponseMetadata
from hishel._utils import parse_date, partition

if TYPE_CHECKING:
    from hishel import Entry, Request, Response


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
    """
    Configuration options for HTTP cache behavior.

    These options control how the cache interprets and applies RFC 9111 caching rules.
    All options have sensible defaults that follow the specification.

    Attributes:
    ----------
    shared : bool
        Determines whether the cache operates as a shared cache or private cache.

        RFC 9111 Section 3.5: Authenticated Responses
        https://www.rfc-editor.org/rfc/rfc9111.html#section-3.5

        - Shared cache (True): Acts as a proxy, CDN, or gateway cache serving multiple users.
          Must respect private directives and Authorization header restrictions.
          Can use s-maxage directive instead of max-age for shared-specific freshness.

        - Private cache (False): Acts as a browser or user-agent cache for a single user.
          Can cache private responses and ignore s-maxage directives.

        Default: True (shared cache)

        Examples:
        --------
        >>> # Shared cache (proxy/CDN)
        >>> options = CacheOptions(shared=True)

        >>> # Private cache (browser)
        >>> options = CacheOptions(shared=False)

    supported_methods : list[str]
        HTTP methods that are allowed to be cached by this cache implementation.

        RFC 9111 Section 3, paragraph 2.1:
        https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.1.1

        "A cache MUST NOT store a response to a request unless:
         - the request method is understood by the cache"

        Default: ["GET", "HEAD"] (most commonly cached methods)

        Examples:
        --------
        >>> # Default: cache GET and HEAD only
        >>> options = CacheOptions()
        >>> options.supported_methods
        ['GET', 'HEAD']

        >>> # Cache POST responses (advanced use case)
        >>> options = CacheOptions(supported_methods=["GET", "HEAD", "POST"])

    allow_stale : bool
        Controls whether stale responses can be served without revalidation.

        RFC 9111 Section 4.2.4: Serving Stale Responses
        https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2.4

        "A cache MUST NOT generate a stale response unless it is disconnected or
        doing so is explicitly permitted by the client or origin server (e.g., by
        the max-stale request directive in Section 5.2.1, extension directives
        such as those defined in [RFC5861], or configuration in accordance with
        an out-of-band contract)."

        Default: False (no stale responses)

        Examples:
        --------
        >>> # Conservative: never serve stale
        >>> options = CacheOptions(allow_stale=False)

        >>> # Permissive: serve stale when allowed
        >>> options = CacheOptions(allow_stale=True)

        >>> # Stale-while-revalidate pattern (RFC 5861)
        >>> # Even with allow_stale=True, directives are respected
        >>> options = CacheOptions(allow_stale=True)
    """

    shared: bool = True
    """
    When True, the cache operates as a shared cache (proxy/CDN).
    When False, as a private cache (browser).
    """

    supported_methods: list[str] = field(default_factory=lambda: ["GET", "HEAD"])
    """HTTP methods that are allowed to be cached."""

    allow_stale: bool = False
    """When True, stale responses can be served without revalidation."""


@dataclass
class State(ABC):
    options: CacheOptions

    @abstractmethod
    def next(self, *args: Any, **kwargs: Any) -> Union["State", None]:
        raise NotImplementedError("Subclasses must implement this method")


def vary_headers_match(
    original_request: Request,
    associated_entry: Entry,
) -> bool:
    """
    Determines if request headers match the Vary requirements of a cached response.

    The Vary header specifies which request headers were used to select the
    representation. For a cached response to be reusable, all headers listed
    in Vary must match between the original and new requests.

    RFC 9111 Section 4.1: Calculating Cache Keys
    https://www.rfc-editor.org/rfc/rfc9111.html#section-4.1

    Parameters:
    ----------
    original_request : Request
        The new incoming request that we're trying to satisfy
    associated_entry : Entry
        A cached request-response entry that might match the new request

    Returns:
    -------
    bool
        True if the Vary headers match (or no Vary header exists),
        False if they don't match or Vary contains "*"

    RFC 9111 Compliance:
    -------------------
    From RFC 9111 Section 4.1:
    "When a cache receives a request that can be satisfied by a stored response
    and that stored response contains a Vary header field, the cache MUST NOT
    use that stored response without revalidation unless all the presented
    request header fields nominated by that Vary field value match those fields
    in the original request (i.e., the request that caused the cached response
    to be stored)."

    "The header fields from two requests are defined to match if and only if
    those in the first request can be transformed to those in the second request
    by applying any of the following:
     - adding or removing whitespace
     - combining multiple header field lines with the same field name
     - normalizing header field values"

    "A stored response with a Vary header field value containing a member '*'
    always fails to match."

    Examples:
    --------
    >>> # No Vary header - always matches
    >>> request = Request(headers=Headers({"accept": "application/json"}))
    >>> response = Response(headers=Headers({}))  # No Vary
    >>> entry = Entry(request=request, response=response)
    >>> vary_headers_match(request, entry)
    True

    >>> # Vary: Accept with matching Accept header
    >>> request1 = Request(headers=Headers({"accept": "application/json"}))
    >>> response = Response(headers=Headers({"vary": "Accept"}))
    >>> entry = Entry(request=request1, response=response)
    >>> request2 = Request(headers=Headers({"accept": "application/json"}))
    >>> vary_headers_match(request2, entry)
    True

    >>> # Vary: Accept with non-matching Accept header
    >>> request2 = Request(headers=Headers({"accept": "application/xml"}))
    >>> vary_headers_match(request2, entry)
    False

    >>> # Vary: * always fails
    >>> response = Response(headers=Headers({"vary": "*"}))
    >>> entry = Entry(request=request1, response=response)
    >>> vary_headers_match(request2, entry)
    False
    """
    # Extract the Vary header from the cached response
    vary_header = associated_entry.response.headers.get("vary")

    # If no Vary header exists, any request matches
    # The response doesn't vary based on request headers
    if not vary_header:
        return True

    # Parse the Vary header value into individual header names
    vary = Vary.from_value(vary_header)

    # Check each header name listed in Vary
    for vary_header in vary.values:
        # Special case: Vary: *
        # RFC 9111 Section 4.1: "A stored response with a Vary header field
        # value containing a member '*' always fails to match."
        #
        # Vary: * means the response varies on factors beyond request headers
        # (e.g., cookies, user agent state, time of day). It can never be matched.
        if vary_header == "*":
            return False

        # Compare the specific header value between original and new request
        # Both headers must have the same value (or both be absent)
        if original_request.headers.get(vary_header) != associated_entry.request.headers.get(vary_header):
            return False

    # All Vary headers matched
    return True


def get_freshness_lifetime(response: Response, is_cache_shared: bool) -> Optional[int]:
    """
    Calculates the freshness lifetime of a cached response in seconds.

    The freshness lifetime is the time period during which a cached response
    can be used without validation. It's determined by explicit directives
    (max-age, s-maxage, Expires) or heuristically calculated.

    RFC 9111 Section 4.2.1: Calculating Freshness Lifetime
    https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2.1

    Parameters:
    ----------
    response : Response
        The cached response to calculate freshness for
    is_cache_shared : bool
        True if this is a shared cache (proxy, CDN), False for private cache (browser)

    Returns:
    -------
    Optional[int]
        Freshness lifetime in seconds, or None if it cannot be determined

    RFC 9111 Compliance:
    -------------------
    From RFC 9111 Section 4.2.1:
    "A cache can calculate the freshness lifetime (denoted as freshness_lifetime)
    of a response by evaluating the following rules and using the first match:

     - If the cache is shared and the s-maxage response directive is present,
       use its value
     - If the max-age response directive is present, use its value
     - If the Expires response header field is present, use its value minus
       the value of the Date response header field
     - Otherwise, no explicit expiration time is present in the response.
       A heuristic freshness lifetime might be applicable; see Section 4.2.2"

    Priority Order:
    --------------
    1. s-maxage (shared caches only) - highest priority
    2. max-age - applies to all caches
    3. Expires - Date - legacy but still supported
    4. Heuristic freshness - calculated from Last-Modified

    Examples:
    --------
    >>> # max-age directive
    >>> response = Response(headers=Headers({"cache-control": "max-age=3600"}))
    >>> get_freshness_lifetime(response, is_cache_shared=True)
    3600

    >>> # s-maxage overrides max-age for shared caches
    >>> response = Response(headers=Headers({
    ...     "cache-control": "max-age=3600, s-maxage=7200"
    ... }))
    >>> get_freshness_lifetime(response, is_cache_shared=True)
    7200
    >>> get_freshness_lifetime(response, is_cache_shared=False)
    3600
    """
    # Parse the Cache-Control header to extract directives
    response_cache_control = parse_cache_control(response.headers.get("Cache-Control"))

    # PRIORITY 1: s-maxage (Shared Cache Only)
    # RFC 9111 Section 5.2.2.10: s-maxage Response Directive
    # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.10
    #
    # "The s-maxage response directive indicates that, for a shared cache,
    # the maximum age specified by this directive overrides the maximum age
    # specified by either the max-age directive or the Expires header field."
    #
    # s-maxage only applies to shared caches (proxies, CDNs)
    # Private caches (browsers) ignore it and fall through to max-age
    if is_cache_shared and response_cache_control.s_maxage is not None:
        return response_cache_control.s_maxage

    # PRIORITY 2: max-age
    # RFC 9111 Section 5.2.2.1: max-age Response Directive
    # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.1
    #
    # "The max-age response directive indicates that the response is to be
    # considered stale after its age is greater than the specified number
    # of seconds."
    #
    # max-age is the most common caching directive
    # It applies to both shared and private caches
    if response_cache_control.max_age is not None:
        return response_cache_control.max_age

    # PRIORITY 3: Expires - Date
    # RFC 9111 Section 5.3: Expires
    # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.3
    #
    # "The Expires header field gives the date/time after which the response
    # is considered stale."
    #
    # This is an older mechanism (HTTP/1.0) but still supported
    # Freshness lifetime = Expires - Date
    if "expires" in response.headers:
        expires_timestamp = parse_date(response.headers["expires"])

        if expires_timestamp is None:
            raise RuntimeError("Cannot parse Expires header")  # pragma: nocover

        # Get the Date header or use current time as fallback
        date_timestamp = parse_date(response.headers["date"]) if "date" in response.headers else time.time()

        if date_timestamp is None:  # pragma: nocover
            # If the Date header is invalid, we use the current time as the date
            # RFC 9110 Section 6.6.1: Date
            # "A recipient with a clock that receives a response with an invalid
            # Date header field value MAY replace that value with the time that
            # response was received."
            date_timestamp = time.time()

        # Calculate freshness lifetime as difference between Expires and Date
        return int(expires_timestamp - (time.time() if date_timestamp is None else date_timestamp))

    # PRIORITY 4: Heuristic Freshness
    # RFC 9111 Section 4.2.2: Calculating Heuristic Freshness
    # https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2.2
    #
    # "Since origin servers do not always provide explicit expiration times,
    # a cache MAY assign a heuristic expiration time when an explicit time
    # is not specified."
    #
    # If no explicit freshness information exists, try to calculate it
    # heuristically based on the Last-Modified header
    heuristic_freshness = get_heuristic_freshness(response)

    if heuristic_freshness is None:
        return None

    return get_heuristic_freshness(response)


def allowed_stale(response: Response, allow_stale_option: bool) -> bool:
    """
    Determines if a stale response is allowed to be served without revalidation.

    Stale responses can sometimes be served to improve performance or availability,
    but only if certain conditions are met and it's explicitly allowed.

    RFC 9111 Section 4.2.4: Serving Stale Responses
    https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2.4

    Parameters:
    ----------
    response : Response
        The stale cached response being considered for use
    allow_stale_option : bool
        Configuration flag indicating if serving stale is allowed

    Returns:
    -------
    bool
        True if the stale response is allowed to be served, False otherwise

    RFC 9111 Compliance:
    -------------------
    From RFC 9111 Section 4.2.4:
    "A cache MUST NOT generate a stale response if it is prohibited by an
    explicit in-protocol directive (e.g., by a no-cache response directive,
    a must-revalidate response directive, or an applicable s-maxage or
    proxy-revalidate response directive; see Section 5.2.2)."

    "A cache MUST NOT generate a stale response unless it is disconnected or
    doing so is explicitly permitted by the client or origin server (e.g., by
    the max-stale request directive in Section 5.2.1, extension directives
    such as those defined in [RFC5861], or configuration in accordance with
    an out-of-band contract)."

    Conditions that prohibit serving stale:
    --------------------------------------
    1. allow_stale_option is False (configuration disallows it)
    2. Response has no-cache directive (must always revalidate)
    3. Response has must-revalidate directive (must revalidate when stale)
    4. Response has proxy-revalidate directive (shared caches must revalidate)
    5. Response has s-maxage directive (shared caches must revalidate)

    Examples:
    --------
    >>> # Stale allowed with permissive configuration
    >>> response = Response(headers=Headers({"cache-control": "max-age=3600"}))
    >>> allowed_stale(response, allow_stale_option=True)
    True

    >>> # Stale not allowed when configuration disables it
    >>> allowed_stale(response, allow_stale_option=False)
    False

    >>> # must-revalidate prevents serving stale
    >>> response = Response(headers=Headers({
    ...     "cache-control": "max-age=3600, must-revalidate"
    ... }))
    >>> allowed_stale(response, allow_stale_option=True)
    False
    """
    # First check: Is serving stale enabled in configuration?
    # If not, we can't serve stale responses regardless of directives
    if not allow_stale_option:
        return False

    # Parse Cache-Control directives to check for prohibitions
    response_cache_control = parse_cache_control(response.headers.get("Cache-Control"))

    # PROHIBITION 1: no-cache directive
    # RFC 9111 Section 5.2.2.4: no-cache Response Directive
    # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.4
    #
    # "The no-cache response directive... indicates that the response MUST NOT
    # be used to satisfy any other request without forwarding it for validation
    # and receiving a successful response."
    #
    # no-cache means the response must ALWAYS be revalidated before use,
    # even if it's fresh. Stale responses definitely cannot be served.
    if response_cache_control.no_cache:
        return False

    # PROHIBITION 2: must-revalidate directive
    # RFC 9111 Section 5.2.2.2: must-revalidate Response Directive
    # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.2
    #
    # "The must-revalidate response directive indicates that once the response
    # has become stale, a cache MUST NOT reuse that response to satisfy another
    # request until it has been successfully validated by the origin."
    #
    # must-revalidate specifically prohibits serving stale responses
    # This is used for responses where serving stale content could cause
    # incorrect operation (e.g., financial transactions)
    if response_cache_control.must_revalidate:
        return False

    # All checks passed - stale response may be served
    return True


def get_heuristic_freshness(response: Response) -> int | None:
    """
    Calculates a heuristic freshness lifetime when no explicit expiration is provided.

    When a response lacks explicit caching directives (max-age, Expires),
    caches may assign a heuristic freshness lifetime based on other response
    characteristics, particularly the Last-Modified header.

    RFC 9111 Section 4.2.2: Calculating Heuristic Freshness
    https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2.2

    Parameters:
    ----------
    response : Response
        The response to calculate heuristic freshness for

    Returns:
    -------
    int | None
        Heuristic freshness lifetime in seconds, or None if it cannot be calculated

    RFC 9111 Compliance:
    -------------------
    From RFC 9111 Section 4.2.2:
    "Since origin servers do not always provide explicit expiration times,
    a cache MAY assign a heuristic expiration time when an explicit time is
    not specified, employing algorithms that use other field values (such as
    the Last-Modified time) to estimate a plausible expiration time. This
    specification does not provide specific algorithms, but it does impose
    worst-case constraints on their results."

    "If the response has a Last-Modified header field, caches are encouraged
    to use a heuristic expiration value that is no more than some fraction of
    the interval since that time. A typical setting of this fraction might
    be 10%."

    Heuristic Calculation:
    ---------------------
    - Freshness = 10% of (now - Last-Modified)
    - Maximum: 1 week (604,800 seconds)
    - Minimum: 0 seconds

    Rationale:
    ---------
    If a resource hasn't changed in a long time (old Last-Modified), it's
    likely stable and can be cached longer. The 10% rule is a conservative
    heuristic that balances caching benefits with freshness.

    Examples:
    --------
    >>> # Resource last modified 10 days ago
    >>> # Heuristic freshness = 10% of 10 days = 1 day
    >>> last_modified = (datetime.now() - timedelta(days=10)).strftime(...)
    >>> response = Response(headers=Headers({"last-modified": last_modified}))
    >>> get_heuristic_freshness(response)
    86400  # 1 day in seconds

    >>> # Resource last modified 100 days ago
    >>> # Would be 10 days, but capped at 1 week maximum
    >>> last_modified = (datetime.now() - timedelta(days=100)).strftime(...)
    >>> response = Response(headers=Headers({"last-modified": last_modified}))
    >>> get_heuristic_freshness(response)
    604800  # 1 week (maximum)

    >>> # No Last-Modified header
    >>> response = Response(headers=Headers({}))
    >>> get_heuristic_freshness(response)
    None
    """
    # Get the Last-Modified header if present
    last_modified = response.headers.get("last-modified")

    if last_modified:
        # Parse the Last-Modified timestamp
        last_modified_timestamp = parse_date(last_modified)

        if last_modified_timestamp is None:  # pragma: nocover
            # Cannot parse the date, cannot calculate heuristic freshness
            return None

        # Calculate how long ago the resource was last modified
        now = time.time()
        age_since_modification = now - last_modified_timestamp

        # RFC 9111 recommends 10% of the age since modification
        # "A typical setting of this fraction might be 10%."
        heuristic_freshness = int(age_since_modification * 0.1)

        # Cap at one week maximum
        # RFC 9111 Section 4.2.2: "Historically, HTTP required the Expires
        # field value to be no more than a year in the future. While longer
        # freshness lifetimes are no longer prohibited, extremely large values
        # have been demonstrated to cause problems."
        #
        # We use a conservative 1-week maximum for heuristic freshness
        ONE_WEEK = 604_800  # 7 days * 24 hours * 60 minutes * 60 seconds

        return min(ONE_WEEK, heuristic_freshness)

    # No Last-Modified header, cannot calculate heuristic freshness
    return None


def get_age(response: Response) -> int:
    """
    Calculates the current age of a cached response in seconds.

    Age represents how old a cached response is - the time since it was
    generated or last validated by the origin server. This is crucial for
    determining if a response is still fresh.

    RFC 9111 Section 4.2.3: Calculating Age
    https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2.3

    Parameters:
    ----------
    response : Response
        The cached response to calculate age for

    Returns:
    -------
    int
        Age of the response in seconds (always >= 0)

    RFC 9111 Compliance:
    -------------------
    From RFC 9111 Section 4.2.3:
    "A response's 'age' is the time that has passed since it was generated by,
    or successfully validated with, the origin server."

    The full RFC formula accounts for:
    - apparent_age: Current time minus Date header
    - age_value: Age header from upstream caches
    - response_delay: Network latency
    - resident_time: Time stored in this cache

    This simplified implementation calculates:
    age = max(0, now - Date)

    Where:
    - now: Current time
    - Date: Value from the Date response header

    Fallbacks:
    ---------
    - If Date header is missing: age = 0
    - If Date header is invalid: age = 0
    - If Date is in the future: age = 0 (via max(0, ...))

    Note on Accuracy:
    ----------------
    This is a simplified calculation suitable for single-hop caches.
    A full implementation would consider:
    - Age header from upstream caches
    - Request/response timing for latency correction
    - Clock skew compensation

    Examples:
    --------
    >>> # Response from 1 hour ago
    >>> date = (datetime.utcnow() - timedelta(hours=1)).strftime(...)
    >>> response = Response(headers=Headers({"date": date}))
    >>> get_age(response)
    3600  # 1 hour in seconds

    >>> # Fresh response (Date = now)
    >>> date = datetime.utcnow().strftime(...)
    >>> response = Response(headers=Headers({"date": date}))
    >>> get_age(response)
    0  # or very close to 0

    >>> # No Date header
    >>> response = Response(headers=Headers({}))
    >>> get_age(response)
    0
    """
    # RFC 9110 Section 6.6.1: Date
    # https://www.rfc-editor.org/rfc/rfc9110#section-6.6.1
    #
    # "A recipient with a clock that receives a response with an invalid Date
    # header field value MAY replace that value with the time that response
    # was received."
    #
    # If no Date header exists, we treat the response as having age 0
    # This is conservative - it assumes the response is brand new
    if "date" not in response.headers:
        return 0

    # Parse the Date header
    date = parse_date(response.headers["date"])

    if date is None:  # pragma: nocover
        # Invalid Date header, treat as age 0
        return 0

    # Calculate apparent age: how long ago was the response generated?
    now = time.time()
    apparent_age = max(0, now - date)

    # Return age as integer seconds
    # max(0, ...) ensures we never return negative age (e.g., if Date is in future)
    return int(apparent_age)


def make_conditional_request(request: Request, response: Response) -> Request:
    """
    Converts a regular request into a conditional request for validation.

    Conditional requests use validators (ETag, Last-Modified) to check if a
    cached response is still valid. If the resource hasn't changed, the server
    responds with 304 Not Modified, saving bandwidth.

    RFC 9111 Section 4.3.1: Sending a Validation Request
    https://www.rfc-editor.org/rfc/rfc9111.html#section-4.3.1

    Parameters:
    ----------
    request : Request
        The original request to make conditional
    response : Response
        The cached response containing validators (ETag, Last-Modified)

    Returns:
    -------
    Request
        A new request with conditional headers added (If-None-Match, If-Modified-Since)

    RFC 9111 Compliance:
    -------------------
    From RFC 9111 Section 4.3.1:
    "When generating a conditional request for validation, a cache... updates
    that request with one or more precondition header fields. These contain
    validator metadata sourced from a stored response(s) that has the same URI."

    "When generating a conditional request for validation, a cache:
     - MUST send the relevant entity tags (using If-Match, If-None-Match, or
       If-Range) if the entity tags were provided in the stored response(s)
       being validated.
     - SHOULD send the Last-Modified value (using If-Modified-Since) if the
       request is not for a subrange, a single stored response is being
       validated, and that response contains a Last-Modified value."

    Conditional Headers Added:
    -------------------------
    1. If-None-Match: Added if response has ETag
       - Asks server: "Send full response only if ETag doesn't match"
       - 304 response if ETag matches (resource unchanged)
       - 200 response with content if ETag differs (resource changed)

    2. If-Modified-Since: Added if response has Last-Modified
       - Asks server: "Send full response only if modified after this date"
       - 304 response if not modified (resource unchanged)
       - 200 response with content if modified (resource changed)

    Validator Priority:
    ------------------
    Both validators are sent if available. ETags are more reliable than
    Last-Modified (1-second granularity), so servers typically check ETag first.

    Examples:
    --------
    >>> # Request with ETag validator
    >>> request = Request(method="GET", url="https://example.com/resource")
    >>> response = Response(headers=Headers({"etag": '"abc123"'}))
    >>> conditional = make_conditional_request(request, response)
    >>> conditional.headers["if-none-match"]
    '"abc123"'

    >>> # Request with Last-Modified validator
    >>> response = Response(headers=Headers({
    ...     "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT"
    ... }))
    >>> conditional = make_conditional_request(request, response)
    >>> conditional.headers["if-modified-since"]
    'Mon, 01 Jan 2024 00:00:00 GMT'

    >>> # Request with both validators
    >>> response = Response(headers=Headers({
    ...     "etag": '"abc123"',
    ...     "last-modified": "Mon, 01 Jan 2024 00:00:00 GMT"
    ... }))
    >>> conditional = make_conditional_request(request, response)
    >>> "if-none-match" in conditional.headers
    True
    >>> "if-modified-since" in conditional.headers
    True
    """
    # Extract validators from the cached response

    # VALIDATOR 1: Last-Modified
    # RFC 9110 Section 8.8.2: Last-Modified
    # https://www.rfc-editor.org/rfc/rfc9110#section-8.8.2
    #
    # Last-Modified indicates when the resource was last changed
    # Used to create If-Modified-Since conditional header
    if "last-modified" in response.headers:
        last_modified = response.headers["last-modified"]
    else:
        last_modified = None

    # VALIDATOR 2: ETag (Entity Tag)
    # RFC 9110 Section 8.8.3: ETag
    # https://www.rfc-editor.org/rfc/rfc9110#section-8.8.3
    #
    # ETag is an opaque validator that represents a specific version of a resource
    # More reliable than Last-Modified (no timestamp granularity issues)
    # Used to create If-None-Match conditional header
    if "etag" in response.headers:
        etag = response.headers["etag"]
    else:
        etag = None

    # Build precondition headers dictionary
    precondition_headers: Dict[str, str] = {}

    # ADD PRECONDITION 1: If-None-Match (from ETag)
    # RFC 9110 Section 13.1.2: If-None-Match
    # https://www.rfc-editor.org/rfc/rfc9110#section-13.1.2
    #
    # "MUST send the relevant entity tags (using If-Match, If-None-Match, or
    # If-Range) if the entity tags were provided in the stored response(s)
    # being validated."
    #
    # If-None-Match tells the server: "Only send the full response if the
    # current ETag is different from this one"
    #
    # Server responses:
    # - 304 Not Modified: ETag matches, cached version is still valid
    # - 200 OK: ETag differs, sends new content
    if etag is not None:
        precondition_headers["If-None-Match"] = etag

    # ADD PRECONDITION 2: If-Modified-Since (from Last-Modified)
    # RFC 9110 Section 13.1.3: If-Modified-Since
    # https://www.rfc-editor.org/rfc/rfc9110#section-13.1.3
    #
    # "SHOULD send the Last-Modified value (using If-Modified-Since) if the
    # request is not for a subrange, a single stored response is being
    # validated, and that response contains a Last-Modified value."
    #
    # If-Modified-Since tells the server: "Only send the full response if the
    # resource has been modified after this date"
    #
    # Server responses:
    # - 304 Not Modified: Not modified since date, cached version is valid
    # - 200 OK: Modified since date, sends new content
    if last_modified:
        precondition_headers["If-Modified-Since"] = last_modified

    # Create a new request with the original headers plus precondition headers
    # The replace() function creates a copy of the request with updated headers
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
    Removes headers that must not be stored in the cache.

    Certain headers are connection-specific or contain sensitive information
    that should not be cached. This function filters them out before storage.

    RFC 9111 Section 3.1: Storing Header and Trailer Fields
    https://www.rfc-editor.org/rfc/rfc9111.html#section-3.1

    Parameters:
    ----------
    response : Response
        The response to filter headers from
    is_cache_shared : bool
        True if this is a shared cache (affects private directive handling)

    Returns:
    -------
    Response
        A new response with unstorable headers removed

    RFC 9111 Compliance:
    -------------------
    From RFC 9111 Section 3.1:
    "Caches MUST include all received response header fields -- including
    unrecognized ones -- when storing a response; this assures that new HTTP
    header fields can be successfully deployed. However, the following exceptions
    are made:
     - The Connection header field and fields whose names are listed in it are
       not stored (see Section 7.6.1 of [HTTP])
     - Caches MUST NOT store fields defined as being specific to a particular
       connection or applicable only to a tunnel or gateway, unless the cache
       was specifically designed to support these fields"

    Headers Always Excluded:
    -----------------------
    Connection-specific headers (RFC 9110 Section 7.6.1):
    - Connection
    - Keep-Alive
    - Proxy-Connection (non-standard but common)
    - Transfer-Encoding
    - Upgrade
    - TE

    Hop-by-hop authentication headers:
    - Proxy-Authenticate
    - Proxy-Authorization
    - Proxy-Authentication-Info

    Headers Conditionally Excluded:
    -------------------------------
    - Fields listed in no-cache directive (always excluded)
    - Fields listed in private directive (excluded for shared caches only)

    Examples:
    --------
    >>> # Remove connection-specific headers
    >>> response = Response(headers=Headers({
    ...     "cache-control": "max-age=3600",
    ...     "connection": "keep-alive",
    ...     "keep-alive": "timeout=5",
    ...     "content-type": "application/json"
    ... }))
    >>> filtered = exclude_unstorable_headers(response, is_cache_shared=True)
    >>> "connection" in filtered.headers
    False
    >>> "content-type" in filtered.headers
    True

    >>> # Remove headers listed in no-cache
    >>> response = Response(headers=Headers({
    ...     "cache-control": 'no-cache="Set-Cookie"',
    ...     "set-cookie": "session=abc123"
    ... }))
    >>> filtered = exclude_unstorable_headers(response, is_cache_shared=True)
    >>> "set-cookie" in filtered.headers
    False
    """
    # Initialize set of headers to exclude
    # These are connection-specific headers that must never be cached
    # RFC 9110 Section 7.6.1: Connection-Specific Header Fields
    # https://www.rfc-editor.org/rfc/rfc9110#section-7.6.1
    need_to_be_excluded = set(
        [
            "connection",  # Connection management
            "keep-alive",  # Connection timeout and max requests
            "te",  # Transfer encoding accepted by client
            "transfer-encoding",  # How the body is encoded for transfer
            "upgrade",  # Protocol upgrade (e.g., WebSocket)
            "proxy-connection",  # Non-standard but widely used
            "proxy-authenticate",  # Proxy authentication challenge
            "proxy-authentication-info",  # Proxy auth additional info
            "proxy-authorization",  # Proxy auth credentials
        ]
    )

    # Parse Cache-Control to check for no-cache and private directives
    cache_control = parse_cache_control(response.headers.get("cache-control"))

    # EXCLUSION RULE 1: no-cache with field names
    # RFC 9111 Section 5.2.2.4: no-cache Response Directive
    # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.4
    #
    # "The qualified form of the no-cache response directive, with an argument
    # that lists one or more field names, indicates that a cache MAY use the
    # response to satisfy a subsequent request, subject to any other restrictions
    # on caching, if the listed header fields are excluded from the subsequent
    # response or the subsequent response has been successfully revalidated with
    # the origin server."
    #
    # Example: Cache-Control: no-cache="Set-Cookie, Set-Cookie2"
    # Means: Cache the response but exclude Set-Cookie headers from the cache
    if isinstance(cache_control.no_cache, list):
        for field in cache_control.no_cache:
            need_to_be_excluded.add(field.lower())

    # EXCLUSION RULE 2: private with field names (shared caches only)
    # RFC 9111 Section 5.2.2.7: private Response Directive
    # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.2.7
    #
    # "If a qualified private response directive is present, with an argument
    # that lists one or more field names, then only the listed header fields
    # are limited to a single user: a shared cache MUST NOT store the listed
    # header fields if they are present in the original response but MAY store
    # the remainder of the response message without those header fields"
    #
    # Example: Cache-Control: private="Authorization"
    # Means: Shared caches can cache the response but must exclude Authorization
    if is_cache_shared and isinstance(cache_control.private, list):
        for field in cache_control.private:
            need_to_be_excluded.add(field.lower())

    # Filter out the excluded headers
    # Create new Headers dict with only the headers we want to keep
    new_headers = Headers(
        {key: value for key, value in response.headers.items() if key.lower() not in need_to_be_excluded}
    )

    # Return a new response with filtered headers
    return replace(
        response,
        headers=new_headers,
    )


def refresh_response_headers(
    stored_response: Response,
    revalidation_response: Response,
    is_cache_shared: bool,
) -> Response:
    """
    Updates a stored response's headers with fresh metadata from a 304 response.

    When revalidation succeeds (304 Not Modified), the cached response is still
    valid but its metadata (Date, Cache-Control, etc.) should be updated with
    fresh values from the 304 response.

    RFC 9111 Section 3.2: Updating Stored Header Fields
    https://www.rfc-editor.org/rfc/rfc9111.html#section-3.2

    Parameters:
    ----------
    stored_response : Response
        The cached response that is being freshened
    revalidation_response : Response
        The 304 Not Modified response containing fresh metadata

    Returns:
    -------
    Response
        The stored response with updated headers

    RFC 9111 Compliance:
    -------------------
    From RFC 9111 Section 3.2:
    "When doing so, the cache MUST add each header field in the provided response
    to the stored response, replacing field values that are already present,
    with the following exceptions:
     - Header fields that provide metadata about the message content and/or the
       selected representation (e.g., Content-Encoding, Content-Type, Content-Range)
       MUST NOT be updated unless the response is being stored as a result of
       successful validation."

    Update Rules:
    ------------
    1. Merge headers from 304 response into stored response
    2. 304 headers override stored headers (newer metadata)
    3. EXCEPT: Content metadata headers are NOT updated
       - Content-Encoding
       - Content-Type
       - Content-Range
    4. Remove unstorable headers after merging

    Rationale for Exceptions:
    ------------------------
    Content-* headers describe the body of the response. A 304 response has
    no body, so its Content-* headers (if any) don't describe the cached body.
    We must preserve the original Content-* headers from the cached response.

    For example:
    - Cached response: Content-Type: application/json, body is JSON
    - 304 response: Content-Type: text/plain (this is wrong for the cached body!)
    - Result: Keep application/json from cached response

    Examples:
    --------
    >>> # Update Date and Cache-Control, preserve Content-Type
    >>> stored = Response(
    ...     status_code=200,
    ...     headers=Headers({
    ...         "date": "Mon, 01 Jan 2024 00:00:00 GMT",
    ...         "cache-control": "max-age=3600",
    ...         "content-type": "application/json"
    ...     })
    ... )
    >>> revalidation = Response(
    ...     status_code=304,
    ...     headers=Headers({
    ...         "date": "Mon, 01 Jan 2024 12:00:00 GMT",
    ...         "cache-control": "max-age=7200",
    ...         "content-type": "text/plain"  # Should be ignored
    ...     })
    ... )
    >>> refreshed = refresh_response_headers(stored, revalidation)
    >>> refreshed.headers["cache-control"]
    'max-age=7200'  # Updated
    >>> refreshed.headers["content-type"]
    'application/json'  # Preserved from stored response
    """
    # Define headers that must NOT be updated from the 304 response
    # These headers describe the message body/representation
    # RFC 9111 Section 3.2: "Header fields that provide metadata about the
    # message content and/or the selected representation... MUST NOT be updated"
    excluded_headers = set(
        [
            "content-encoding",  # How the body is encoded (gzip, br, etc.)
            "content-type",  # MIME type of the body
            "content-range",  # For partial content (206 responses)
        ]
    )

    # Merge headers: Start with stored response, overlay revalidation response
    # Headers from revalidation_response override stored_response
    # EXCEPT for excluded headers (content metadata)
    new_headers = {
        **stored_response.headers,  # Base: original cached headers
        **{
            key: value
            for key, value in revalidation_response.headers.items()
            if key.lower() not in excluded_headers  # Skip content metadata
        },
    }

    # Remove unstorable headers from the final merged headers
    # This ensures we don't accidentally cache connection-specific headers
    # that might have been in the 304 response
    return exclude_unstorable_headers(
        replace(
            stored_response,
            headers=Headers(new_headers),
        ),
        is_cache_shared,
    )


AnyState = Union[
    "CacheMiss",
    "StoreAndUse",
    "CouldNotBeStored",
    "FromCache",
    "NeedToBeUpdated",
    "NeedRevalidation",
    "IdleClient",
    "InvalidateEntries",
]

# Defined in https://www.rfc-editor.org/rfc/rfc9110#name-safe-methods
SAFE_METHODS = frozenset(["GET", "HEAD", "OPTIONS", "TRACE"])


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
        self, request: Request, associated_entries: list[Entry]
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
        associated_entries : list[Entry]
            List of request-response entries previously stored in the cache that may match
            this request. These entries are pre-filtered by cache key (typically URI).

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
        - Request no-cache directive forces revalidation of cached responses

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

        >>> # Need revalidation - request no-cache forces validation of fresh response
        >>> idle = IdleClient(options=default_options)
        >>> no_cache_request = Request(
        ...     method="GET",
        ...     url="https://example.com",
        ...     headers=Headers({"cache-control": "no-cache"})
        ... )
        >>> cached_pair = CompletePair(no_cache_request, fresh_response)
        >>> next_state = idle.next(no_cache_request, [cached_pair])
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
        def no_cache_missing(pair: Entry) -> bool:
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
        def fresh_or_allowed_stale(pair: Entry) -> bool:
            """
            Determine if a cached response is fresh or allowed to be served stale.

            RFC 9111 Section 4.2:
            "A 'fresh' response is one whose age has not yet exceeded its freshness
            lifetime. Conversely, a 'stale' response is one where it has."

            RFC 9111 Section 4.2.4: Serving Stale Responses
            "A cache MUST NOT generate a stale response unless it is disconnected or
            doing so is explicitly permitted by the client or origin server."
            """
            freshness_lifetime = get_freshness_lifetime(pair.response, self.options.shared)
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
            for pair in associated_entries
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
        # STEP 7: Handle Request no-cache Directive
        # ============================================================================
        # RFC 9111 Section 5.2.1.4: no-cache Request Directive
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-5.2.1.4
        #
        # "The no-cache request directive indicates that a cache MUST NOT use a
        # stored response to satisfy the request without successful validation on
        # the origin server."
        #
        # When a client sends Cache-Control: no-cache in the request, it's explicitly
        # requesting that the cache not use any stored response without first validating
        # it with the origin server. This is different from the response no-cache directive,
        # which applies to how responses should be cached.
        request_cache_control = parse_cache_control(request.headers.get("cache-control"))

        if request_cache_control.no_cache is True:
            # Move all fresh responses to the revalidation queue
            # This ensures that even fresh cached responses will be validated
            # with the origin server via conditional requests (If-None-Match,
            # If-Modified-Since) before being served to the client.
            need_revalidation.extend(ready_to_use)
            ready_to_use = []

        # ============================================================================
        # STEP 8: Determine Next State Based on Available Responses
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

            # Use the most recent response (first in sorted list)
            selected_pair = ready_to_use[0]

            # Calculate current age and update the Age header
            current_age = get_age(selected_pair.response)
            return FromCache(
                entry=replace(
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
                revalidating_entries=need_revalidation,
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

    def next(self, response: Response) -> Union["StoreAndUse", "CouldNotBeStored"]:
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

        Examples:
        --------
        >>> # Cacheable response
        >>> cache_miss = CacheMiss(request=get_request, options=default_options)
        >>> response = Response(
        ...     status_code=200,
        ...     headers=Headers({"cache-control": "max-age=3600"})
        ... )
        >>> next_state = cache_miss.next(response)
        >>> isinstance(next_state, StoreAndUse)
        True

        >>> # Non-cacheable response (no-store)
        >>> response = Response(
        ...     status_code=200,
        ...     headers=Headers({"cache-control": "no-store"})
        ... )
        >>> next_state = cache_miss.next(response)
        >>> isinstance(next_state, CouldNotBeStored)
        True
        """

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
        has_explicit_directive = (
            response_cache_control.public
            or response_cache_control.s_maxage is not None
            or response_cache_control.must_revalidate
        )
        can_cache_auth_request = (
            not self.options.shared or "authorization" not in request.headers or has_explicit_directive
        )

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
            or not can_cache_auth_request
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
                elif not can_cache_auth_request:
                    logger.debug(
                        "Cannot store the response because the request contained an Authorization header "
                        "and there was no explicit directive allowing shared caching. "
                        "See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-5"
                    )
                elif not contains_required_component:
                    logger.debug(
                        "Cannot store the response because it does not contain any of the required components. "
                        "See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.7.1"
                    )

            return CouldNotBeStored(
                response=response,
                options=self.options,
                after_revalidation=self.after_revalidation,
            )

        # --------------------------------------------------------------------
        # Transition to: StoreAndUse
        # --------------------------------------------------------------------
        # All storage requirements are met. The response will be cached.

        logger.debug("Storing response in cache")

        # Remove headers that should not be stored
        # RFC 9111 Section 3.1: Storing Header and Trailer Fields
        # https://www.rfc-editor.org/rfc/rfc9111.html#section-3.1
        # Certain headers (Connection, hop-by-hop headers, etc.) must be excluded
        cleaned_response = exclude_unstorable_headers(response, self.options.shared)

        return StoreAndUse(
            response=cleaned_response,
            options=self.options,
            after_revalidation=self.after_revalidation,
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
    - InvalidateEntries + CacheMiss: 2xx/5xx response received, new response must be cached
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
    revalidating_entries : list[Entry]
        The cached request-response entries that are being revalidated. These are
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

    revalidating_entries: list[Entry]
    """
    The stored entries that the request was sent for revalidation.
    """

    def next(
        self, revalidation_response: Response
    ) -> Union["NeedToBeUpdated", "InvalidateEntries", "CacheMiss", "FromCache", "StoreAndUse", "CouldNotBeStored"]:
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
        Union[NeedToBeUpdated, InvalidateEntries, CacheMiss]
            - NeedToBeUpdated: When 304 response allows cached responses to be freshened
            - InvalidateEntries: When old responses must be invalidated (wraps next state)
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
        ...     revalidating_entries=[cached_entry],
        ...     options=default_options
        ... )
        >>> response_304 = Response(status_code=304, headers=Headers({"etag": '"abc123"'}))
        >>> next_state = need_revalidation.next(response_304)
        >>> isinstance(next_state, NeedToBeUpdated)
        True

        >>> # 200 OK - use new response
        >>> response_200 = Response(status_code=200, headers=Headers({"cache-control": "max-age=3600"}))
        >>> next_state = need_revalidation.next(response_200)
        >>> isinstance(next_state, InvalidateEntries)
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
            # Invalidate all old entries except the last one
            # The last entry's ID will be reused for the new response
            return InvalidateEntries(
                options=self.options,
                entry_ids=[entry.id for entry in self.revalidating_entries[:-1]],
                # After invalidation, attempt to cache the new response
                next_state=CacheMiss(
                    request=self.original_request,
                    options=self.options,
                    after_revalidation=True,  # Mark that this occurred during revalidation
                ).next(
                    revalidation_response,
                ),
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
            return InvalidateEntries(
                options=self.options,
                entry_ids=[entry.id for entry in self.revalidating_entries[:-1]],
                next_state=CacheMiss(
                    request=self.original_request,
                    options=self.options,
                    after_revalidation=True,
                ).next(
                    revalidation_response,
                ),
            )
        else:
            # ============================================================================
            # STEP 4: Handle Unexpected Status Codes
            # ============================================================================
            # RFC 9111 does not define behavior for other status codes in this context.
            # In practice, we need to forward any unexpected responses to the client.
            return CacheMiss(
                request=self.revalidating_entries[-1].request,
                options=self.options,
                after_revalidation=True,
            ).next(revalidation_response)

    def freshening_stored_responses(
        self, revalidation_response: Response
    ) -> "NeedToBeUpdated" | "InvalidateEntries" | "CacheMiss":
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
        Union[NeedToBeUpdated, InvalidateEntries, CacheMiss]
            - NeedToBeUpdated: When matching responses are found and updated
            - InvalidateEntries: Wraps NeedToBeUpdated if non-matching responses exist
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

        identified_for_revalidation: list[Entry]

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
                self.revalidating_entries,
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
                self.revalidating_entries,
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
            if len(self.revalidating_entries) == 1:
                # Only one cached response - it must be the matching one
                identified_for_revalidation, need_to_be_invalidated = (
                    [self.revalidating_entries[0]],
                    [],
                )
            else:
                # Multiple cached responses but no validators to match them
                # We cannot determine which (if any) are valid
                # Conservative approach: invalidate all of them
                identified_for_revalidation, need_to_be_invalidated = (
                    [],
                    self.revalidating_entries,
                )

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
                updating_entries=[
                    replace(
                        pair,
                        response=refresh_response_headers(pair.response, revalidation_response, self.options.shared),
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
            return InvalidateEntries(
                options=self.options,
                entry_ids=[entry.id for entry in need_to_be_invalidated],
                next_state=next_state,
            )

        # No invalidations needed, return the next state directly
        return next_state


class StoreAndUse(State):
    """
    The state that indicates that the response can be stored in the cache and used.

    Attributes:
    ----------
    response : Response
        The HTTP response to be stored in the cache.
    after_revalidation : bool
        Indicates if the storage is occurring after a revalidation process.
    """

    def __init__(
        self,
        response: Response,
        options: CacheOptions,
        after_revalidation: bool = False,
    ) -> None:
        super().__init__(options)
        self.response = response
        self.after_revalidation = after_revalidation
        response_meta = ResponseMetadata(
            hishel_created_at=time.time(),
            hishel_from_cache=False,
            hishel_revalidated=after_revalidation,
            hishel_stored=True,
        )
        self.response.metadata.update(response_meta)  # type: ignore

    def next(self) -> None:
        return None


# @dataclass
# class CouldNotBeStored(State):
#     """
#     The state that indicates that the response could not be stored in the cache.
#     """

#     response: Response

#     pair_id: uuid.UUID

#     def next(self) -> None:
#         return None  # pragma: nocover


class CouldNotBeStored(State):
    """
    The state that indicates that the response could not be stored in the cache.

    Attributes:
    ----------
    response : Response
        The HTTP response that could not be stored.
    pair_id : uuid.UUID
        The unique identifier for the cache pair.
    after_revalidation : bool
        Indicates if the storage attempt occurred after a revalidation process.
    """

    def __init__(
        self,
        response: Response,
        options: CacheOptions,
        after_revalidation: bool = False,
    ) -> None:
        super().__init__(options)
        self.response = response
        response_meta = ResponseMetadata(
            hishel_created_at=time.time(),
            hishel_from_cache=False,
            hishel_revalidated=after_revalidation,
            hishel_stored=False,
        )
        self.response.metadata.update(response_meta)  # type: ignore

    def next(self) -> None:
        return None


@dataclass
class InvalidateEntries(State):
    """
    The state that represents the deletion of cache entries.
    """

    entry_ids: list[uuid.UUID]

    next_state: AnyState

    def next(self) -> AnyState:
        return self.next_state


class FromCache(State):
    def __init__(
        self,
        entry: Entry,
        options: CacheOptions,
        after_revalidation: bool = False,
    ) -> None:
        super().__init__(options)
        self.entry = entry
        self.after_revalidation = after_revalidation
        response_meta = ResponseMetadata(
            hishel_created_at=entry.meta.created_at,
            hishel_from_cache=True,
            hishel_revalidated=after_revalidation,
            hishel_stored=False,
        )
        self.entry.response.metadata.update(response_meta)  # type: ignore

    def next(self) -> None:
        return None


@dataclass
class NeedToBeUpdated(State):
    updating_entries: list[Entry]
    original_request: Request

    def next(self) -> FromCache:
        return FromCache(entry=self.updating_entries[-1], options=self.options, after_revalidation=True)
