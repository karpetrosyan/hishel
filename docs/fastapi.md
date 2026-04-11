
# FastAPI Integration

Hishel provides FastAPI integration in two ways:

1. **Cache-Control Headers Only** - Use the `cache()` dependency to send proper Cache-Control headers to clients (browsers, CDNs, proxies)
2. **Full Caching** - Combine with ASGI middleware to also cache responses locally based on the Cache-Control rules you specify


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
