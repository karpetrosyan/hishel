from httpcore import Request, Response

from hishel._controller import BaseClock, Controller, get_age, get_freshness_lifetime


def test_is_cachable_for_cachables():
    controller = Controller()

    request = Request(
        b'GET',
        b'https://example.com',
        headers=[]
    )

    resposne = Response(
        200,
        headers=[
            (b'Expires', b'some-date')
        ]
    )

    assert controller.is_cachable(request=request, response=resposne)

    resposne = Response(
        200,
        headers=[
            (b'Cache-Control', b'max-age=10000')
        ]
    )

    assert controller.is_cachable(request=request, response=resposne)

def test_is_cachable_for_non_cachables():
    controller = Controller()

    request = Request(
        b'GET',
        b'https://example.com',
        headers=[]
    )

    resposne = Response(
        200,
        headers=[
        ]
    )

    assert not controller.is_cachable(request=request, response=resposne)


def test_is_cachable_for_heuristically_cachable():
    controller = Controller(cache_heuristically=True)

    request = Request(
        b'GET',
        b'https://example.com',
        headers=[]
    )

    resposne = Response(
        200,
        headers=[
        ]
    )

    assert controller.is_cachable(request=request, response=resposne)


def test_is_cachable_for_unsupported_method():
    controller = Controller(cacheable_methods=["POST"])

    request = Request(
        b'GET',
        b'https://example.com',
        headers=[]
    )

    resposne = Response(
        200,
        headers=[
            (b'Expires', b'some-date')
        ]
    )

    assert not controller.is_cachable(request=request, response=resposne)

def test_is_cachable_for_unsupported_status():
    controller = Controller(cacheable_status_codes=[301])

    request = Request(
        b'GET',
        b'https://example.com',
        headers=[]
    )

    resposne = Response(
        200,
        headers=[
            (b'Expires', b'some-date')
        ]
    )

    assert not controller.is_cachable(request=request, response=resposne)


def test_is_cachable_for_not_final():
    controller = Controller(cacheable_status_codes=[100])

    request = Request(
        b'GET',
        b'https://example.com',
        headers=[]
    )

    resposne = Response(
        100,
        headers=[
            (b'Expires', b'some-date')
        ]
    )

    assert not controller.is_cachable(request=request, response=resposne)


def test_is_cachable_for_no_store():
    controller = Controller(cache_heuristically=True)

    request = Request(
        b'GET',
        b'https://example.com',
        headers=[]
    )

    resposne = Response(
        200,
        headers=[
            (b'Cache-Control', b'no-store')
        ]
    )

    assert not controller.is_cachable(request=request, response=resposne)


def test_get_freshness_lifetime():

    response = Response(
        status=200,
        headers=[
            (b'Cache-Control', b'max-age=3600')
        ]
    )

    freshness_lifetime = get_freshness_lifetime(response=response)
    assert freshness_lifetime == 3600

def test_get_freshness_omit():

    response = Response(
        status=200,
        headers=[]
    )

    freshness_lifetime = get_freshness_lifetime(response=response)
    assert freshness_lifetime is None

def test_get_freshness_lifetime_with_expires():

    response = Response(
        status=200,
        headers=[
            (b'Expires', b'Mon, 25 Aug 2015 12:00:00 GMT'),
            (b'Date', b'Mon, 24 Aug 2015 12:00:00 GMT')
        ]
    )

    freshness_lifetime = get_freshness_lifetime(response=response)
    assert freshness_lifetime == 86400  # one day


def test_get_age():

    class MockedClock(BaseClock):

        def now(self) -> int:
            return 1440590400
    response = Response(
        status=200,
        headers=[
            (b'Date', b'Mon, 25 Aug 2015 12:00:00 GMT')
        ]
    )
    age = get_age(response=response, clock=MockedClock())
    assert age == 86400  # One day
