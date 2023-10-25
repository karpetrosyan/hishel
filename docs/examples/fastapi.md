---
icon: simple/fastapi
---

Many `FastAPI` users use `HTTPX` as a modern and very fast HTTP client, which also supports **async/await** syntax like FastAPI does.

Here is an example of how `HTTPX` can be used in `FastAPI`.

``` python
from fastapi import FastAPI
from httpx import AsyncClient
from httpx import Limits

app = FastAPI()
client = AsyncClient(limits=Limits(max_connections=1000))

@app.get("/")
async def main():
    response = await client.get('https://www.encode.io')
    return response.status_code
```

Now let's do some load testing using the popular load testing tool [Locust](https://locust.io/).

[Here are](https://raw.githubusercontent.com/karpetrosyan/hishel/master/docs/static/fastapi_without_cache.png) the test results:

<a href="https://raw.githubusercontent.com/karpetrosyan/hishel/master/docs/static/fastapi_without_cache.png">
    <img src="https://raw.githubusercontent.com/karpetrosyan/hishel/master/docs/static/fastapi_without_cache.png" alt="pypi">
</a>

Despite the fact that we use **async/await**, we got only **±70 RPS**.

Now let's change the `httpx.AsyncClient` to `hishel.AsyncCacheClient` and do the same tests again.

``` python hl_lines="2 6"
from fastapi import FastAPI
from hishel import AsyncCacheClient
from httpx import Limits

app = FastAPI()
client = AsyncCacheClient(limits=Limits(max_connections=1000))

@app.get("/")
async def main():
    response = await client.get('https://www.encode.io')
    return response.status_code
```

[Here are](https://raw.githubusercontent.com/karpetrosyan/hishel/master/docs/static/fastapi_with_cache.png) the test results:

<a href="https://raw.githubusercontent.com/karpetrosyan/hishel/master/docs/static/fastapi_with_cache.png">
    <img src="https://raw.githubusercontent.com/karpetrosyan/hishel/master/docs/static/fastapi_with_cache.png" alt="pypi">
</a>

Now we have more than **365+ RPS** using the power of HTTP caching.
