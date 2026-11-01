# ASGI Integration

`ASGICacheMiddleware` caches the responses of any ASGI application on the server, so that repeated requests don't reach your application.

## Installation

```bash
pip install "hishel[async]"
```

## Quick Start

Wrap your application, and send caching headers from the endpoints you want cached:

```python
from hishel.asgi import ASGICacheMiddleware


async def my_app(scope, receive, send):
    await send(
        {
            "type": "http.response.start",
            "status": 200,
            "headers": [(b"cache-control", b"public, max-age=60")],
        }
    )
    await send({"type": "http.response.body", "body": b"Expensive result"})


app = ASGICacheMiddleware(my_app)
```

Lifespan and WebSocket traffic passes straight through to your application.

## Caching Modes

Unlike the client integrations, the middleware follows RFC 9111 by default, because a server usually serves many users and your application knows what can be shared. Responses are only cached when their headers allow it.

`rfc` accepts [`CacheOptions`](/httpx#caching-modes), or `False` to keep every successful `GET` and `HEAD` response until the storage expires it, ignoring HTTP caching headers:

```python
from hishel.asgi import ASGICacheMiddleware

app = ASGICacheMiddleware(my_app, rfc=False)
```

::: danger
With `rfc=False`, entries are shared by everyone who requests the same URL. Don't use it for an application with responses that depend on the user.

In RFC mode, a request with a `Cookie` header can also be answered from a shared entry. Send `private` or `no-store` from any endpoint whose response depends on the user's session.
:::

## Choosing a Storage

The middleware uses an `AsyncSqliteStorage` unless you pass another. See [Storages](/storages) for the options.

```python
from hishel import AsyncSqliteStorage
from hishel.asgi import ASGICacheMiddleware

app = ASGICacheMiddleware(my_app, storage=AsyncSqliteStorage(default_ttl=3600))
```

To close the storage when your application shuts down, call `await app.aclose()`.

## Things to Know

- **Responses are buffered:** each response is read fully into memory before it is sent. Endpoints that never finish responding, such as server-sent events, won't work behind the middleware, so keep them in an application that it doesn't wrap.
- **Entries are per host:** the cache key includes the `Host` header, so different hosts served by one application don't share entries.
- **`Date` is added:** a response without a `Date` header gets one, because freshness is calculated from it.
- **Cache hits skip your application:** that includes anything your application does per request, such as authentication, logging or metrics.
