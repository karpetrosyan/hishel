---
icon: simple/python
---

# Requests Integration

Hishel provides seamless integration with [Requests](https://requests.readthedocs.io/), adding RFC 9111-compliant HTTP caching to your Requests applications with minimal code changes.

## Quick Start

Add caching to your Requests application using the `CacheAdapter`:

```python
import requests
from hishel.requests import CacheAdapter

# Create session with cache adapter
session = requests.Session()
session.mount("https://", CacheAdapter())
session.mount("http://", CacheAdapter())

# First request - fetches from origin
response = session.get("https://api.example.com/data")
print(response.headers.get("X-Hishel-From-Cache"))  # None

# Second request - served from cache
response = session.get("https://api.example.com/data")
print(response.headers.get("X-Hishel-From-Cache"))  # True
```

That's it! Hishel automatically caches responses according to RFC 9111 rules.

---

## Cache Adapter

Hishel provides `CacheAdapter`, a custom HTTPAdapter that adds caching to Requests sessions.

### Basic Usage

```python
import requests
from hishel.requests import CacheAdapter

# Create a session
session = requests.Session()

# Mount cache adapter for HTTP and HTTPS
adapter = CacheAdapter()
session.mount("https://", adapter)
session.mount("http://", adapter)

# Make requests as usual
response = session.get("https://api.example.com/users")

# All requests methods work
session.post("https://api.example.com/data", json={"key": "value"})
session.put("https://api.example.com/resource/1", data="content")

# Close when done
session.close()
```

**Using Context Manager:**

```python
import requests
from hishel.requests import CacheAdapter

with requests.Session() as session:
    session.mount("https://", CacheAdapter())
    session.mount("http://", CacheAdapter())
    
    response = session.get("https://api.example.com/data")
    print(response.json())
```

### Force Caching (Ignoring RFC 9111)

By default, Hishel follows RFC 9111 caching rules. To force caching regardless of response headers:

```python
import requests
from hishel import CacheOptions
from hishel.requests import CacheAdapter

session = requests.Session()
adapter = CacheAdapter(
    cache_options=CacheOptions(always_cache=True)
)
session.mount("https://", adapter)
session.mount("http://", adapter)

# This will be cached even without proper cache headers
response = session.get("https://api.example.com/data")
```

### Setting TTL (Time To Live)

Specify how long responses should be cached:

```python
import requests
from hishel import CacheOptions
from hishel.requests import CacheAdapter

# Cache for 1 hour (3600 seconds)
session = requests.Session()
adapter = CacheAdapter(
    cache_options=CacheOptions(ttl=3600)
)
session.mount("https://", adapter)
session.mount("http://", adapter)

response = session.get("https://api.example.com/data")
```

### Refresh on Hit

Update cache metadata on every cache hit to extend freshness:

```python
import requests
from hishel import CacheOptions
from hishel.requests import CacheAdapter

session = requests.Session()
adapter = CacheAdapter(
    cache_options=CacheOptions(refresh_on_hit=True)
)
session.mount("https://", adapter)
session.mount("http://", adapter)

response = session.get("https://api.example.com/data")
```

### Configuration

Configure storage backend and cache behavior:

```python
import requests
from hishel import CacheOptions, SyncSqliteStorage
from hishel.requests import CacheAdapter

session = requests.Session()

adapter = CacheAdapter(
    # Storage configuration
    storage=SyncSqliteStorage(
        database_path="my_cache.db",
        default_ttl=3600,  # 1 hour default TTL
        refresh_ttl_on_access=True
    ),
    
    # Cache behavior options
    cache_options=CacheOptions(
        shared=False,  # Private cache
        supported_methods=["GET", "HEAD"],
        allow_stale=False
    )
)

session.mount("https://", adapter)
session.mount("http://", adapter)
```

**Configuration Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `storage` | `SyncBaseStorage` | `None` (in-memory) | Storage backend for cached data |
| `cache_options` | `CacheOptions` | `None` (defaults) | RFC 9111 caching behavior configuration |
| `pool_connections` | `int` | `10` | Number of connection pools to cache |
| `pool_maxsize` | `int` | `10` | Max number of connections in pool |
| `max_retries` | `int` | `0` | Max retries for requests |
| `pool_block` | `bool` | `False` | Block when no free connections |

---

## Controlling Cache Behavior

### Using Headers

Set caching metadata using HTTP headers:

```python
import requests
from hishel.requests import CacheAdapter

session = requests.Session()
session.mount("https://", CacheAdapter())

# Custom TTL for specific request
response = session.get(
    "https://api.example.com/data",
    headers={"X-Hishel-Ttl": "300"}  # Cache for 5 minutes
)

# Ignore caching rules
response = session.get(
    "https://api.example.com/private",
    headers={"X-Hishel-Spec-Ignore": "true"}
)

# Multiple options
response = session.get(
    "https://api.example.com/search",
    headers={
        "X-Hishel-Ttl": "600",
        "X-Hishel-Refresh-Ttl-On-Access": "true",
        "X-Hishel-Body-Key": "true"  # Include body in cache key
    }
)
```

### Available Metadata

See [Metadata Documentation](../metadata.md) for complete reference:

- `X-Hishel-Ttl` - Custom TTL in seconds
- `X-Hishel-Refresh-Ttl-On-Access` - Enable sliding expiration
- `X-Hishel-Spec-Ignore` - Ignore RFC 9111 rules
- `X-Hishel-Body-Key` - Include body in cache key (for POST/GraphQL)

---

## Inspecting Cache Status

Check if responses came from cache using response headers:

```python
import requests
from hishel.requests import CacheAdapter

session = requests.Session()
session.mount("https://", CacheAdapter())

response = session.get("https://api.example.com/data")

# Check cache status
from_cache = response.headers.get("X-Hishel-From-Cache") == "True"
revalidated = response.headers.get("X-Hishel-Revalidated") == "True"
stored = response.headers.get("X-Hishel-Stored") == "True"

if from_cache and not revalidated:
    print("✓ Fresh cache hit")
elif from_cache and revalidated:
    print("↻ Revalidated (304)")
else:
    print("✗ Cache miss")

if stored:
    print("Response was cached for future requests")
```

---

## Migration from Standard Requests

Migrating existing Requests code to use Hishel is straightforward:

**Before (Standard Requests):**
```python
import requests

session = requests.Session()
response = session.get("https://api.example.com/data")
```

**After (With Caching):**
```python
import requests
from hishel.requests import CacheAdapter

session = requests.Session()
session.mount("https://", CacheAdapter())  # Add this line
session.mount("http://", CacheAdapter())   # Add this line
response = session.get("https://api.example.com/data")
```

All Requests features continue to work:

- ✓ Request parameters (`params`, `headers`, `json`, `data`)
- ✓ Authentication (`auth`)
- ✓ Timeouts (`timeout`)
- ✓ Proxies (`proxies`)
- ✓ SSL verification (`verify`)
- ✓ Cookies
- ✓ Redirects
- ✓ Sessions

---

## See Also

- [Metadata Reference](../metadata.md) - Complete guide to caching metadata
- [Storage Documentation](../storages.md) - Storage backend configuration
- [Specification](../specification.md) - RFC 9111 state machine
- [HTTPX Integration](httpx.md) - Alternative async HTTP client
- [Requests Documentation](https://requests.readthedocs.io/) - Official Requests docs
