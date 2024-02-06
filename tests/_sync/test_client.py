import os
from datetime import datetime, timedelta
from pathlib import Path
from time import mktime
from wsgiref.handlers import format_date_time

import httpx
import pytest
from httpcore import Request

import hishel
from hishel._utils import generate_key



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



def test_empty_cachefile_handling(use_temp_dir):
    with hishel.MockTransport() as transport:
        transport.add_responses(
            [
                httpx.Response(
                    status_code=200,
                    headers=[
                        ("Cache-Control", "public, max-age=86400, s-maxage=86400"),
                        ("Date", format_date_time(mktime((datetime.now() - timedelta(hours=2)).timetuple()))),
                    ],
                    text="test",
                )
                for i in range(2)
            ]
        )

        with hishel.CacheClient(storage=hishel.FileStorage(), transport=transport) as client:
            request = Request(b"GET", "https://example.com/")
            key = generate_key(request)
            filedir = Path(os.getcwd() + "/.cache/hishel/" + key)

            client.get("https://example.com/")
            response = client.get("https://example.com/")

            assert response.status_code == 200
            assert response.text == "test"
            assert response.extensions["from_cache"]

            with open(filedir, "w+", encoding="utf-8") as file:
                file.truncate(0)
            assert os.path.getsize(filedir) == 0

            response = client.get("https://example.com/")
            assert response.status_code == 200
            assert response.text == "test"
            assert response.extensions["from_cache"] is False

            response = client.get("https://example.com/")
            assert response.extensions["from_cache"]
