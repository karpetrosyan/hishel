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

**Real-World Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    # Short TTL for frequently changing stock prices
    stocks = client.get(
        "https://api.example.com/stocks",
        extensions={"hishel_ttl": 60}  # 1 minute
    )

    # Long TTL for static configuration
    config = client.get(
        "https://api.example.com/config",
        extensions={"hishel_ttl": 86400}  # 24 hours
    )
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    # Short TTL for frequently changing stock prices
    stocks = session.get(
        "https://api.example.com/stocks",
        headers={"X-Hishel-Ttl": "60"}  # 1 minute
    )

    # Long TTL for static configuration
    config = session.get(
        "https://api.example.com/config",
        headers={"X-Hishel-Ttl": "86400"}  # 24 hours
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

**Real-World Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    # User session data - keep active sessions cached
    # Each access extends the cache lifetime
    session_data = client.get(
        "https://api.example.com/user/session",
        extensions={
            "hishel_ttl": 1800,  # 30 minutes
            "hishel_refresh_ttl_on_access": True  # Reset on each use
        }
    )

    # Analytics report - expire exactly 1 hour after creation
    # Don't extend lifetime even if accessed multiple times
    report = client.get(
        "https://api.example.com/reports/daily",
        extensions={
            "hishel_ttl": 3600,  # 1 hour
            "hishel_refresh_ttl_on_access": False  # Fixed expiration
        }
    )
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    # User session data - keep active sessions cached
    # Each access extends the cache lifetime
    session_data = session.get(
        "https://api.example.com/user/session",
        headers={
            "X-Hishel-Ttl": "1800",  # 30 minutes
            "X-Hishel-Refresh-Ttl-On-Access": "true"  # Reset on each use
        }
    )

    # Analytics report - expire exactly 1 hour after creation
    # Don't extend lifetime even if accessed multiple times
    report = session.get(
        "https://api.example.com/reports/daily",
        headers={
            "X-Hishel-Ttl": "3600",  # 1 hour
            "X-Hishel-Refresh-Ttl-On-Access": "false"  # Fixed expiration
        }
    )
    ```

---

### hishel_spec_ignore

**Type:** `bool | None`

**Description:** When `True`, Hishel ignores RFC 9111 caching rules and caches the response regardless of `Cache-Control`, `Expires`, or other standard headers. The response will be stored even if it would normally be uncacheable.

**Use Cases:**

- Force caching of responses with `no-store` or `no-cache`
- Cache responses without proper cache headers
- Override server caching directives for testing

**Default:** `False` (follow RFC 9111 specification)

!!! warning
    Use with caution. Ignoring the specification may cache sensitive data or stale content.

**Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    # Force caching even if server says not to
    response = client.get(
        "https://api.example.com/dynamic-content",
        extensions={"hishel_spec_ignore": True}
    )
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    # Force caching even if server says not to
    response = session.get(
        "https://api.example.com/dynamic-content",
        headers={"X-Hishel-Spec-Ignore": "true"}
    )
    ```

**Real-World Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    # Development: Cache API responses that don't have cache headers
    # This reduces API calls during development/testing
    response = client.get(
        "https://api.example.com/test-endpoint",
        extensions={
            "hishel_spec_ignore": True,
            "hishel_ttl": 300  # Cache for 5 minutes
        }
    )

    # Cache a response that has Cache-Control: no-store
    # Useful when you control both client and server
    response = client.get(
        "https://api.example.com/private-but-cacheable",
        extensions={
            "hishel_spec_ignore": True,
            "hishel_ttl": 60
        }
    )
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    # Development: Cache API responses that don't have cache headers
    # This reduces API calls during development/testing
    response = session.get(
        "https://api.example.com/test-endpoint",
        headers={
            "X-Hishel-Spec-Ignore": "true",
            "X-Hishel-Ttl": "300"  # Cache for 5 minutes
        }
    )

    # Cache a response that has Cache-Control: no-store
    # Useful when you control both client and server
    response = session.get(
        "https://api.example.com/private-but-cacheable",
        headers={
            "X-Hishel-Spec-Ignore": "true",
            "X-Hishel-Ttl": "60"
        }
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

**Real-World Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    # GraphQL: Cache different queries to the same endpoint
    query1 = client.post(
        "https://api.example.com/graphql",
        json={
            "query": "{ user(id: 1) { name email } }"
        },
        extensions={
            "hishel_body_key": True,
            "hishel_ttl": 300
        }
    )

    query2 = client.post(
        "https://api.example.com/graphql",
        json={
            "query": "{ posts { title author } }"
        },
        extensions={
            "hishel_body_key": True,
            "hishel_ttl": 300
        }
    )
    # These will be cached separately despite same URL

    # Search API: Cache different search queries
    search_python = client.post(
        "https://api.example.com/search",
        json={"q": "python", "limit": 10},
        extensions={
            "hishel_body_key": True,
            "hishel_ttl": 600
        }
    )

    search_javascript = client.post(
        "https://api.example.com/search",
        json={"q": "javascript", "limit": 10},
        extensions={
            "hishel_body_key": True,
            "hishel_ttl": 600
        }
    )
    # Different searches cached separately
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    # GraphQL: Cache different queries to the same endpoint
    query1 = session.post(
        "https://api.example.com/graphql",
        json={
            "query": "{ user(id: 1) { name email } }"
        },
        headers={
            "X-Hishel-Body-Key": "true",
            "X-Hishel-Ttl": "300"
        }
    )

    query2 = session.post(
        "https://api.example.com/graphql",
        json={
            "query": "{ posts { title author } }"
        },
        headers={
            "X-Hishel-Body-Key": "true",
            "X-Hishel-Ttl": "300"
        }
    )
    # These will be cached separately despite same URL

    # Search API: Cache different search queries
    search_python = session.post(
        "https://api.example.com/search",
        json={"q": "python", "limit": 10},
        headers={
            "X-Hishel-Body-Key": "true",
            "X-Hishel-Ttl": "600"
        }
    )

    search_javascript = session.post(
        "https://api.example.com/search",
        json={"q": "javascript", "limit": 10},
        headers={
            "X-Hishel-Body-Key": "true",
            "X-Hishel-Ttl": "600"
        }
    )
    # Different searches cached separately
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

**Real-World Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient
    import time

    client = SyncCacheClient()

    # Monitor cache performance
    cache_hits = 0
    cache_misses = 0

    for i in range(100):
        response = client.get("https://api.example.com/popular-data")
        
        if response.extensions.get("hishel_from_cache"):
            cache_hits += 1
        else:
            cache_misses += 1

    hit_rate = (cache_hits / 100) * 100
    print(f"Cache hit rate: {hit_rate}%")

    # Conditional processing based on cache status
    response = client.get("https://api.example.com/user/profile")
    
    if response.extensions.get("hishel_from_cache"):
        print("Using cached profile - may be slightly outdated")
    else:
        print("Fresh profile data from server")
        # Trigger additional processing for fresh data
        process_fresh_data(response.json())
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter
    import time

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    # Monitor cache performance
    cache_hits = 0
    cache_misses = 0

    for i in range(100):
        response = session.get("https://api.example.com/popular-data")
        
        if response.headers.get("X-Hishel-From-Cache") == "true":
            cache_hits += 1
        else:
            cache_misses += 1

    hit_rate = (cache_hits / 100) * 100
    print(f"Cache hit rate: {hit_rate}%")

    # Conditional processing based on cache status
    response = session.get("https://api.example.com/user/profile")
    
    if response.headers.get("X-Hishel-From-Cache") == "true":
        print("Using cached profile - may be slightly outdated")
    else:
        print("Fresh profile data from server")
        # Trigger additional processing for fresh data
        process_fresh_data(response.json())
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

**Real-World Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    # Track different cache states
    response = client.get("https://api.example.com/articles")

    from_cache = response.extensions.get("hishel_from_cache")
    revalidated = response.extensions.get("hishel_revalidated")

    if from_cache and not revalidated:
        print("✓ Fresh cache hit - no server contact")
    elif from_cache and revalidated:
        print("↻ Stale cache revalidated - saved bandwidth")
    else:
        print("✗ Cache miss - full response from server")

    # Analyze caching patterns
    revalidation_count = 0
    total_requests = 100

    for i in range(total_requests):
        resp = client.get("https://api.example.com/data")
        if resp.extensions.get("hishel_revalidated"):
            revalidation_count += 1

    print(f"Revalidation rate: {(revalidation_count/total_requests)*100}%")
    print("Tip: High revalidation rate might indicate TTL is too short")
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    # Track different cache states
    response = session.get("https://api.example.com/articles")

    from_cache = response.headers.get("X-Hishel-From-Cache") == "true"
    revalidated = response.headers.get("X-Hishel-Revalidated") == "true"

    if from_cache and not revalidated:
        print("✓ Fresh cache hit - no server contact")
    elif from_cache and revalidated:
        print("↻ Stale cache revalidated - saved bandwidth")
    else:
        print("✗ Cache miss - full response from server")

    # Analyze caching patterns
    revalidation_count = 0
    total_requests = 100

    for i in range(total_requests):
        resp = session.get("https://api.example.com/data")
        if resp.headers.get("X-Hishel-Revalidated") == "true":
            revalidation_count += 1

    print(f"Revalidation rate: {(revalidation_count/total_requests)*100}%")
    print("Tip: High revalidation rate might indicate TTL is too short")
    ```

---

### hishel_spec_ignored

**Type:** `bool | None`

**Description:** Indicates whether RFC 9111 caching specification was ignored for this response. When `True`, the response was cached despite having directives that would normally prevent caching (like `Cache-Control: no-store`).

**Use Cases:**

- Verify `hishel_spec_ignore` worked as expected
- Audit which responses bypass standard caching rules
- Debug forced caching behavior

**Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    # Force cache a response
    response = client.get(
        "https://api.example.com/no-cache-endpoint",
        extensions={"hishel_spec_ignore": True}
    )

    # Verify spec was ignored
    if response.extensions.get("hishel_spec_ignored"):
        print("✓ Caching rules were bypassed as requested")
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    # Force cache a response
    response = session.get(
        "https://api.example.com/no-cache-endpoint",
        headers={"X-Hishel-Spec-Ignore": "true"}
    )

    # Verify spec was ignored
    if response.headers.get("X-Hishel-Spec-Ignored") == "true":
        print("✓ Caching rules were bypassed as requested")
    ```

**Real-World Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    # Testing/Development: Force cache responses without proper headers
    response = client.get(
        "https://api.example.com/dev-endpoint",
        extensions={
            "hishel_spec_ignore": True,
            "hishel_ttl": 300
        }
    )

    # Log which responses bypass caching rules
    if response.extensions.get("hishel_spec_ignored"):
        print(f"⚠️  Spec ignored for: {response.url}")
        print(f"   Original Cache-Control: {response.headers.get('cache-control')}")
        print("   Response cached anyway")

    # Audit forced caching
    forced_cache_urls = []
    
    for url in api_endpoints:
        resp = client.get(url, extensions={"hishel_spec_ignore": True})
        if resp.extensions.get("hishel_spec_ignored"):
            forced_cache_urls.append(url)
    
    print(f"Total endpoints with forced caching: {len(forced_cache_urls)}")
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    # Testing/Development: Force cache responses without proper headers
    response = session.get(
        "https://api.example.com/dev-endpoint",
        headers={
            "X-Hishel-Spec-Ignore": "true",
            "X-Hishel-Ttl": "300"
        }
    )

    # Log which responses bypass caching rules
    if response.headers.get("X-Hishel-Spec-Ignored") == "true":
        print(f"⚠️  Spec ignored for: {response.url}")
        print(f"   Original Cache-Control: {response.headers.get('cache-control')}")
        print("   Response cached anyway")

    # Audit forced caching
    forced_cache_urls = []
    
    for url in api_endpoints:
        resp = session.get(url, headers={"X-Hishel-Spec-Ignore": "true"})
        if resp.headers.get("X-Hishel-Spec-Ignored") == "true":
            forced_cache_urls.append(url)
    
    print(f"Total endpoints with forced caching: {len(forced_cache_urls)}")
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

**Real-World Example:**

=== "httpx"
    ```python
    from hishel.httpx import SyncCacheClient

    client = SyncCacheClient()

    # Debug why responses aren't being cached
    response = client.get("https://api.example.com/user/profile")

    stored = response.extensions.get("hishel_stored")
    from_cache = response.extensions.get("hishel_from_cache")

    if not stored and not from_cache:
        print("⚠️  Response not cached!")
        print(f"   Status: {response.status_code}")
        print(f"   Cache-Control: {response.headers.get('cache-control')}")
        print("   Check server caching headers")

    # Monitor cache storage rate
    stored_count = 0
    not_stored_count = 0
    
    test_urls = [
        "https://api.example.com/static",
        "https://api.example.com/dynamic",
        "https://api.example.com/private",
    ]
    
    for url in test_urls:
        resp = client.get(url)
        if resp.extensions.get("hishel_stored"):
            stored_count += 1
            print(f"✓ {url} - cached")
        else:
            not_stored_count += 1
            print(f"✗ {url} - not cached")
    
    storage_rate = (stored_count / len(test_urls)) * 100
    print(f"\nStorage rate: {storage_rate}%")

    # Validate caching after configuration changes
    response = client.get(
        "https://api.example.com/test",
        extensions={"hishel_ttl": 600}
    )
    
    if response.extensions.get("hishel_stored"):
        print("✓ Configuration working - responses are being cached")
    else:
        print("✗ Configuration issue - check TTL and cache headers")
    ```

=== "requests"
    ```python
    import requests
    from hishel.requests import CacheAdapter

    session = requests.Session()
    session.mount("http://", CacheAdapter())
    session.mount("https://", CacheAdapter())

    # Debug why responses aren't being cached
    response = session.get("https://api.example.com/user/profile")

    stored = response.headers.get("X-Hishel-Stored") == "true"
    from_cache = response.headers.get("X-Hishel-From-Cache") == "true"

    if not stored and not from_cache:
        print("⚠️  Response not cached!")
        print(f"   Status: {response.status_code}")
        print(f"   Cache-Control: {response.headers.get('cache-control')}")
        print("   Check server caching headers")

    # Monitor cache storage rate
    stored_count = 0
    not_stored_count = 0
    
    test_urls = [
        "https://api.example.com/static",
        "https://api.example.com/dynamic",
        "https://api.example.com/private",
    ]
    
    for url in test_urls:
        resp = session.get(url)
        if resp.headers.get("X-Hishel-Stored") == "true":
            stored_count += 1
            print(f"✓ {url} - cached")
        else:
            not_stored_count += 1
            print(f"✗ {url} - not cached")
    
    storage_rate = (stored_count / len(test_urls)) * 100
    print(f"\nStorage rate: {storage_rate}%")

    # Validate caching after configuration changes
    response = session.get(
        "https://api.example.com/test",
        headers={"X-Hishel-Ttl": "600"}
    )
    
    if response.headers.get("X-Hishel-Stored") == "true":
        print("✓ Configuration working - responses are being cached")
    else:
        print("✗ Configuration issue - check TTL and cache headers")
    ```

---

## Metadata Reference Summary

### Setting Request Metadata

| Library | Method | Format |
|---------|--------|--------|
| **httpx** | `extensions` (recommended) | `extensions={"hishel_ttl": 3600}` (Python types) |
| **httpx** | `headers` | `headers={"X-Hishel-Ttl": "3600"}` (string values) |
| **requests** | `headers` | `headers={"X-Hishel-Ttl": "3600"}` (string values) |

### Request Metadata Fields

| Field | Header | Type | Description |
|-------|--------|------|-------------|
| `hishel_ttl` | `X-Hishel-Ttl` | `float` / `string` | Custom TTL in seconds |
| `hishel_refresh_ttl_on_access` | `X-Hishel-Refresh-Ttl-On-Access` | `bool` / `string` | Enable sliding expiration |
| `hishel_spec_ignore` | `X-Hishel-Spec-Ignore` | `bool` / `string` | Ignore RFC 9111 rules |
| `hishel_body_key` | `X-Hishel-Body-Key` | `bool` / `string` | Include body in cache key |

### Reading Response Metadata

| Library | Method | Example |
|---------|--------|---------|
| **httpx** | `extensions` dict | `response.extensions.get("hishel_from_cache")` |
| **httpx** | `headers` | `response.headers.get("X-Hishel-From-Cache")` |
| **requests** | `headers` | `response.headers.get("X-Hishel-From-Cache")` |

### Response Metadata Fields

| Field | Header | Type | Description |
|-------|--------|------|-------------|
| `hishel_from_cache` | `X-Hishel-From-Cache` | `bool` / `string` | Response from cache |
| `hishel_revalidated` | `X-Hishel-Revalidated` | `bool` / `string` | Response was revalidated |
| `hishel_spec_ignored` | `X-Hishel-Spec-Ignored` | `bool` / `string` | Spec was ignored |
| `hishel_stored` | `X-Hishel-Stored` | `bool` / `string` | Response was stored |

!!! note "Type Differences"
    - **httpx extensions**: Native Python types (`bool`, `float`)
    - **httpx/requests headers**: String values (`"true"`, `"false"`, `"3600"`)

---
