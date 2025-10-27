---
icon: material/web
---

# ASGI Integration

Hishel provides ASGI middleware for caching HTTP responses in any ASGI-compatible application (FastAPI, Starlette, Django ASGI, etc.).

The middleware intercepts requests and responses, caching them according to HTTP caching specifications (RFC 9111) or custom rules.

---

## Installation

```bash
pip install hishel
```

No extra dependencies required - ASGI support is included by default.

---

## Quick Start

Wrap your ASGI application with `ASGICacheMiddleware`:

```python
from hishel.asgi import ASGICacheMiddleware

# Your ASGI application
async def app(scope, receive, send):
    if scope["type"] == "http":
        await send({
            "type": "http.response.start",
            "status": 200,
            "headers": [[b"cache-control", b"max-age=3600"]],
        })
        await send({
            "type": "http.response.body",
            "body": b"Hello, World!",
        })

# Wrap with caching middleware
cached_app = ASGICacheMiddleware(app)
```

---

## Basic Usage

# HTTP Caching with Hishel

Hishel provides elegant HTTP caching middleware for ASGI applications.

## Installation

```bash
pip install hishel fastapi aiohttp litestar blacksheep uvicorn
```

## Examples

=== "FastAPI"

    ```python
    # fastapi_example.py
    from fastapi import FastAPI
    from hishel import ASGICacheMiddleware

    app = FastAPI()

    @app.get("/")
    async def index():
        return {"message": "Hello, world!"}

    app = ASGICacheMiddleware(app)

    # Run: uvicorn fastapi_example:app --reload
    ```

=== "Litestar"

    ```python
    # litestar_example.py
    from litestar import Litestar, get
    from hishel import ASGICacheMiddleware

    @get("/")
    async def index() -> str:
        return "Hello, world!"

    app = ASGICacheMiddleware(Litestar([index]))

    # Run: uvicorn litestar_example:app --reload
    ```

=== "BlackSheep"

    ```python
    # blacksheep_example.py
    from blacksheep import Application, get
    from hishel import ASGICacheMiddleware

    app = Application()

    @get("/")
    async def index():
        return "Hello, world!"

    app = ASGICacheMiddleware(app)

    # Run: uvicorn blacksheep_example:app --reload
    ```

## See Also

- [Storage Backends](../storages.md) - Configure cache storage
- [Request/Response Metadata](../metadata.md) - Control caching behavior
- [FastAPI Integration](fastapi.md) - FastAPI-specific helpers
