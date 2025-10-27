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

## See Also

- [Metadata Reference](../metadata.md) - Complete guide to caching metadata
- [Storage Documentation](../storages.md) - Storage backend configuration
- [Specification](../specification.md) - RFC 9111 state machine
- [HTTPX Integration](httpx.md) - Alternative async HTTP client
- [Requests Documentation](https://requests.readthedocs.io/) - Official Requests docs
