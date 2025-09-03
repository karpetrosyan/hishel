from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Dict,
    Iterator,
    Literal,
    Optional,
    TypeVar,
    Union,
)

from hishel._core._headers import Headers, Range, Vary, parse_cache_control
from hishel._core.models import IncompletePair
from hishel._utils import parse_date, partition

if TYPE_CHECKING:
    from hishel import CompletePair, Request, Response


TState = TypeVar("TState", bound="State")
HEURISTICALLY_CACHEABLE_STATUS_CODES = (
    200,
    203,
    204,
    206,
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


class UnknownStream:
    def __iter__(self) -> Iterator[bytes]:
        return self

    def __next__(self) -> bytes:
        raise RuntimeError("Stream is not known yet")

    def __aiter__(self) -> AsyncIterator[bytes]:
        return self

    async def __anext__(self) -> bytes:
        raise RuntimeError("Stream is not known yet")


@dataclass
class TakeRangeInfo:
    response: Response
    """
    The response that was used to take the ranged content from.
    """

    lower_skip: int
    """
    The number of bytes to skip from the start of the response stream.
    """

    take: int
    """
    The number of bytes to take from the response stream.
    """


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


def is_partial(pair: CompletePair) -> bool:
    return pair.response.status_code == 206 or pair.complete_stream is False


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
    The class that represents the idle state of the client, which wants to send a
    request—possibly caching it and retrieving the response from the cache.

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-constructing-responses-from
    """

    def next(
        self, incomplete_pair: IncompletePair, associated_pairs: list[CompletePair]
    ) -> Union["CacheMiss" | "FromCache" | "NeedRevalidation"]:
        request = incomplete_pair.request
        request_range = Range.try_from_str(request.headers["range"]) if "range" in request.headers else None

        if request_range is not None:
            return CacheMiss(options=self.options, pair_id=incomplete_pair.id, request=request)

        # A cache MUST write through requests with methods that are unsafe (Section 9.2.1 of [HTTP])
        # to the origin server; i.e., a cache is not allowed to generate a reply to such a request
        # before having forwarded the request and having received a corresponding response.
        if request.method.upper() not in SAFE_METHODS:
            return CacheMiss(
                pair_id=incomplete_pair.id, request=incomplete_pair.request, options=self.options
            )  # pragma: nocover

        # When presented with a request, a cache MUST NOT reuse a stored response unless:

        # 1. the presented target URI (Section 7.1 of [HTTP])
        # and that of the stored response match, and
        url_matches = lambda pair: pair.request.url == request.url  # noqa: E731

        # 2. the request method associated with the stored response
        # allows it to be used for the presented request, and
        method_matches = lambda pair: pair.request.method == request.method  # noqa: E731

        # 3. request header fields nominated by the stored response
        # (if any) match those presented (see Section 4.1), and
        vary_headers_same = lambda pair: vary_headers_match(request, pair)  # noqa: E731

        # 4. the stored response does not contain the no-cache directive
        # (Section 5.2.2.4), unless it is successfully validated (Section 4.3), and
        def no_cache_missing(pair: CompletePair) -> bool:
            return parse_cache_control(pair.response.headers.get("cache-control")).no_cache is False

        # 5. the stored response is one of the following:
        #   1. fresh (see Section 4.2), or
        #   2. allowed to be served stale (see Section 4.2.4), or
        #   3. successfully validated (see Section 4.3). (Handled in `NeedRevalidation` state)
        def fresh_or_allowed_stale(pair: CompletePair) -> bool:
            freshness_lifetime = get_freshness_lifetime(pair.response, is_cache_shared=True)
            age = get_age(pair.response)
            is_fresh = False if freshness_lifetime is None else age < freshness_lifetime
            return is_fresh or allowed_stale(pair.response, allow_stale_option=self.options.allow_stale)

        # Filtering by 1-4 conditions, skip 5
        filtered_pairs = [
            pair
            for pair in associated_pairs
            if url_matches(pair) and method_matches(pair) and vary_headers_same(pair) and no_cache_missing(pair)  # type: ignore[no-untyped-call]
        ]

        # When more than one suitable response is stored, a cache MUST use the most recent one
        # (as determined by the Date header field). It can also forward the request with
        # "Cache-Control: max-age=0" or "Cache-Control: no-cache" to disambiguate which response to use.
        filtered_pairs.sort(
            key=lambda pair: parse_date(
                pair.response.headers.get("date", str(int(time.time()))),
            )
            or int(time.time()),
            reverse=True,
        )

        ready_to_use, need_revalidation = partition(filtered_pairs, fresh_or_allowed_stale)

        if ready_to_use:
            # When a stored response is used to satisfy a request without validation,
            # a cache MUST generate an Age header field (Section 5.1), replacing any present
            # in the response with a value equal to the stored response's current_age; see Section 4.2.3.
            return FromCache(
                pair=replace(
                    ready_to_use[0],
                    response=replace(
                        ready_to_use[0].response,
                        headers=Headers(
                            {
                                **ready_to_use[0].response.headers,
                                "age": str(get_age(ready_to_use[0].response)),
                            }
                        ),
                    ),
                ),
                options=self.options,
            )

        elif need_revalidation:
            return NeedRevalidation(
                pair_id=incomplete_pair.id,
                request=make_conditional_request(incomplete_pair.request, need_revalidation[-1].response),
                revalidating_pairs=need_revalidation,
                options=self.options,
            )
        else:
            return CacheMiss(
                pair_id=incomplete_pair.id,
                request=incomplete_pair.request,
                options=self.options,
            )


@dataclass
class StoreAndUse(State):
    """
    The state that indicates that the response can be stored in the cache and used.
    """

    pair: CompletePair
    """
    The pair that according to 3 (Storing Responses in Caches) of RFC 9111 can be stored in the cache.
    """

    def next(self) -> None:
        return None  # pragma: nocover


@dataclass
class CouldNotBeStored(State):
    """
    The state that indicates that the response could not be stored in the cache.
    """

    pair: CompletePair
    """
    The pair that could not be stored in the cache.
    """

    def next(self) -> None:
        return None  # pragma: nocover


@dataclass
class CacheMiss(State):
    """
    Storing Responses in Caches

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-storing-responses-in-caches
    """

    pair_id: uuid.UUID
    """
    The id of the pair that missed the cache.
    """

    request: Request
    """
    The request that missed the cache.

    Note that this has a type of Requet and not IncompletePair because
    when moving to this state from `NeedRevalidation` we don't have incomplete pair
    """

    def next(self, pair: CompletePair) -> Union["StoreAndUse", "CouldNotBeStored"]:
        request = pair.request
        response = pair.response
        response_cache_control = parse_cache_control(
            response.headers.get(
                "cache-control",
            )
        )
        # the request method is understood by the cache;
        method_understood_by_cache = request.method.upper() in self.options.supported_methods

        # the response status code is final (see Section 15 of [HTTP]);
        response_status_code_is_final = response.status_code % 100 != 1

        # if the response status code is 206 or 304, or the must-understand cache directive
        # (see Section 5.2.2.3) is present: the cache understands the response status code;
        if pair.response.status_code in (206, 304):
            understands_how_to_cache = False
        else:
            understands_how_to_cache = True

        # the no-store cache directive is not present in the response (see Section 5.2.2.5);
        no_store_is_not_present = not response_cache_control.no_store

        # if the cache is shared: the private response directive is either not present
        # or allows a shared cache to store a modified response;
        private_directive_allows_storing = self.options.shared and response_cache_control.private is not True

        # if the cache is shared: the Authorization header field is not present in the request
        # (see Section 11.6.2 of [HTTP]) or a response directive is present that explicitly
        # allows shared caching (see Section 3.5);
        is_shared_and_authorized = self.options.shared and "authorization" not in request.headers

        # the response contains at least one of the following:
        contains_required_component = (
            # a public response directive (see Section 5.2.2.9);
            response_cache_control.public
            # a private response directive, if the cache is not shared (see Section 5.2.2.7);
            or (not self.options.shared and response_cache_control.private)
            # an Expires header field (see Section 5.3);
            or ("expires" in response.headers)
            # a max-age response directive (see Section 5.2.2.1);
            or (response_cache_control.max_age is not None)
            # if the cache is shared: an s-maxage response directive (see Section 5.2.2.10);
            or (self.options.shared and response_cache_control.s_maxage is not None)
            # a status code that is defined as heuristically cacheable (see Section 4.2.2).
            or response.status_code in HEURISTICALLY_CACHEABLE_STATUS_CODES
        )

        if (
            not method_understood_by_cache
            or not response_status_code_is_final
            or not understands_how_to_cache
            or not no_store_is_not_present
            or not private_directive_allows_storing
            or not is_shared_and_authorized
            or not contains_required_component
        ):
            if logger.isEnabledFor(logging.DEBUG):
                if not method_understood_by_cache:
                    logger.debug(
                        "Cannot store the response because the request method is not understood by the cache."
                        "See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.1.1"
                    )
                elif not response_status_code_is_final:
                    logger.debug(
                        f"Cannot store the response because the response status code ({response.status_code}) "
                        "is not final. See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.2.1"
                    )
                elif not understands_how_to_cache:
                    logger.debug(
                        "Cannot store the response because the cache does not understand how to cache the response."
                        "See: https://www.rfc-editor.org/rfc/rfc9111.html#section-3-2.3.2"
                    )
                elif not no_store_is_not_present:
                    logger.debug(
                        "Cannot store the response because the no-store cache directive is present in the response."
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

            return CouldNotBeStored(pair=pair, options=self.options)

        return StoreAndUse(
            pair=replace(
                pair,
                response=exclude_unstorable_headers(response, self.options.shared),
            ),
            options=self.options,
        )


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

    def next(self) -> FromCache:
        return FromCache(pair=self.updating_pairs[-1], options=self.options)  # pragma: nocover


@dataclass
class NeedRevalidation(State):
    """
    4.3.3 Handling a validation response.

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-handling-a-validation-respo
    """

    pair_id: uuid.UUID

    request: Request
    """
    The request that was sent to the server for revalidation.
    """

    revalidating_pairs: list[CompletePair]
    """
    The stored pairs that the request was sent for revalidation.
    """

    def next(self, revalidation_pair: CompletePair) -> Union["NeedToBeUpdated", "CacheMiss"]:
        revalidation_response = revalidation_pair.response

        # Cache handling of a response to a conditional request depends upon its status code:
        if revalidation_response.status_code == 304:
            # A 304 (Not Modified) response status code indicates that the stored
            # response can be updated and reused; see Section 4.3.4.
            return self.freshening_stored_responses(revalidation_response)
        elif revalidation_response.status_code // 100 == 2:
            # A full response (i.e., one containing content) indicates that none of the stored
            # responses nominated in the conditional request are suitable. Instead, the cache
            # MUST use the full response to satisfy the request. The cache MAY store such a full
            # response, subject to its constraints (see Section 3).
            return CacheMiss(pair_id=revalidation_pair.id, request=revalidation_pair.request, options=self.options)
        elif revalidation_response.status_code // 100 == 5:
            # However, if a cache receives a 5xx (Server Error) response while attempting to
            # validate a response, it can either forward this response to the requesting client
            # or act as if the server failed to respond. In the latter case, the cache can send
            # a previously stored response, subject to its constraints on doing so
            # (see Section 4.2.4),or retry the validation request.
            return CacheMiss(pair_id=revalidation_pair.id, request=revalidation_pair.request, options=self.options)
        raise RuntimeError(
            f"Unexpected response status code during revalidation: {revalidation_response.status_code}"
        )  # pragma: nocover

    def freshening_stored_responses(self, revalidation_response: Response) -> NeedToBeUpdated:
        """
        4.3.4 Freshening stored responses upon validation

        RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-freshening-stored-responses
        """

        identified_for_revalidation: list[CompletePair] = []
        if "etag" in revalidation_response.headers and (not revalidation_response.headers["etag"].startswith("W/")):
            for pair in self.revalidating_pairs:  # pragma: nocover
                if pair.response.headers.get("etag") == revalidation_response.headers.get("etag"):
                    identified_for_revalidation.append(pair)
        elif revalidation_response.headers.get("last-modified"):
            for pair in self.revalidating_pairs:  # pragma: nocover
                if pair.response.headers.get("last-modified") == revalidation_response.headers.get("last-modified"):
                    identified_for_revalidation.append(pair)
        else:
            if len(self.revalidating_pairs) == 1:
                identified_for_revalidation.append(self.revalidating_pairs[0])
        return NeedToBeUpdated(
            updating_pairs=[
                replace(
                    pair,
                    response=refresh_response_headers(pair.response, revalidation_response),
                )
                for pair in identified_for_revalidation
            ],
            options=self.options,
        )
