---
icon: material/apps
---

# Request and Response Metadata

Metadata allows you to control caching behavior and inspect cache operations. Hishel supports metadata on both requests (to control caching) and responses (to inspect what happened).

All metadata fields are prefixed with `hishel_` to avoid collisions with user data.

---

## Request Metadata

Request metadata controls how Hishel caches the request and its response. You can set metadata using:

- **httpx**: `extensions` parameter (recommended) or `X-Hishel-*` headers
- **requests**: `X-Hishel-*` headers

!!! tip "httpx supports both methods"
    While httpx supports both `extensions` and headers, using `extensions` is recommended as it provides better type safety and doesn't pollute HTTP headers sent to the server.

### hishel_ttl

**Type:** `float | None`

**Description:** Sets a custom time-to-live (TTL) for the cached response. After the specified number of seconds, the cached response will be considered expired and removed during cleanup.

**Use Cases:**

- Override default TTL for specific endpoints
- Set shorter TTL for frequently changing data
- Set longer TTL for static resources

**Default:** Storage's `default_ttl` setting

**Example:**

=== "httpx (extensions)"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    # Cache this response for 1 hour using extensions (recommended)
    response = client.get(
        "https://api.example.com/data",
        extensions={"hishel_ttl": 3600}
    )
    ```

=== "httpx (headers)"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    # Cache this response for 1 hour using headers
    response = client.get(
        "https://api.example.com/data",
        headers={"X-Hishel-Ttl": "3600"}
    )
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    # Cache this response for 1 hour
    response = session.get(
        "https://api.example.com/data",
        headers={"X-Hishel-Ttl": "3600"}
    )
    ```

---

### hishel_refresh_ttl_on_access

**Type:** `bool | None`

**Description:** When `True`, accessing a cached entry resets its TTL, keeping frequently accessed entries fresh. When `False`, the TTL countdown starts from the original storage time and is not affected by subsequent accesses.

**Use Cases:**

- Keep popular content cached longer (sliding expiration)
- Ensure rarely accessed content expires on schedule (fixed expiration)

**Default:** Storage's `refresh_ttl_on_access` setting (typically `True`)

**Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    # Enable sliding expiration - each access resets the timer
    response = client.get(
        "https://api.example.com/user/profile",
        extensions={"hishel_refresh_ttl_on_access": True}
    )
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    # Enable sliding expiration - each access resets the timer
    response = session.get(
        "https://api.example.com/user/profile",
        headers={"X-Hishel-Refresh-Ttl-On-Access": "true"}
    )
    ```

---

### hishel_body_key

**Type:** `bool | None`

**Description:** When `True`, includes the request body in cache key generation. This allows caching different responses for the same URL but with different request bodies, which is essential for POST requests and GraphQL queries.

**Use Cases:**

- Cache POST requests with different payloads
- Cache GraphQL queries (different queries to same endpoint)
- Cache search requests with different parameters in body

**Default:** `False` (body not included in cache key)

**Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    # Cache POST request based on body content
    response = client.post(
        "https://api.example.com/search",
        json={"query": "python"},
        extensions={"hishel_body_key": True}
    )
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    # Cache POST request based on body content
    response = session.post(
        "https://api.example.com/search",
        json={"query": "python"},
        headers={"X-Hishel-Body-Key": "true"}
    )
    ```

---

## Response Metadata

Response metadata provides information about cache operations that occurred. These fields are read-only and set by Hishel.

### hishel_from_cache

**Type:** `bool | None`

**Description:** Indicates whether the response was served from cache (`True`) or fetched from the origin server (`False`).

**Use Cases:**

- Monitor cache hit rates
- Debug caching behavior
- Log cache performance
- Conditional logic based on cache status


**Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    response = client.get("https://api.example.com/data")

    # Check if response came from cache
    if response.extensions.get("hishel_from_cache"):
        print("✓ Cache hit")
    else:
        print("✗ Cache miss - fetched from origin")
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    response = session.get("https://api.example.com/data")

    # Check if response came from cache
    if response.headers.get("X-Hishel-From-Cache") == "true":
        print("✓ Cache hit")
    else:
        print("✗ Cache miss - fetched from origin")
    ```

---

### hishel_revalidated

**Type:** `bool | None`

**Description:** Indicates whether a stale cached response was revalidated with the origin server. When `True`, the response was in cache but required validation (typically resulting in a 304 Not Modified response).

**Use Cases:**

- Monitor revalidation frequency
- Debug cache freshness logic
- Track conditional request behavior
- Optimize cache TTL settings


**Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    response = client.get("https://api.example.com/data")

    # Check if cached response was revalidated
    if response.extensions.get("hishel_revalidated"):
        print("Response was revalidated (304 Not Modified)")
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    response = session.get("https://api.example.com/data")

    # Check if cached response was revalidated
    if response.headers.get("X-Hishel-Revalidated") == "true":
        print("Response was revalidated (304 Not Modified)")
    ```

---

### hishel_stored

**Type:** `bool | None`

**Description:** Indicates whether the response was successfully stored in cache. When `True`, the response met all caching requirements and was saved. When `False`, the response was not cacheable (e.g., due to `Cache-Control: no-store`).

**Use Cases:**

- Verify responses are being cached
- Debug why responses aren't cached
- Monitor cache storage success rate
- Validate caching configuration


**Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    response = client.get("https://api.example.com/data")

    # Check if response was cached
    if response.extensions.get("hishel_stored"):
        print("✓ Response stored in cache")
    else:
        print("✗ Response not cached")
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    response = session.get("https://api.example.com/data")

    # Check if response was cached
    if response.headers.get("X-Hishel-Stored") == "true":
        print("✓ Response stored in cache")
    else:
        print("✗ Response not cached")
    ```

### hishel_created_at

**Type:** `float | None`

**Description:** POSIX timestamp (seconds since the epoch) indicating when the response entry was created in the cache. This value is set by Hishel when the response is stored and can be used with `hishel_ttl` to compute remaining freshness.

**Use Cases:**

- Determine when an entry was cached for logging or debugging.
- Compute remaining TTL: `remaining = hishel_ttl - (now - hishel_created_at)`.

**Example (httpx extensions):**

```python
created = response.extensions.get("hishel_created_at")
if created:
    print("Cached at:", created)
```

**Example (requests headers):**

```python
created = response.headers.get("X-Hishel-Created-At")
if created:
    print("Cached at:", created)
```

---