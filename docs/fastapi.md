# FastAPI Integration

Hishel integrates with [FastAPI](https://fastapi.tiangolo.com/) in two ways:

- The `cache()` dependency sends `Cache-Control` headers to clients, browsers and CDNs.
- Adding [`ASGICacheMiddleware`](/asgi) also caches responses on your server, following those headers.

## Installation

```bash
pip install "hishel[fastapi]"
```

To also cache on your server, add the `async` extra:

```bash
pip install "hishel[fastapi,async]"
```

## Cache-Control Headers

Add `cache()` to the dependencies of an endpoint:

```python
from fastapi import FastAPI
from hishel.fastapi import cache

app = FastAPI()


@app.get("/api/data", dependencies=[cache(max_age=300, public=True)])
async def get_data():
    # Cache-Control: max-age=300, public
    return {"data": "Clients will cache this for 5 minutes"}
```

It also sets the `Date` header, which caches use to calculate freshness.

## Caching on the Server

Add the middleware, and Hishel will follow the headers you set with `cache()`:

```python
from fastapi import FastAPI
from hishel import AsyncSqliteStorage
from hishel.asgi import ASGICacheMiddleware
from hishel.fastapi import cache

app = FastAPI()
app.add_middleware(ASGICacheMiddleware, storage=AsyncSqliteStorage())


@app.get("/api/data", dependencies=[cache(max_age=300, public=True)])
async def get_data():
    # Cached on the server, and by clients and CDNs
    return {"data": "Expensive operation result"}
```

See the [ASGI integration](/asgi) for what to know about the middleware, in particular that it buffers responses.

## Common Examples

**Static assets**, cached for a long time:

```python
@app.get("/static/logo.png", dependencies=[cache(max_age=31536000, public=True, immutable=True)])
async def get_logo(): ...
```

**Private user data**, cached by browsers but not by shared caches, including the middleware:

```python
@app.get("/api/user/profile", dependencies=[cache(max_age=300, private=True)])
async def get_profile(): ...
```

**Different lifetimes** for browsers and for shared caches:

```python
@app.get("/api/data", dependencies=[cache(max_age=60, s_maxage=3600, public=True)])
async def get_data(): ...
```

**Sensitive data**, never cached:

```python
@app.get("/api/secrets", dependencies=[cache(no_store=True)])
async def get_secrets(): ...
```

## Directives

`cache()` takes one keyword argument for each directive:

- `max_age`: How long a response is fresh, in seconds.
- `s_maxage`: The same, for shared caches only. Overrides `max_age` for them.
- `public`: Any cache can store the response, even for a request with `Authorization`.
- `private`: Only private caches can store the response. Pass a list of field names to apply it to those headers only.
- `no_cache`: Caches must revalidate the response before using it. Pass a list of field names to apply it to those headers only.
- `no_store`: No cache can store the response.
- `no_transform`: Caches must not change the response.
- `must_revalidate`: Caches must revalidate the response once it is stale.
- `must_understand`: Caches must understand the status code to store the response.
- `proxy_revalidate`: The same as `must_revalidate`, for shared caches only.
- `immutable`: The response never changes while it is fresh.
- `stale_while_revalidate`: How long a stale response can be used while it is revalidated, in seconds.
- `stale_if_error`: How long a stale response can be used when the server fails, in seconds.

Hishel itself doesn't act on `no_transform`, `must_understand`, `proxy_revalidate`, `immutable`, `stale_while_revalidate` or `stale_if_error`. They are sent for browsers and CDNs that do.
