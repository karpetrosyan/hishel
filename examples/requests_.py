#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "hishel[requests]",
# ]
#
# [tool.uv.sources]
# hishel = { path = "../", editable = true }
# ///

import sqlite3

import requests

from hishel._core._storages._sync_sqlite import SyncSqliteStorage
from hishel.requests import CacheAdapter

session = requests.Session()

adapter = CacheAdapter(storage=SyncSqliteStorage(connection=sqlite3.connect(":memory:")))

session.mount("http://", adapter)
session.mount("https://", adapter)


def fetch_and_print(url: str):
    print(f"\n➡ Sending request to {url}...")
    response = session.get(url)

    print(f"🚀 Was Stored: {response.headers['x-hishel-stored']}")
    print(f"⏰ Created At: {response.headers['x-hishel-created-at']}")
    print(f"🔄 From Cache: {response.headers['x-hishel-from-cache']}")
    print(f"📍 Revalidated: {response.headers['x-hishel-revalidated']}")


if __name__ == "__main__":
    url = "https://hishel.com/"
    fetch_and_print(url)
    fetch_and_print(url)
