# Getting Started

## Installation

```bash
pip install hishel
```

### With HTTPX

```python
from hishel.httpx import AsyncCacheClient

async with AsyncCacheClient() as client:
    # First request - fetches from origin
    await client.get("https://hishel.com")
    # Second request - served from cache
    response = await client.get("https://hishel.com")
    print(response.text)
```

## with requests

```python
import requests
from hishel.requests import CacheAdapter

session = requests.Session()
session.mount("https://", CacheAdapter())
session.mount("http://", CacheAdapter())

# First request - fetches from origin
response = session.get("https://hishel.com")

# Second request - served from cache
response = session.get("https://hishel.com")
```

## with FastAPI

```python
from fastapi import FastAPI
from hishel import AsyncSqliteStorage
from hishel.fastapi import cache
from hishel.asgi import ASGICacheMiddleware

app = FastAPI()

@app.get("/api/data", dependencies=[cache(max_age=300, public=True)])
async def get_data():
    # Cache-Control: public, max-age=300
    return {"data": "cached for 5 minutes"}


app = ASGICacheMiddleware(app, storage=AsyncSqliteStorage())
```

## with BlackSheep

```python
from blacksheep import Application, get
from blacksheep.server.headers.cache import cache_control

app = Application()

@get("/api/data")
@cache_control(max_age=300, public=True)
async def get_data():
    # Cache-Control: public, max-age=300
    return {"data": "cached for 5 minutes"}
```