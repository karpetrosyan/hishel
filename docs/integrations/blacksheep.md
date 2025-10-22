---
icon: material/sheep
---

# BlackSheep Integration

Hishel provides seamless integration with [BlackSheep](https://www.neoteroi.dev/blacksheep/) through ASGI middleware. You can use BlackSheep's built-in `cache_control` decorator to set Cache-Control headers, and combine it with Hishel's ASGI middleware for local server-side caching.

!!! tip "Two approaches"
    - Use BlackSheep's `@cache_control()` decorator to send Cache-Control headers to clients (browsers, CDNs, proxies)
    - Add Hishel's ASGI middleware to also cache responses locally based on those Cache-Control headers

---

## Installation

```bash
pip install hishel blacksheep
```

---

## Quick Start

### Cache-Control Headers Only

Use BlackSheep's built-in `cache_control` decorator:

```python
from blacksheep import Application, get
from blacksheep.server.headers.cache import cache_control

app = Application()

@get("/api/data")
@cache_control(max_age=300, public=True)
async def get_data():
    # Cache-Control: public, max-age=300
    return {"data": "Clients will cache this for 5 minutes"}
```

### With Local Server Caching

Combine BlackSheep's `cache_control` decorator with Hishel's ASGI middleware:

```python
from blacksheep import Application, get
from blacksheep.server.headers.cache import cache_control
from hishel.asgi import ASGICacheMiddleware
from hishel import AsyncSqliteStorage

app = Application()

@get("/api/data")
@cache_control(max_age=300, public=True)
async def get_data():
    # Cached locally AND by clients/CDNs
    return {"data": "Expensive operation result"}

# Wrap with Hishel's ASGI middleware for local caching
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
@get("/static/logo.png")
@cache_control(max_age=31536000, public=True, immutable=True)
async def get_logo():
    return {"file": "logo.png"}
```

### Public API Data

Cache public API responses:

```python
@get("/api/articles")
@cache_control(max_age=300, public=True)
async def get_articles():
    return {"articles": ["Article 1", "Article 2"]}
```

### Private User Data

Cache user-specific data (browsers only):

```python
@get("/api/user/profile")
@cache_control(max_age=300, private=True)
async def get_profile():
    return {"user": "john_doe"}
```

### CDN Optimization

Different cache times for browsers vs CDNs:

```python
@get("/api/data")
@cache_control(max_age=60, s_maxage=3600, public=True)
async def get_data():
    # Browsers: 1 minute, CDN: 1 hour
    return {"data": "..."}
```

### No Caching

Prevent caching of sensitive data:

```python
@get("/api/secrets")
@cache_control(no_cache=True, no_store=True)
async def get_secrets():
    # Cache-Control: no-cache, no-store
    return {"secret": "This response should not be cached or stored!"}
```

---

## How It Works

1. **BlackSheep's `@cache_control()` decorator** adds Cache-Control headers to responses
2. **Hishel's ASGI middleware** reads those headers and caches responses locally according to RFC 9111
3. **Subsequent requests** are served from the local cache when valid, or forwarded to your handlers when cache is stale/missing

This gives you the best of both worlds:
- ✅ Client-side caching (browsers, CDNs) via Cache-Control headers
- ✅ Server-side caching to reduce load on your application
- ✅ RFC 9111 compliant caching behavior
- ✅ Simple, declarative API using BlackSheep's native decorators

---

## Notes

!!! tip "Use BlackSheep's native decorator"
    BlackSheep has excellent built-in cache control support. Use `@cache_control()` from BlackSheep rather than creating custom headers.

!!! warning "no_store is strongest"
    `no_store` prevents all caching regardless of other directives.

---

## See Also

- [ASGI Integration](asgi.md) - General ASGI middleware documentation
- [FastAPI Integration](fastapi.md) - Similar integration with FastAPI
- [Storage Backends](../storages.md) - Configure cache storage
- [BlackSheep Documentation](https://www.neoteroi.dev/blacksheep/)
- [RFC 9111: HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
