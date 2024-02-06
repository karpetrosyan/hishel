import os
from datetime import datetime, timedelta
from pathlib import Path
from time import mktime
from wsgiref.handlers import format_date_time

import httpx
import pytest
import respx
from httpcore import Request

import hishel
from hishel._utils import generate_key


@pytest.fixture()
def hishel_client():
    storage = hishel.FileStorage()
    controller = hishel.Controller()
    client = hishel.CacheClient(
        storage=storage,
        controller=controller,
    )

    with client:
        yield client


@pytest.fixture()
def clear_cache():
    yield
    workdir = Path(os.getcwd() + "/.cache/hishel/")
    for file in workdir.iterdir():
        if file.is_file():
            os.unlink(file)



def test_client_301():
    with hishel.MockTransport() as transport:
        transport.add_responses([httpx.Response(301, headers=[(b"Location", b"https://example.com")])])
        with hishel.CacheClient(transport=transport, storage=hishel.InMemoryStorage()) as client:
            client.request(
                "GET",
                "https://www.example.com",
            )
            response = client.request(
                "GET",
                "https://www.example.com",
            )
            assert response.extensions["from_cache"]



@respx.mock
def test_empty_cachefile_handling(hishel_client: hishel.CacheClient, clear_cache: None) -> None:
    respx.get("https://example.com/").respond(
        status_code=200,
        headers=[
            ("Cache-Control", "public, max-age=86400, s-maxage=86400"),
            ("Date", format_date_time(mktime((datetime.now() - timedelta(hours=2)).timetuple()))),
        ],
        text="test",
    )

    request = Request(b"GET", "https://example.com/")
    key = generate_key(request)
    filedir = Path(os.getcwd() + "/.cache/hishel/" + key)

    hishel_client.get("https://example.com/")
    response = hishel_client.get("https://example.com/")

    assert response.status_code == 200
    assert response.text == "test"
    assert response.extensions["from_cache"]

    with open(filedir, "w+", encoding="utf-8") as file:
        file.truncate(0)
    assert os.path.getsize(filedir) == 0

    response = hishel_client.get("https://example.com/")
    assert response.status_code == 200
    assert response.text == "test"
    assert response.extensions["from_cache"] is False

    response = hishel_client.get("https://example.com/")
    assert response.extensions["from_cache"]
