import typing as tp

from httpcore import Request, Response

from ._headers import CacheControl
from ._utils import extract_header_values, extract_header_values_decoded, header_presents

HEURISTICALLY_CACHABLE = (200, 203, 204, 206, 300, 301, 308, 404, 405, 410, 414, 501)

class Controller:


    def __init__(self,
                 cacheable_methods: tp.Optional[tp.List[str]] = None,
                 cacheable_status_codes: tp.Optional[tp.List[int]] = None):

        if cacheable_methods:
            self._cacheable_methods = cacheable_methods
        else:
            self._cacheable_methods = ["GET"]

        if cacheable_status_codes:
            self._cacheable_status_codes = cacheable_status_codes
        else:
            self._cacheable_status_codes = [200]

    def is_cachable(self, request: Request, response: Response) -> bool:
        """
            According to https://www.rfc-editor.org/rfc/rfc9111.html#section-3
        """


        method = request.method.decode('ascii')
        response_cache_control = CacheControl.from_value(
            extract_header_values_decoded(response.headers, b'cache-control')
        )

        # the request method is understood by the cache
        if method not in self._cacheable_methods:
            return False

        # the response status code is final
        if response.status // 100 == 1:
            return False

        # the no-store cache directive is not present in the response (see Section 5.2.2.5)
        if response_cache_control.no_store is not None:
            return False

        expires_presents = header_presents(response.headers, b'expiers')
        # the response contains at least one of the following:
        # - a public response directive (see Section 5.2.2.9);
        # - a private response directive, if the cache is not shared (see Section 5.2.2.7);
        # - an Expires header field (see Section 5.3);
        # - a max-age response directive (see Section 5.2.2.1);
        # - if the cache is shared: an s-maxage response directive (see Section 5.2.2.10);
        # - a cache extension that allows it to be cached (see Section 5.2.3); or
        # - a status code that is defined as heuristically cacheable (see Section 4.2.2).
        if not any(
            [
                response_cache_control.public,
                response_cache_control.private,
                expires_presents,
                response_cache_control.max_age is not None,
                response.status in HEURISTICALLY_CACHABLE
            ]
        ):
            return False

        # response is a cachable!
        return True


    def get_updated_headers(
        self,
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
