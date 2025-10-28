# /// script
# requires-python = ">=3.9"
# dependencies = [
#     "hishel[fastapi]",
#     "httpx",
#     "yaspin",
# ]
#
# [tool.uv.sources]
# hishel = { path = "../", editable = true }
# ///


import asyncio
import time

import httpx
import yaspin
from fastapi import FastAPI

from hishel.asgi import ASGICacheMiddleware
from hishel.fastapi import cache

app = FastAPI()

processed_requests = 0


@app.get("/items/", dependencies=[cache(max_age=5)])
async def read_item():
    global processed_requests
    processed_requests += 1
    return {"created_at": time.time(), "processed_requests": processed_requests}


async def main():
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=ASGICacheMiddleware(app))) as client:
        while True:
            response = await client.get("http://testserver/items/")
            data = response.json()
            print(f"Response: created_at={data['created_at']:.2f}, processed_requests={data['processed_requests']}, ")
            with yaspin.yaspin(text="Waiting 2 seconds before next request..."):
                await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
