import typing as tp

from httpcore import Request, Response

from hishel._headers import Vary, parse_cache_control

from ._utils import (
    BaseClock,
    Clock,
    extract_header_values,
    extract_header_values_decoded,
    header_presents,
    parse_date,
)

HEURISTICALLY_CACHEABLE_STATUS_CODES = (200, 203, 204, 206, 300, 301, 308, 404, 405, 410, 414, 501)

__all__ = ("Controller", "HEURISTICALLY_CACHEABLE_STATUS_CODES")


def get_updated_headers(
    stored_response_headers: tp.List[tp.Tuple[bytes, bytes]],
    new_response_headers: tp.List[tp.Tuple[bytes, bytes]],
) -> tp.List[tp.Tuple[bytes, bytes]]:
    updated_headers = []

    checked = set()

    for key, value in stored_response_headers:
        if key not in checked and key.lower() != b"content-length":
            checked.add(key)
            values = extract_header_values(new_response_headers, key)

            if values:
                updated_headers.extend([(key, value) for value in values])
            else:
                values = extract_header_values(stored_response_headers, key)
                updated_headers.extend([(key, value) for value in values])

    for key, value in new_response_headers:
        if key not in checked and key.lower() != b"content-length":
            values = extract_header_values(new_response_headers, key)
            updated_headers.extend([(key, value) for value in values])

    return updated_headers


def get_freshness_lifetime(response: Response) -> tp.Optional[int]:
    response_cache_control = parse_cache_control(extract_header_values_decoded(response.headers, b"Cache-Control"))

    if response_cache_control.max_age is not None:
        return response_cache_control.max_age

    if header_presents(response.headers, b"expires"):
        expires = extract_header_values_decoded(response.headers, b"expires", single=True)[0]
        expires_timestamp = parse_date(expires)
        date = extract_header_values_decoded(response.headers, b"date", single=True)[0]
        date_timestamp = parse_date(date)

        return expires_timestamp - date_timestamp
    return None


def get_heuristic_freshness(response: Response, clock: "BaseClock") -> int:
    last_modified = extract_header_values_decoded(response.headers, b"last-modified", single=True)

    if last_modified:
        last_modified_timestamp = parse_date(last_modified[0])
        now = clock.now()

        ONE_WEEK = 604_800

        return min(ONE_WEEK, int((now - last_modified_timestamp) * 0.1))

    ONE_DAY = 86_400
    return ONE_DAY


def get_age(response: Response, clock: "BaseClock") -> int:
    if not header_presents(response.headers, b"date"):  # pragma: no cover
        raise RuntimeError("The `Date` header is missing in the response.")

    date = parse_date(extract_header_values_decoded(response.headers, b"date")[0])

    now = clock.now()

    apparent_age = max(0, now - date)
    return int(apparent_age)


def allowed_stale(response: Response) -> bool:
    response_cache_control = parse_cache_control(extract_header_values_decoded(response.headers, b"Cache-Control"))

    if response_cache_control.no_cache:
        return False

    if response_cache_control.must_revalidate:
        return False

    return True


class Controller:
    def __init__(
        self,
        cacheable_methods: tp.Optional[tp.List[str]] = None,
        cacheable_status_codes: tp.Optional[tp.List[int]] = None,
        allow_heuristics: bool = False,
        clock: tp.Optional[BaseClock] = None,
        allow_stale: bool = False,
        always_revalidate: bool = False,
    ):
        self._cacheable_methods = []

        if cacheable_methods is None:
            self._cacheable_methods.append("GET")
        else:
            for method in cacheable_methods:
                if method.upper() not in ["GET", "HEAD"]:
                    raise RuntimeError(
                        f"Hishel does not support the HTTP method `{method}`. Please use either `GET` or `HEAD`."
                    )
                self._cacheable_methods.append(method.upper())

        self._cacheable_status_codes = cacheable_status_codes if cacheable_status_codes else [200, 301, 308]
        self._clock = clock if clock else Clock()
        self._allow_heuristics = allow_heuristics
        self._allow_stale = allow_stale
        self._always_revalidate = always_revalidate

    def is_cachable(self, request: Request, response: Response) -> bool:
        """
        Determines whether the response may be cached.

        The only thing this method does is determine whether the
        response associated with this request can be cached for later use.
        `https://www.rfc-editor.org/rfc/rfc9111.html#name-storing-responses-in-caches`
        lists the steps that this method simply follows.
        """
        method = request.method.decode("ascii")

        if response.status not in self._cacheable_status_codes:
            return False

        if response.status in (301, 308):
            return True

        # the request method is understood by the cache
        if method not in self._cacheable_methods:
            return False

        response_cache_control = parse_cache_control(extract_header_values_decoded(response.headers, b"cache-control"))
        request_cache_control = parse_cache_control(extract_header_values_decoded(request.headers, b"cache-control"))

        # the response status code is final
        if response.status // 100 == 1:
            return False

        # the no-store cache directive is not present (see Section 5.2.2.5)
        if request_cache_control.no_store:
            return False

        # note that the must-understand cache directive overrides
        # no-store in certain circumstances; see Section 5.2.2.3.
        if response_cache_control.no_store and not response_cache_control.must_understand:
            return False

        expires_presents = header_presents(response.headers, b"expires")
        # the response contains at least one of the following:
        # - a public response directive (see Section 5.2.2.9);
        # - a private response directive, if the cache is not shared (see Section 5.2.2.7);
        # - an Expires header field (see Section 5.3);
        # - a max-age response directive (see Section 5.2.2.1);
        # - if the cache is shared: an s-maxage response directive (see Section 5.2.2.10);
        # - a cache extension that allows it to be cached (see Section 5.2.3); or
        # - a status code that is defined as heuristically cacheable (see Section 4.2.2).
        if self._allow_heuristics and response.status in HEURISTICALLY_CACHEABLE_STATUS_CODES:
            return True

        if not any(
            [
                response_cache_control.public,
                response_cache_control.private,
                expires_presents,
                response_cache_control.max_age is not None,
            ]
        ):
            return False

        # response is a cachable!
        return True

    def _make_request_conditional(self, request: Request, response: Response) -> None:
        """
        Adds the precondition headers needed for response validation.

        This method will use the "Last-Modified" or "Etag" headers
        if they are provided in order to create precondition headers.

        See also (https://www.rfc-editor.org/rfc/rfc9111.html#name-sending-a-validation-reques)
        """

        if header_presents(response.headers, b"last-modified"):
            last_modified = extract_header_values(response.headers, b"last-modified", single=True)[0]
        else:
            last_modified = None

        if header_presents(response.headers, b"etag"):
            etag = extract_header_values(response.headers, b"etag", single=True)[0]
        else:
            etag = None

        precondition_headers: tp.List[tp.Tuple[bytes, bytes]] = []
        if last_modified:
            precondition_headers.append((b"If-Modified-Since", last_modified))
        if etag:
            precondition_headers.append((b"If-None-Match", etag))

        request.headers.extend(precondition_headers)

    def _validate_vary(self, request: Request, response: Response, original_request: Request) -> bool:
        """
        Determines whether the "vary" headers in the request and response headers are identical.

        See also (https://www.rfc-editor.org/rfc/rfc9111.html#name-calculating-cache-keys-with).
        """

        vary_headers = extract_header_values_decoded(response.headers, b"vary")
        vary = Vary.from_value(vary_values=vary_headers)
        for vary_header in vary._values:
            if vary_header == "*":
                return False  # pragma: no cover

            if extract_header_values(request.headers, vary_header) != extract_header_values(
                original_request.headers, vary_header
            ):
                return False

        return True

    def construct_response_from_cache(
        self, request: Request, response: Response, original_request: Request
    ) -> tp.Union[Response, Request, None]:
        """
        Specifies whether the response should be used, skipped, or validated by the cache.

        This method makes a decision regarding what to do with
        the stored response when it is retrieved from storage.
        It might be ready for use or it might need to be revalidated.
        This method mirrors the relevant section from RFC 9111,
        see (https://www.rfc-editor.org/rfc/rfc9111.html#name-constructing-responses-from).

        Returns:
            Response: This response is applicable to the request.
            Request: This response can be used for this request, but it must first be revalidated.
            None: It is not possible to use this response for this request.
        """

        # Use of responses with status codes 301 and 308 is always
        # legal as long as they don't adhere to any caching rules.
        if response.status in (301, 308):
            return response

        response_cache_control = parse_cache_control(extract_header_values_decoded(response.headers, b"Cache-Control"))
        request_cache_control = parse_cache_control(extract_header_values_decoded(request.headers, b"Cache-Control"))

        # request header fields nominated by the stored
        # response (if any) match those presented (see Section 4.1)
        if not self._validate_vary(request=request, response=response, original_request=original_request):
            # If the vary headers does not match, then do not use the response
            return None  # pragma: no cover

        # the stored response does not contain the
        # no-cache directive (Section 5.2.2.4), unless
        # it is successfully validated (Section 4.3)
        if (
            self._always_revalidate
            or response_cache_control.no_cache
            or response_cache_control.must_revalidate
            or request_cache_control.no_cache
        ):
            self._make_request_conditional(request=request, response=response)
            return request

        freshness_lifetime = get_freshness_lifetime(response)

        if freshness_lifetime is None:
            if self._allow_heuristics and response.status in HEURISTICALLY_CACHEABLE_STATUS_CODES:
                freshness_lifetime = get_heuristic_freshness(response=response, clock=self._clock)
            else:
                # If Freshness cannot be calculated, then send the request
                self._make_request_conditional(request=request, response=response)
                return request

        age = get_age(response, self._clock)
        is_fresh = freshness_lifetime > age

        # The min-fresh request directive indicates that the client
        # prefers a response whose freshness lifetime is no less than
        #  its current age plus the specified time in seconds.
        # That is, the client wants a response that will still
        # be fresh for at least the specified number of seconds.
        if request_cache_control.min_fresh is not None:
            if freshness_lifetime < (age + request_cache_control.min_fresh):
                return None

        # The max-stale request directive indicates that the
        # client will accept a response that has exceeded its freshness lifetime.
        # If a value is present, then the client is willing to accept a response
        # that has exceeded its freshness lifetime by no more than the specified
        # number of seconds. If no value is assigned to max-stale, then
        # the client will accept a stale response of any age.
        if not is_fresh and request_cache_control.max_stale is not None:
            exceeded_freshness_lifetime = age - freshness_lifetime

            if request_cache_control.max_stale < exceeded_freshness_lifetime:
                return None

        # The max-age request directive indicates that
        # the client prefers a response whose age is
        # less than or equal to the specified number of seconds.
        # Unless the max-stale request directive is also present,
        # the client does not wish to receive a stale response.
        if request_cache_control.max_age is not None:
            if request_cache_control.max_age < age:
                return None

            if request_cache_control.max_stale is None and not is_fresh:
                return None

        # the stored response is one of the following:
        #   fresh (see Section 4.2), or
        #   allowed to be served stale (see Section 4.2.4), or
        #   successfully validated (see Section 4.3).
        if is_fresh:
            return response
        else:
            # Otherwise, make a conditional request
            self._make_request_conditional(request=request, response=response)
            return request

    def handle_validation_response(self, old_response: Response, new_response: Response) -> Response:
        """
        Handles incoming validation response.

        This method takes care of what to do with the incoming
        validation response; if it is a 304 response, it updates
        the headers with the new response and returns it.

        This method mirrors the relevant section from RFC 9111,
        see (https://www.rfc-editor.org/rfc/rfc9111.html#name-handling-a-validation-respo).
        """
        if new_response.status == 304:
            headers = get_updated_headers(
                stored_response_headers=old_response.headers,
                new_response_headers=new_response.headers,
            )
            old_response.headers = headers
            return old_response
        else:
            return new_response
