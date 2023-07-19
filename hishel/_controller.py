import time
import typing as tp

from httpcore import Request, Response

from hishel._headers import parse_cache_control

from ._utils import (
    extract_header_values,
    extract_header_values_decoded,
    header_presents,
    parse_date,
)

HEURISTICALLY_CACHABLE = (200, 203, 204, 206, 300, 301, 308, 404, 405, 410, 414, 501)

def get_updated_headers(
        stored_response_headers: tp.List[tp.Tuple[bytes, bytes]],
        new_response_headers: tp.List[tp.Tuple[bytes, bytes]]
    ) -> tp.List[tp.Tuple[bytes, bytes]]:
        updated_headers = []

        checked = set()

        for key, value in stored_response_headers:
            if key not in checked and key.lower() != b'content-length':
                checked.add(key)
                values = extract_header_values(new_response_headers, key)

                if values:
                    updated_headers.extend([(key, value) for value in values])
                else:
                    values = extract_header_values(stored_response_headers, key)
                    updated_headers.extend([(key, value) for value in values])

        for key, value in new_response_headers:
            if key not in checked and key.lower() != b'content-length':
                values = extract_header_values(new_response_headers, key)
                updated_headers.extend([(key, value) for value in values])

        return updated_headers


def get_freshness_lifetime(response: Response) -> tp.Optional[int]:

    response_cache_control = parse_cache_control(
        extract_header_values_decoded(response.headers, b'Cache-Control'))

    if response_cache_control.max_age is not None:
        return response_cache_control.max_age

    if header_presents(response.headers, b'expires'):
        expires = extract_header_values_decoded(response.headers, b'expires', single=True)[0]
        expires_timestamp = parse_date(expires)
        date = extract_header_values_decoded(response.headers, b'date', single=True)[0]
        date_timestamp = parse_date(date)

        return expires_timestamp - date_timestamp
    return None

def get_age(response: Response, clock: "BaseClock") -> tp.Optional[int]:

    date = parse_date(extract_header_values_decoded(response.headers, b'date')[0])

    now = clock.now()

    apparent_age = max(0, now - date)
    return int(apparent_age)

def allowed_stale(response: Response) -> bool:
    response_cache_control = parse_cache_control(
        extract_header_values_decoded(response.headers, b'Cache-Control'))

    if response_cache_control.no_cache:
        return False

    if response_cache_control.must_revalidate:
        return False

    return True

class BaseClock:

    def now(self) -> int:
        raise NotImplementedError()

class Clock(BaseClock):

    def now(self) -> int:
        return int(time.time())

class Controller:


    def __init__(self,
                 cacheable_methods: tp.Optional[tp.List[str]] = None,
                 cacheable_status_codes: tp.Optional[tp.List[int]] = None,
                 cache_heuristically: bool = False,
                 clock: tp.Optional[BaseClock] = None,
                 allow_stale: bool = False):

        if cacheable_methods:
            self._cacheable_methods = cacheable_methods
        else:
            self._cacheable_methods = ["GET"]

        if cacheable_status_codes:
            self._cacheable_status_codes = cacheable_status_codes
        else:
            self._cacheable_status_codes = [200, 301, 308]

        if clock:  # pragma: no cover
            self._clock = clock
        else:
            self._clock = Clock()
        self._cache_heuristically = cache_heuristically
        self._allow_stale = allow_stale

    def is_cachable(self, request: Request, response: Response) -> bool:
        """
            According to https://www.rfc-editor.org/rfc/rfc9111.html#section-3
        """

        method = request.method.decode('ascii')

        if response.status not in self._cacheable_status_codes:
            return False

        if response.status in (301, 308):
            return True

        # the request method is understood by the cache
        if method not in self._cacheable_methods:
            return False

        response_cache_control = parse_cache_control(
            extract_header_values_decoded(response.headers, b'cache-control')
        )

        # the response status code is final
        if response.status // 100 == 1:
            return False

        # the no-store cache directive is not present in the response (see Section 5.2.2.5)
        if response_cache_control.no_store:
            return False

        expires_presents = header_presents(response.headers, b'expires')
        # the response contains at least one of the following:
        # - a public response directive (see Section 5.2.2.9);
        # - a private response directive, if the cache is not shared (see Section 5.2.2.7);
        # - an Expires header field (see Section 5.3);
        # - a max-age response directive (see Section 5.2.2.1);
        # - if the cache is shared: an s-maxage response directive (see Section 5.2.2.10);
        # - a cache extension that allows it to be cached (see Section 5.2.3); or
        # - a status code that is defined as heuristically cacheable (see Section 4.2.2).
        if self._cache_heuristically and response.status in HEURISTICALLY_CACHABLE:
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

        if header_presents(response.headers, b'last-modified'):
            last_modified = extract_header_values(response.headers, b'last-modified', single=True)[0]
        else:
            last_modified = None

        if header_presents(response.headers, b'etag'):
            etag = extract_header_values(response.headers, b'etag', single=True)[0]
        else:
            etag = None

        precondition_headers: tp.List[tp.Tuple[bytes, bytes]] = []
        if last_modified:
            precondition_headers.append((b'If-Unmodified-Since', last_modified))
        if etag:
            precondition_headers.append((b'If-None-Match', etag))

        request.headers.extend(precondition_headers)


    def construct_response_from_cache(self,
                                      request: Request,
                                      response: Response) -> tp.Union[Response, Request]:

        if response.status in (301, 308):
            return response

        response_cache_control = parse_cache_control(
            extract_header_values_decoded(response.headers, b'Cache-Control'))

        if response_cache_control.no_cache:
            self._make_request_conditional(request=request, response=response)
            return request

        freshness_lifetime = get_freshness_lifetime(response)
        age = get_age(response, self._clock)

        if freshness_lifetime is None or age is None:  # pragma: no cover
            raise RuntimeError("Invalid response, can't calculate age")

        is_fresh = freshness_lifetime > age
        if is_fresh or (self._allow_stale and allowed_stale(response)):
            return response

        else:
            self._make_request_conditional(request=request, response=response)
            return request

    def handle_validation_response(self, old_response: Response, new_response: Response) -> Response:

        if new_response.status == 304:
            headers = get_updated_headers(
                stored_response_headers=old_response.headers,
                new_response_headers=new_response.headers)
            old_response.headers = headers
        else:
            return new_response
        return old_response
