#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "hishel[httpx]",
# ]
#
# [tool.uv.sources]
# hishel = { path = "../", editable = true }
# ///


import sqlite3

from hishel import SyncSqliteStorage
from hishel.httpx import SyncCacheClient

cl = SyncCacheClient(storage=SyncSqliteStorage(connection=sqlite3.connect(":memory:")))

cl.get("https://hishel.com/")
response = cl.get("https://hishel.com/")
print(response.extensions)
