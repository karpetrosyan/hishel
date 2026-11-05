#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "hishel[httpx]",
# ]
#
# [tool.uv.sources]
# hishel = { path = "../", editable = true }
# ///


import sqlite3

from hishel import SqliteStorage
from hishel.httpx import CacheClient

cl = CacheClient(storage=SqliteStorage(connection=sqlite3.connect(":memory:")))

cl.get("https://hishel.com/")
response = cl.get("https://hishel.com/")
print(response.extensions)
