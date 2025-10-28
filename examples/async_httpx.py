#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "hishel[async, httpx]",
# ]
#
# [tool.uv.sources]
# hishel = { path = "../", editable = true }
# ///

import asyncio
from typing import cast

import anysqlite

from hishel import ResponseMetadata
from hishel._core._storages._async_sqlite import AsyncSqliteStorage
from hishel.httpx import AsyncCacheClient


async def fetch_and_print(client, url: str):
    print(f"\n➡ Sending request to {url}...")
    response = await client.get(url)
    meta = cast(ResponseMetadata, response.extensions)

    print(f"🚀 Was Stored: {meta['hishel_stored']}")
    print(f"⏰ Created At: {meta['hishel_created_at']}")
    print(f"🔄 From Cache: {meta['hishel_from_cache']}")
    print(f"📍 Revalidated: {meta['hishel_revalidated']}")


async def main():
    url = "https://hishel.com/"
    async with AsyncCacheClient(storage=AsyncSqliteStorage(connection=await anysqlite.connect(":memory:"))) as client:
        await fetch_and_print(client, url)
        await fetch_and_print(client, url)


if __name__ == "__main__":
    asyncio.run(main())
