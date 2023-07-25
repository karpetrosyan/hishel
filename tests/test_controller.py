from httpcore import Request, Response

from hishel._controller import (
    Controller,
    allowed_stale,
    get_age,
    get_freshness_lifetime,
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
    controller = Controller(cache_heuristically=True)

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
    controller = Controller(cache_heuristically=True)

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
    request = Request("GET", "https://example.com")
    assert response is controller.construct_response_from_cache(
        request=request, response=response
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
    request = Request("GET", "https://example.com")
    assert response is controller.construct_response_from_cache(
        request=request, response=response
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
    request = Request("GET", "https://example.com")
    conditional_request = controller.construct_response_from_cache(
        request=request, response=response
    )
    assert isinstance(conditional_request, Request)


def test_construct_response_from_cache_stale_with_allowed_stale():
    class MockedClock(BaseClock):
        def now(self) -> int:
            return 1440504002

    controller = Controller(clock=MockedClock(), allow_stale=True)
    response = Response(
        status=200,
        headers=[
            (b"Cache-Control", b"max-age=1"),
            (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
        ],
    )
    request = Request("GET", "https://example.com")
    assert response is controller.construct_response_from_cache(
        request=request, response=response
    )


def test_construct_response_from_cache_with_no_cache():
    controller = Controller(allow_stale=True)
    response = Response(
        status=200,
        headers=[
            (b"Cache-Control", b"max-age=1, no-cache"),
            (b"Date", b"Mon, 25 Aug 2015 12:00:00 GMT"),
        ],
    )
    request = Request("GET", "https://example.com")
    conditional_request = controller.construct_response_from_cache(
        request=request, response=response
    )
    assert isinstance(conditional_request, Request)


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
    )

    response = controller.handle_validation_response(
        old_response=old_response, new_response=new_response
    )
    response.read()

    assert response.headers == [(b"old-response", b"true"), (b"new-response", b"false")]
    assert response.content == b"old"
