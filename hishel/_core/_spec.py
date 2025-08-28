from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, replace
from itertools import groupby
from typing import TYPE_CHECKING, Any, AsyncIterable, Dict, Generic, Iterable, Literal, Optional, TypeVar, Union

from hishel._core._headers import ContentRange, Range, Vary, parse_cache_control
from hishel._utils import aislice, chain, islice, parse_date, partition

if TYPE_CHECKING:
    from hishel import CompletePair, Request, Response


TState = TypeVar("TState", bound="State")
HEURISTICALLY_CACHEABLE_STATUS_CODES = (200, 203, 204, 206, 300, 301, 308, 404, 405, 410, 414, 501)
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
        raw_headers={
            **request.headers,
            **precondition_headers,
        },
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

    new_headers = {key: value for key, value in response.headers.items() if key.lower() not in need_to_be_excluded}
    return replace(
        response,
        raw_headers=new_headers,
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
            raw_headers=new_headers,
        ),
        is_cache_shared=True,
    )


@dataclass
class Merged:
    range: tuple[int, int]
    combined_stream: Iterable[bytes] | AsyncIterable[bytes]
    combined_pairs: list[CompletePair]


def merge_pairs(partial_pairs: list[CompletePair]) -> list[Merged]:
    def _sort_func(pair: CompletePair) -> int:
        if "content-range" not in pair.response.headers:
            raise RuntimeError("Cannot merge pairs without Content-Range header")  # pragma: nocover

        content_range = ContentRange.from_str(pair.response.headers["content-range"])

        if not content_range.range:
            raise RuntimeError("Cannot merge pairs without Content-Range header")

        return content_range.range[0]

    sorted_pairs = sorted(partial_pairs, key=_sort_func)
    merged: list[Merged] = []
    for pair in sorted_pairs:
        current_content_range = ContentRange.from_str(pair.response.headers["content-range"])
        if not current_content_range.range:
            raise RuntimeError("Cannot merge pairs without range information")

        if not merged:
            merged.append(
                Merged(range=current_content_range.range, combined_stream=pair.response.stream, combined_pairs=[pair])
            )
            continue

        last_merged = merged[-1]

        if (
            current_content_range.range[0] <= last_merged.range[1] + 1
            and current_content_range.range[1] > last_merged.range[1]
        ):
            if isinstance(pair.response.stream, Iterable):
                assert isinstance(last_merged.combined_stream, Iterable)
                overlapping_bytes = last_merged.range[1] - current_content_range.range[0] + 1

                last_merged.combined_stream = chain(
                    last_merged.combined_stream, islice(pair.response.stream, start=overlapping_bytes, stop=None)
                )
                last_merged.combined_pairs.append(pair)
                last_merged.range = (last_merged.range[0], current_content_range.range[1])

    return list(merged)


def combine_partial_content(partial_pairs: list[CompletePair]) -> list[tuple[CompletePair, list[CompletePair]]]:
    """
    3.4 Combining Partial Content Responses

    Given partial pairs, it merges all responses that share the same
    strong validator and overlap with each other. It then builds a
    merged pair using a modified content iterator that combines multiple
    contents into one, and returns a mapping of the final pair
    (which cannot be merged further) along with a list of pairs it invalidates.
    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-combining-partial-content
    """
    from hishel import CompletePair, Response

    # Map of newly created pair and pairs we are invalidating
    merged_pairs: list[tuple[CompletePair, list[CompletePair]]] = []
    sorted_pairs = sorted(
        partial_pairs, key=lambda pair: pair.response.headers.get("date", str(int(time.time()))), reverse=True
    )

    # A client that has received multiple partial responses
    # to GET requests on a target resource MAY combine those
    # responses into a larger continuous range if they share
    # the same strong validator.
    grouped_by_strong_validator = groupby(sorted_pairs, key=lambda pair: pair.response.headers.get("etag"))

    for validator, pairs_iter in grouped_by_strong_validator:
        if validator is None:
            continue

        pairs = list(pairs_iter)

        if not pairs:
            continue

        recent_pair = pairs[0]

        empty_response = Response(
            status_code=200,
            stream=[],
        )

        # If the most recent response is an incomplete 200 (OK)
        # response, then the header fields of that response are
        # used for any combined response and replace those
        # of the matching stored responses.
        if recent_pair.response.status_code == 200:
            headers = recent_pair.response.headers
        # If the most recent response is a 206 (Partial Content) response
        # and at least one of the matching stored responses is a 200 (OK),
        # then the combined response header fields consist of
        # the most recent 200 response's header fields.
        elif with_ok_status := list(filter(lambda pair: pair.response.status_code == 200, pairs)):
            headers = with_ok_status[0].response.headers
        # If all of the matching stored responses are 206 responses,
        # then the stored response with the most recent header fields
        # is used as the source of header fields for the combined response,
        # except that the client MUST use other header fields provided in
        # the new response, aside from Content-Range, to replace all instances
        # of the corresponding header fields in the stored response.
        else:
            headers = recent_pair.response.headers

        with_updated_headers = refresh_response_headers(
            empty_response,
            Response(
                status_code=200,
                raw_headers=headers,
                stream=[],
            ),
        )

        for merged in merge_pairs(pairs):
            if len(merged.combined_pairs) > 1:
                original_content_range = ContentRange.from_str(headers["content-range"])

                if merged.range[1] - merged.range[0] + 1 == (original_content_range.size or None):
                    response = Response(
                        status_code=200,
                        raw_headers={
                            **with_updated_headers.headers,
                            **(
                                {"Content-Length": str(original_content_range.size)}
                                if original_content_range.size
                                else {}
                            ),
                        },
                        stream=merged.combined_stream,
                        extra=merged.combined_pairs[0].response.extra,
                    )
                else:
                    response = Response(
                        status_code=206,
                        raw_headers={
                            **with_updated_headers.headers,
                            "Content-Range": f"bytes {merged.range[0]}-"
                            f"{merged.range[1]}/{original_content_range.size or '*'}",
                        },
                        stream=merged.combined_stream,
                        extra=merged.combined_pairs[0].response.extra,
                    )

                merged_pair = CompletePair(
                    id=uuid.uuid4(),
                    request=merged.combined_pairs[0].request,
                    meta=merged.combined_pairs[0].meta,
                    cache_key=merged.combined_pairs[0].cache_key,
                    response=response,
                    extra=merged.combined_pairs[0].extra,
                    complete_stream=True,
                )
                merged_pairs.append((merged_pair, merged.combined_pairs))
            else:
                merged_pair = merged.combined_pairs[0]
                merged_pairs.append((merged_pair, []))

    return merged_pairs


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
class UpdatePartials(Generic[TState], State):
    """
    The state that indicates that the client needs to update the partial content.
    """

    merged_pairs: list[tuple[CompletePair, list[CompletePair]]]
    """
    Mapping of pairs that we created from multiple partial pairs to the list of pairs we are invalidating.
    """

    next_state: TState

    def next(self) -> TState:
        return self.next_state


@dataclass
class IdleClient(State):
    """
    The class that represents the idle state of the client, which wants to send a
    request—possibly caching it and retrieving the response from the cache.

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-constructing-responses-from
    """

    def next(
        self, request: Request, associated_pairs: list[CompletePair]
    ) -> Union[UpdatePartials["CacheMiss" | "FromCache" | "NeedRevalidation"], CacheMiss]:
        request_range = Range.try_from_str(request.headers["range"]) if "range" in request.headers else None

        # A cache MUST write through requests with methods that are unsafe (Section 9.2.1 of [HTTP])
        # to the origin server; i.e., a cache is not allowed to generate a reply to such a request
        # before having forwarded the request and having received a corresponding response.
        if request.method.upper() not in SAFE_METHODS:
            return CacheMiss(request=request, options=self.options)

        # When presented with a request, a cache MUST NOT reuse a stored response unless:

        # 1. the presented target URI (Section 7.1 of [HTTP])
        # and that of the stored response match, and
        url_matches = lambda pair: pair.request.url == request.url  # noqa: E731

        # 2. the request method associated with the stored response
        # allows it to be used for the presented request, and
        method_matches = lambda pair: pair.request.method == request.method  # noqa: E731

        # 2.5 This step is specific to our implementation, in this
        # step we need to merge incomplete responses into a single one
        partial_pairs, complete_pairs = partition(associated_pairs, is_partial)

        merged_pairs = combine_partial_content(partial_pairs)
        associated_pairs = complete_pairs + [new_pair for new_pair, _ in merged_pairs]

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

        ready_to_use, need_revalidation = [], []
        for pair in filtered_pairs:
            if fresh_or_allowed_stale(pair):
                ready_to_use.append(pair)
            else:
                need_revalidation.append(pair)

        if request_range is None:
            next_state = self._handle_non_range_request(
                request,
                ready_to_use,
                need_revalidation,
            )
        else:
            next_state = self._handle_range_request(
                request,
                request_range,
                ready_to_use,
                need_revalidation,
            )
        return UpdatePartials(merged_pairs=merged_pairs, next_state=next_state, options=self.options)

    def _try_take_subrange(
        self,
        response: Response,
        request_range: Range,
    ) -> Response | None:
        """
        Given a response and a request range, builds a new response with that range
        if the response content fully covers it; otherwise, returns None.
        """

        if "content-range" not in response.headers:
            return None

        content_range = ContentRange.from_str(response.headers["content-range"])

        if content_range.range is None:
            return None

        start_range = request_range.range[0] if request_range.range[0] is not None else 0
        end_range = (
            request_range.range[1]
            if request_range.range[1] is not None
            else (content_range.size if content_range.size is not None else float("+inf"))
        )

        lower_bound = start_range >= content_range.range[0]
        upper_bound = end_range <= content_range.range[1]

        if not lower_bound and upper_bound:
            return None

        lower_skip = lower_bound - content_range.range[0]
        take = upper_bound - lower_bound + 1
        new_stream: Iterable[bytes] | AsyncIterable[bytes]
        if isinstance(response.stream, Iterable):
            new_stream = islice(response.stream, start=lower_skip, stop=take)
        elif isinstance(response.stream, AsyncIterable):
            new_stream = aislice(response.stream, start=lower_skip, stop=take)

        assert content_range.size
        return replace(
            response,
            stream=new_stream,
            status_code=206,
            raw_headers={
                **response.headers,
                "Content-Range": f"bytes {start_range}-{end_range}/{content_range.size}",
                "Content-Length": str(take),
            },
        )

    def _handle_range_request(
        self,
        request: Request,
        request_range: Range,
        ready_to_use: list[CompletePair],
        need_revalidation: list[CompletePair],
    ) -> Union["FromCache", "NeedRevalidation", "CacheMiss"]:
        partial_ready_to_use, complete_ready_to_use = partition(
            ready_to_use,
            is_partial,
        )

        if complete_ready_to_use:
            for pair in complete_ready_to_use:
                maybe_subrange_response = self._try_take_subrange(pair.response, request_range)

                if maybe_subrange_response:
                    return FromCache(
                        pair=replace(
                            pair,
                            response=replace(
                                maybe_subrange_response,
                                raw_headers={
                                    **maybe_subrange_response.headers,
                                    "age": str(get_age(maybe_subrange_response)),
                                },
                            ),
                        ),
                        options=self.options,
                    )

        for partial_pair in partial_ready_to_use:
            maybe_subrange_response = self._try_take_subrange(partial_pair.response, request_range)

            if maybe_subrange_response:
                return FromCache(
                    pair=replace(
                        partial_pair,
                        response=replace(
                            partial_pair.response,
                            raw_headers={
                                **partial_pair.response.headers,
                                "age": str(get_age(maybe_subrange_response)),
                            },
                        ),
                    ),
                    options=self.options,
                )

        if need_revalidation:
            return NeedRevalidation(
                request=make_conditional_request(request, need_revalidation[-1].response),
                revalidating_pairs=need_revalidation,
                options=self.options,
            )
        return CacheMiss(
            request=request,
            options=self.options,
        )

    def _handle_non_range_request(
        self,
        request: Request,
        ready_to_use: list[CompletePair],
        need_revalidation: list[CompletePair],
    ) -> FromCache | NeedRevalidation | CacheMiss:
        complete_ready_to_use = [pair for pair in ready_to_use if not is_partial(pair)]
        if complete_ready_to_use:
            # When a stored response is used to satisfy a request without validation,
            # a cache MUST generate an Age header field (Section 5.1), replacing any present
            # in the response with a value equal to the stored response's current_age; see Section 4.2.3.
            return FromCache(
                pair=replace(
                    complete_ready_to_use[0],
                    response=replace(
                        complete_ready_to_use[0].response,
                        raw_headers={
                            **complete_ready_to_use[0].response.headers,
                            "age": str(get_age(complete_ready_to_use[0].response)),
                        },
                    ),
                ),
                options=self.options,
            )

        elif need_revalidation:
            return NeedRevalidation(
                request=make_conditional_request(request, need_revalidation[-1].response),
                revalidating_pairs=need_revalidation,
                options=self.options,
            )
        else:
            return CacheMiss(
                request=request,
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
        return None


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
        return None


@dataclass
class CacheMiss(State):
    """
    Storing Responses in Caches

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-storing-responses-in-caches
    """

    request: Request
    """
    The request that missed the cache.
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
        def is_multipart_byterange(pair: CompletePair) -> bool:
            # We don't support 206 responses that are multipart/byteranges
            return pair.response.headers.get("content-type") == "multipart/byteranges"

        if pair.response.status_code in (206, 304):
            understands_how_to_cache = False if response.status_code == 304 or is_multipart_byterange(pair) else True
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
            pair=replace(pair, response=exclude_unstorable_headers(response, self.options.shared)), options=self.options
        )


@dataclass
class FromCache(State):
    pair: CompletePair
    """
    List of pairs that can be used to satisfy the request.
    """

    def next(self) -> None:
        return None


@dataclass
class NeedToBeUpdated(State):
    updating_pairs: list[CompletePair]

    def next(self) -> FromCache:
        return FromCache(pair=self.updating_pairs[-1], options=self.options)


@dataclass()
class NeedRevalidation(State):
    """
    4.3.3 Handling a validation response.

    RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-handling-a-validation-respo
    """

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
            return CacheMiss(request=revalidation_pair.request, options=self.options)
        elif revalidation_response.status_code // 100 == 5:
            # However, if a cache receives a 5xx (Server Error) response while attempting to
            # validate a response, it can either forward this response to the requesting client
            # or act as if the server failed to respond. In the latter case, the cache can send
            # a previously stored response, subject to its constraints on doing so
            # (see Section 4.2.4),or retry the validation request.
            return CacheMiss(request=revalidation_pair.request, options=self.options)
        raise RuntimeError(f"Unexpected response status code during revalidation: {revalidation_response.status_code}")

    def freshening_stored_responses(self, revalidation_response: Response) -> NeedToBeUpdated:
        """
        4.3.4 Freshening stored responses upon validation

        RFC reference: https://www.rfc-editor.org/rfc/rfc9111.html#name-freshening-stored-responses
        """

        identified_for_revalidation: list[CompletePair] = []
        if "etag" in revalidation_response.headers and (not revalidation_response.headers["etag"].startswith("W/")):
            for pair in self.revalidating_pairs:
                if pair.response.headers.get("etag") == revalidation_response.headers.get("etag"):
                    identified_for_revalidation.append(pair)
        elif revalidation_response.headers.get("last-modified"):
            for pair in self.revalidating_pairs:
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
