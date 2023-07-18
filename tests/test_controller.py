from httpcore import Request, Response

from hishel._controller import Controller


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
        201,
        headers=[
        ]
    )

    assert not controller.is_cachable(request=request, response=resposne)


def test_is_cachable_for_heuristically_cachable():
    controller = Controller()

    request = Request(
        b'GET',
        b'https://example.com',
        headers=[]
    )

    resposne = Response(
        201,
        headers=[
        ]
    )

    assert not controller.is_cachable(request=request, response=resposne)


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
