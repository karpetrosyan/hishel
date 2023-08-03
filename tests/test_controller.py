from httpcore import Request, Response

from hishel._controller import (
    Controller,
    allowed_stale,
    get_age,
    get_freshness_lifetime,
    get_heuristic_freshness,
)
from hishel._utils import BaseClock, Clock


def test_is_cachable_for_cachables():
    controller = Controller()

    request = Request(b"GET", b"https://example.com", headers=[])

    resposne = Response(200, headers=[(b"Expires", b"some-date")])

    assert controller.is_cachable(request=request, response=resposne)

    resposne = Response(200, headers=[(b"Cache-Control", b"max-age=10000")])

    assert controller.is_cachable(request=request, response=resposne)


def test_is_cachable_for_non_cachables():
    controller = Controller()

    request = Request(b"GET", b"https://example.com", headers=[])

    resposne = Response(200, headers=[])

    assert not controller.is_cachable(request=request, response=resposne)


def test_is_cachable_for_heuristically_cachable():
    controller = Controller(allow_heuristics=True)

    request = Request(b"GET", b"https://example.com", headers=[])

    resposne = Response(200, headers=[])

    assert controller.is_cachable(request=request, response=resposne)


def test_is_cachable_for_unsupported_method():
    controller = Controller(cacheable_methods=["POST"])

    request = Request(b"GET", b"https://example.com", headers=[])

    resposne = Response(200, headers=[(b"Expires", b"some-date")])

    assert not controller.is_cachable(request=request, response=resposne)


def test_is_cachable_for_unsupported_status():
    controller = Controller(cacheable_status_codes=[301])

    request = Request(b"GET", b"https://example.com", headers=[])

    resposne = Response(200, headers=[(b"Expires", b"some-date")])

    assert not controller.is_cachable(request=request, response=resposne)


def test_is_cachable_for_not_final():
    controller = Controller(cacheable_status_codes=[100])

    request = Request(b"GET", b"https://example.com", headers=[])

    resposne = Response(100, headers=[(b"Expires", b"some-date")])

    assert not controller.is_cachable(request=request, response=resposne)


def test_is_cachable_for_no_store():
    controller = Controller(allow_heuristics=True)

    request = Request(b"GET", b"https://example.com", headers=[])

    resposne = Response(200, headers=[(b"Cache-Control", b"no-store")])

    assert not controller.is_cachable(request=request, response=resposne)


def test_get_freshness_lifetime():
    response = Response(status=200, headers=[(b"Cache-Control", b"max-age=3600")])

    freshness_lifetime = get_freshness_lifetime(response=response)
    assert freshness_lifetime == 3600


def test_get_freshness_omit():
    response = Response(status=200, headers=[])

    freshness_lifetime = get_freshness_lifetime(response=response)
    assert freshness_lifetime is None


def test_get_freshness_lifetime_with_expires():
    response = Response(
        status=200,
        headers=[
            (b"Expires", b"Mon, 25 Aug 2015 12:00:00 GMT"),
            (b"Date", b"Mon, 24 Aug 2015 12:00:00 GMT"),
        ],
    )

    freshness_lifetime = get_freshness_lifetime(response=response)
    assert freshness_lifetime == 86400  # one day


def test_get_heuristic_freshness():
    ONE_WEEK = 604_800

    class MockedClock(BaseClock):
        def now(self) -> int:
            return 1093435200  # Mon, 25 Aug 2003 12:00:00 GMT

    response = Response(
        status=200, headers=[(b"Last-Modified", "Mon, 25 Aug 2003 12:00:00 GMT")]
    )
    assert get_heuristic_freshness(response=response, clock=MockedClock()) == ONE_WEEK


def test_get_heuristic_freshness_without_last_modified():
    ONE_DAY = 86400

    response = Response(200)
    assert get_heuristic_freshness(response=response, clock=Clock()) == ONE_DAY


def test_get_age():
    class MockedClock(BaseClock):
        def now(self) -> int:
            return 1440590400

    response = Response(
        status=200, headers=[(b"Date", b"Tue, 25 Aug 2015 12:00:00 GMT")]
    )
    age = get_age(response=response, clock=MockedClock())
    assert age == 86400  # One day


def test_allowed_stale_no_cache():
    response = Response(status=200, headers=[(b"Cache-Control", b"no-cache")])

    assert not allowed_stale(response)


def test_allowed_stale_must_revalidate():
    response = Response(status=200, headers=[(b"Cache-Control", b"must-revalidate")])

    assert not allowed_stale(response)


def test_allowed_stale_allowed():
    response = Response(status=200, headers=[(b"Cache-Control", b"max-age=3600")])

    assert allowed_stale(response)


def test_clock():
    date_07_19_2023 = 1689764505
    assert Clock().now() > date_07_19_2023


def test_permanent_redirect_cache():
    controller = Controller()

    request = Request(b"GET", b"https://example.com")

    response = Response(status=301)

    assert controller.is_cachable(request=request, response=response)

    response = Response(status=302)

    assert not controller.is_cachable(request=request, response=response)


def test_make_conditional_request_with_etag():
    controller = Controller()

    request = Request(
        b"GET",
        b"https://example.com",
        headers=[
            (b"Content-Type", b"application/json"),
        ],
    )

    response = Response(status=200, headers=[(b"Etag", b"some-etag")])

    controller._make_request_conditional(request=request, response=response)

    assert request.headers == [
        (b"Content-Type", b"application/json"),
        (b"If-None-Match", b"some-etag"),
    ]


def test_make_conditional_request_with_last_modified():
    controller = Controller()

    request = Request(
        b"GET",
        b"https://example.com",
        headers=[
            (b"Content-Type", b"application/json"),
        ],
    )

    response = Response(
        status=200, headers=[(b"Last-Modified", b"Wed, 21 Oct 2015 07:28:00 GMT")]
    )

    controller._make_request_conditional(request=request, response=response)

    assert request.headers == [
        (b"Content-Type", b"application/json"),
        (b"If-Unmodified-Since", b"Wed, 21 Oct 2015 07:28:00 GMT"),
    ]


def test_construct_response_from_cache_redirect():
    controller = Controller()
    response = Response(status=301)
    original_request = Request("GET", "https://example.com")
    request = Request("GET", "https://example.com")
    assert response is controller.construct_response_from_cache(
        request=request, response=response, original_request=original_request
    )


def test_construct_response_from_cache_fresh():
    class MockedClock(BaseClock):
        def now(self) -> int:
            return 1440504000

    controller = Controller(clock=MockedClock())
    response = Response(
        status=200,
        headers=[
            (b"Cache-Control", b"max-age=3600"),
            (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
        ],
    )
    original_request = Request("GET", "https://example.com")
    request = Request("GET", "https://example.com")
    assert response is controller.construct_response_from_cache(
        request=request, response=response, original_request=original_request
    )


def test_construct_response_from_cache_stale():
    class MockedClock(BaseClock):
        def now(self) -> int:
            return 1440504002

    controller = Controller(clock=MockedClock())
    response = Response(
        status=200,
        headers=[
            (b"Cache-Control", b"max-age=1"),
            (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
        ],
    )
    original_request = Request("GET", "https://example.com")
    request = Request("GET", "https://example.com")
    conditional_request = controller.construct_response_from_cache(
        request=request, response=response, original_request=original_request
    )
    assert isinstance(conditional_request, Request)


def test_construct_response_from_cache_with_no_cache():
    controller = Controller(allow_stale=True)
    response = Response(
        status=200,
        headers=[
            (b"Cache-Control", b"max-age=1, no-cache"),
            (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
        ],
    )
    original_request = Request("GET", "https://example.com")
    request = Request("GET", "https://example.com")
    conditional_request = controller.construct_response_from_cache(
        request=request, response=response, original_request=original_request
    )
    assert isinstance(conditional_request, Request)


def test_construct_response_heuristically():
    class MockedClock(BaseClock):
        def now(self) -> int:
            return 1440590400  # Mon, 26 Aug 2015 12:00:00 GMT

    controller = Controller(allow_heuristics=True, clock=MockedClock())

    # Age less than 7 days
    response = Response(
        status=200,
        headers=[
            (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
            (b"Last-Modified", b"Mon, 25 Aug 2003 12:00:00 GMT"),
        ],
    )
    original_request = Request("GET", "https://example.com")
    request = Request("GET", "https://example.com")

    res = controller.construct_response_from_cache(
        request=request, response=response, original_request=original_request
    )

    assert isinstance(res, Response)

    # Age more than 7 days
    response = Response(
        status=200,
        headers=[
            (b"Date", b"Mon, 18 Aug 2015 12:00:00 GMT"),
            (b"Last-Modified", b"Mon, 25 Aug 2003 12:00:00 GMT"),
        ],
    )

    res = controller.construct_response_from_cache(
        request=request, response=response, original_request=original_request
    )

    assert not isinstance(res, Response)


def test_handle_validation_response_changed():
    controller = Controller()

    old_response = Response(
        status=200, headers=[(b"old-response", b"true")], content=b"old"
    )

    new_response = Response(
        status=200, headers=[(b"new-response", b"true")], content=b"new"
    )

    response = controller.handle_validation_response(
        old_response=old_response, new_response=new_response
    )
    response.read()

    assert response.headers == [(b"new-response", b"true")]
    assert response.content == b"new"


def test_handle_validation_response_not_changed():
    controller = Controller()

    old_response = Response(
        status=200, headers=[(b"old-response", b"true")], content=b"old"
    )

    new_response = Response(
        status=304,
        headers=[(b"new-response", b"false"), (b"old-response", b"true")],
        content=b"new",
    )

    response = controller.handle_validation_response(
        old_response=old_response, new_response=new_response
    )
    response.read()

    assert response.headers == [(b"old-response", b"true"), (b"new-response", b"false")]
    assert response.content == b"old"


def test_vary_validation():
    original_request = Request(
        method="GET",
        url="https://example.com",
        headers=[
            (b"Content-Type", b"application/json"),
            (b"Content-Language", b"en-US"),
        ],
    )
    request = Request(
        method="GET",
        url="https://example.com",
        headers=[
            (b"Content-Type", b"application/json"),
            (b"Content-Language", b"en-US"),
        ],
    )

    response = Response(
        status=200,
        headers=[
            (b"Content-Type", b"application/json"),
            (b"Content-Language", b"en-US"),
            (b"Vary", b"Content-Type, Content-Language"),
        ],
    )

    controller = Controller()

    assert controller._validate_vary(
        request=request, response=response, original_request=original_request
    )

    original_request.headers.pop(0)

    assert not controller._validate_vary(
        request=request, response=response, original_request=original_request
    )


def test_vary_validation_value_mismatch():
    original_request = Request(
        method="GET",
        url="https://example.com",
        headers=[
            (b"Content-Type", b"application/json"),
            (b"Content-Language", b"en-US"),
        ],
    )

    request = Request(
        method="GET",
        url="https://example.com",
        headers=[
            (b"Content-Type", b"application/html"),
            (b"Content-Language", b"en-US"),
        ],
    )

    response = Response(
        status=200,
        headers=[
            (b"Content-Type", b"application/json"),
            (b"Content-Language", b"en-US"),
            (b"Vary", b"Content-Type, Content-Language"),
        ],
    )

    controller = Controller()

    assert not controller._validate_vary(
        request=request, response=response, original_request=original_request
    )


def test_vary_validation_value_wildcard():
    original_request = Request(
        method="GET",
        url="https://example.com",
        headers=[
            (b"Content-Type", b"application/json"),
            (b"Content-Language", b"en-US"),
        ],
    )

    request = Request(
        method="GET",
        url="https://example.com",
        headers=[
            (b"Content-Type", b"application/json"),
            (b"Content-Language", b"en-US"),
        ],
    )

    response = Response(
        status=200,
        headers=[
            (b"Content-Type", b"application/json"),
            (b"Content-Language", b"en-US"),
            (b"Vary", b"Content-Type, Content-Language, *"),
        ],
    )

    controller = Controller()

    assert not controller._validate_vary(
        request=request, response=response, original_request=original_request
    )
