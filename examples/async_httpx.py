#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "hishel[async, httpx]",
# ]
#
# [tool.uv.sources]
# hishel = { path = "../", editable = true }
# ///

import asyncio

import anysqlite

from hishel import AsyncSqliteStorage
from hishel.httpx import AsyncCacheClient


async def fetch_and_print(client, url: str):
    print(f"\n➡ Sending request to {url}...")
    response = await client.get(url)
    print(f"⬅ {response.status_code}, {len(response.content)} bytes")


async def main():
    url = "https://hishel.com/"
    async with AsyncCacheClient(storage=AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))) as client:
        await fetch_and_print(client, url)
        await fetch_and_print(client, url)


if __name__ == "__main__":
    asyncio.run(main())
