---
icon: simple/fastapi
---

# FastAPI Integration

Hishel provides FastAPI integration in two ways:

1. **Cache-Control Headers Only** - Use the `cache()` dependency to send proper Cache-Control headers to clients (browsers, CDNs, proxies)
2. **Full Caching** - Combine with ASGI middleware to also cache responses locally based on the Cache-Control rules you specify

!!! tip "Choose your approach"
    - Use `cache()` dependency alone to let clients/CDNs cache responses
    - Add ASGI middleware on top to also cache locally on your server
    - Both approaches use the same Cache-Control headers for consistency

---

## Installation

```bash
pip install hishel[fastapi]
```

Or if you already have FastAPI installed:

```bash
pip install hishel
```

---

## Quick Start

### Cache-Control Headers Only

Use the `cache()` dependency to add Cache-Control headers:

```python
from fastapi import FastAPI
from hishel.fastapi import cache

app = FastAPI()

@app.get("/api/data", dependencies=[cache(max_age=300, public=True)])
async def get_data():
    # Cache-Control: public, max-age=300
    return {"data": "Clients will cache this for 5 minutes"}
```

### With Local Server Caching

Combine with ASGI middleware to also cache locally:

```python
from fastapi import FastAPI
from hishel.fastapi import cache
from hishel.asgi import ASGICacheMiddleware
from hishel import AsyncSqliteStorage

app = FastAPI()

@app.get("/api/data", dependencies=[cache(max_age=300, public=True)])
async def get_data():
    # Cached locally AND by clients/CDNs
    return {"data": "Expensive operation result"}

# Wrap with caching middleware to enable local caching
app = ASGICacheMiddleware(
    app,
    storage=AsyncSqliteStorage(),
)
```

---

## Common Examples

### Static Assets

Cache static files for a long time:

```python
@app.get("/static/logo.png", dependencies=[cache(max_age=31536000, public=True, immutable=True)])
async def get_logo():
    return {"file": "logo.png"}
```

### Public API Data

Cache public API responses:

```python
@app.get("/api/articles", dependencies=[cache(max_age=300, public=True)])
async def get_articles():
    return {"articles": [...]}
```

### Private User Data

Cache user-specific data (browsers only):

```python
@app.get("/api/user/profile", dependencies=[cache(max_age=300, private=True)])
async def get_profile():
    return {"user": "john_doe"}
```

### CDN Optimization

Different cache times for browsers vs CDNs:

```python
@app.get("/api/data", dependencies=[cache(
    max_age=60,      # Browsers: 1 minute
    s_maxage=3600,   # CDN: 1 hour
    public=True
)])
async def get_data():
    return {"data": "..."}
```

### No Caching

Prevent caching of sensitive data:

```python
@app.get("/api/secrets", dependencies=[cache(no_store=True)])
async def get_secrets():
    return {"secret": "value"}
```

---

## Notes

!!! tip "Combine directives wisely"
    Some directives conflict (e.g., `public` and `private`). Choose combinations that match your caching strategy.

!!! warning "no_store is strongest"
    `no_store` prevents all caching regardless of other directives.

!!! info "Field names for fine-grained control"
    `private` and `no_cache` accept lists of header names for precise control over which parts of the response require special handling.

---

## See Also

- [ASGI Integration](asgi.md) - Full ASGI middleware for caching
- [Request/Response Metadata](../metadata.md) - Control caching behavior
- [Storage Backends](../storages.md) - Configure cache storage
- [RFC 9111: HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [RFC 8246: Immutable Responses](https://www.rfc-editor.org/rfc/rfc8246.html)
- [RFC 5861: Cache-Control Extensions](https://www.rfc-editor.org/rfc/rfc5861.html)
