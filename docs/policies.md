---
icon: octicons/lock-16
---

# Caching Policies

Hishel provides a flexible policy system that allows you to control caching behavior. 
Policies determine how requests and responses are cached, giving you fine-grained control over the caching strategy.

## Overview

A **policy** is an object that defines the caching strategy for your HTTP client. Hishel supports two main types of policies:

1. **SpecificationPolicy** - Follows RFC 9111 HTTP caching specification
2. **FilterPolicy** - Applies custom user-defined filtering logic

All policies inherit from the `CachePolicy` base class.

## SpecificationPolicy

The `SpecificationPolicy` implements RFC 9111 compliant HTTP caching. This is the default policy used by `Hishel` when no policy is explicitly provided.

### Configuration

```python
from hishel import CacheOptions, SpecificationPolicy

policy = SpecificationPolicy(
    cache_options=CacheOptions(
        shared=True,           # Act as a shared cache (proxy/CDN)
        allow_stale=False,     # Don't serve stale responses
        supported_methods=["GET", "HEAD"],  # Cache these methods
    )
)
```

### CacheOptions

The `SpecificationPolicy` accepts a `CacheOptions` object that configures how the cache behaves:

#### shared

Determines whether the cache operates as a shared cache or private cache.

**RFC 9111 Section 3.5**: [Authenticated Responses](https://www.rfc-editor.org/rfc/rfc9111.html#section-3.5)

- **Shared cache** (`True`): Acts as a proxy, CDN, or gateway cache serving multiple users.
  - Must respect `private` directives
  - Must handle `Authorization` header restrictions
  - Can use `s-maxage` directive instead of `max-age`

- **Private cache** (`False`): Acts as a browser or user-agent cache for a single user.
  - Can cache private responses
  - Ignores `s-maxage` directives

```python
# Shared cache (proxy/CDN)
policy = SpecificationPolicy(
    cache_options=CacheOptions(shared=True)
)

# Private cache (browser)
policy = SpecificationPolicy(
    cache_options=CacheOptions(shared=False)
)
```

#### supported_methods

HTTP methods that are allowed to be cached.

**RFC 9111 Section 3**: A cache MUST NOT store a response to a request unless the request method is understood by the cache.

```python
# Default: cache GET and HEAD only
policy = SpecificationPolicy(
    cache_options=CacheOptions(
        supported_methods=["GET", "HEAD"]
    )
)

# Cache POST responses (advanced use case)
policy = SpecificationPolicy(
    cache_options=CacheOptions(
        supported_methods=["GET", "HEAD", "POST"]
    )
)
```

#### allow_stale

Controls whether stale responses can be served without revalidation.

**RFC 9111 Section 4.2.4**: [Serving Stale Responses](https://www.rfc-editor.org/rfc/rfc9111.html#section-4.2.4)

```python
# Conservative: never serve stale
policy = SpecificationPolicy(
    cache_options=CacheOptions(allow_stale=False)
)

# Permissive: serve stale when allowed by directives
policy = SpecificationPolicy(
    cache_options=CacheOptions(allow_stale=True)
)
```

### Usage Examples

=== "HTTPX (Async)"

    ```python
    import httpx
    from hishel import AsyncCacheClient, SpecificationPolicy, CacheOptions

    policy = SpecificationPolicy(
        cache_options=CacheOptions(
            shared=False,  # Private browser cache
            allow_stale=False,
        )
    )

    async with AsyncCacheClient(policy=policy) as client:
        response = await client.get("https://api.example.com/data")
    ```

=== "HTTPX (Sync)"

    ```python
    import httpx
    from hishel import SyncCacheClient, SpecificationPolicy, CacheOptions
    from hishel import CacheOptions

    policy = SpecificationPolicy(
        cache_options=CacheOptions(
            shared=True,  # Shared proxy cache
            allow_stale=True,
        )
    )

    with SyncCacheClient(policy=policy) as client:
        response = client.get("https://api.example.com/data")
    ```

=== "Requests"

    ```python
    import requests
    from hishel.requests import CacheAdapter
    from hishel import SpecificationPolicy, CacheOptions

    policy = SpecificationPolicy(
        cache_options=CacheOptions(shared=False)
    )

    session = requests.Session()
    session.mount("https://", CacheAdapter(policy=policy))
    session.mount("http://", CacheAdapter(policy=policy))

    response = session.get("https://api.example.com/data")
    ```

=== "ASGI Middleware"

    ```python
    from hishel.asgi import ASGICacheMiddleware
    from hishel import SpecificationPolicy, CacheOptions

    policy = SpecificationPolicy(
        cache_options=CacheOptions(
            shared=True,  # Server-side shared cache
            allow_stale=False,
        )
    )

    app = ASGICacheMiddleware(
        app=your_asgi_app,
        policy=policy,
    )
    ```

## FilterPolicy

The `FilterPolicy` allows you to implement custom caching logic by applying user-defined filters to requests and responses. This is useful when you need fine-grained control over what gets cached based on criteria beyond HTTP headers.

### Configuration

```python
from hishel import FilterPolicy, BaseFilter

policy = FilterPolicy(
    request_filters=[...],   # List of request filters
    response_filters=[...],  # List of response filters
)
```

### Creating Custom Filters

Filters must inherit from `BaseFilter[T]` where `T` is either `Request` or `Response`.

```python
from hishel import BaseFilter, Request, Response

class MyRequestFilter(BaseFilter[Request]):
    def needs_body(self) -> bool:
        """Return True if the filter needs access to the request body."""
        return False

    def apply(self, item: Request, body: bytes | None) -> bool:
        """
        Return True to allow caching, False to bypass cache.
        
        Args:
            item: The request to filter
            body: The request body (only if needs_body() returns True)
        """
        # Your filtering logic here
        return True


class MyResponseFilter(BaseFilter[Response]):
    def needs_body(self) -> bool:
        """Return True if the filter needs access to the response body."""
        return False

    def apply(self, item: Response, body: bytes | None) -> bool:
        """
        Return True to cache the response, False to skip caching.
        
        Args:
            item: The response to filter
            body: The response body (only if needs_body() returns True)
        """
        # Your filtering logic here
        return True
```

### Filter Examples

#### Filter by URL Pattern

```python
import re
from hishel import BaseFilter, FilterPolicy, Request

class URLPatternFilter(BaseFilter[Request]):
    def __init__(self, pattern: str):
        self.pattern = re.compile(pattern)
    
    def needs_body(self) -> bool:
        return False
    
    def apply(self, item: Request, body: bytes | None) -> bool:
        # Only cache requests matching the pattern
        return bool(self.pattern.search(str(item.url)))

# Cache only API endpoints
policy = FilterPolicy(
    request_filters=[
        URLPatternFilter(r'/api/.*')
    ]
)
```

#### Filter by Response Status Code

```python
from hishel import BaseFilter, FilterPolicy, Response

class StatusCodeFilter(BaseFilter[Response]):
    def __init__(self, allowed_codes: list[int]):
        self.allowed_codes = allowed_codes
    
    def needs_body(self) -> bool:
        return False
    
    def apply(self, item: Response, body: bytes | None) -> bool:
        # Only cache successful responses
        return item.status_code in self.allowed_codes

# Cache only 200 and 304 responses
policy = FilterPolicy(
    response_filters=[
        StatusCodeFilter([200, 304])
    ]
)
```

#### Filter by Content Type

```python
from hishel import BaseFilter, FilterPolicy, Response

class ContentTypeFilter(BaseFilter[Response]):
    def __init__(self, allowed_types: list[str]):
        self.allowed_types = allowed_types
    
    def needs_body(self) -> bool:
        return False
    
    def apply(self, item: Response, body: bytes | None) -> bool:
        content_type = item.headers.get("content-type", "")
        return any(allowed in content_type for allowed in self.allowed_types)

# Cache only JSON and XML responses
policy = FilterPolicy(
    response_filters=[
        ContentTypeFilter(["application/json", "application/xml"])
    ]
)
```

#### Filter with Body Inspection

```python
import json
from hishel import BaseFilter, FilterPolicy, Response

class JSONResponseFilter(BaseFilter[Response]):
    def needs_body(self) -> bool:
        # We need access to the body to inspect it
        return True
    
    def apply(self, item: Response, body: bytes | None) -> bool:
        if body is None:
            return False
        
        try:
            data = json.loads(body)
            # Cache only if response contains 'cacheable' field set to True
            return data.get("cacheable", False)
        except json.JSONDecodeError:
            return False

policy = FilterPolicy(
    response_filters=[JSONResponseFilter()]
)
```

### Combining Multiple Filters

Filters are applied in sequence. All request filters must pass for the request to be checked against the cache. All response filters must pass for the response to be cached.

```python
from hishel import FilterPolicy

policy = FilterPolicy(
    request_filters=[
        URLPatternFilter(r'/api/.*'),
        MethodFilter(["GET", "HEAD"]),
    ],
    response_filters=[
        StatusCodeFilter([200, 203, 204, 300, 301, 304, 404, 405, 410]),
        ContentTypeFilter(["application/json"]),
        SizeFilter(max_size=1024 * 1024),  # Max 1MB
    ]
)
```

### Complete Example: GraphQL Caching

```python
import json
from hishel import AsyncCacheClient, FilterPolicy, BaseFilter, Request, Response

class GraphQLQueryFilter(BaseFilter[Request]):
    """Only cache GraphQL queries (not mutations)."""
    
    def needs_body(self) -> bool:
        return True
    
    def apply(self, item: Request, body: bytes | None) -> bool:
        if body is None:
            return False
        
        try:
            data = json.loads(body)
            query = data.get("query", "")
            # Cache only if it's a query, not a mutation
            return "mutation" not in query.lower()
        except json.JSONDecodeError:
            return False


class GraphQLSuccessFilter(BaseFilter[Response]):
    """Only cache successful GraphQL responses (no errors)."""
    
    def needs_body(self) -> bool:
        return True
    
    def apply(self, item: Response, body: bytes | None) -> bool:
        if item.status_code != 200 or body is None:
            return False
        
        try:
            data = json.loads(body)
            # Cache only if there are no GraphQL errors
            return "errors" not in data
        except json.JSONDecodeError:
            return False

# Create the policy
policy = FilterPolicy(
    request_filters=[GraphQLQueryFilter()],
    response_filters=[GraphQLSuccessFilter()],
)

# Use with HTTPX
async with AsyncCacheClient(policy=policy) as client:
    response = await client.post(
        "https://api.example.com/graphql",
        json={
            "query": "{ user(id: 1) { name email } }"
        }
    )
```

## Policy Comparison

| Feature | SpecificationPolicy | FilterPolicy |
|---------|-------------------|--------------|
| RFC 9111 Compliance | ✅ Full | ❌ None |
| Respects Cache-Control headers | ✅ Yes | ❌ No |
| Custom filtering logic | ❌ No | ✅ Yes |
| Body inspection | ❌ No | ✅ Yes |
| Use Case | Standard HTTP caching | Custom caching logic |
| Complexity | Simple | Moderate to Complex |

## Best Practices

### When to Use SpecificationPolicy

- **Standard web applications**: When caching public HTTP APIs that follow HTTP caching standards
- **CDN/Proxy scenarios**: When implementing shared caches that serve multiple users
- **Browser-like caching**: When you want behavior similar to a web browser's cache
- **REST APIs**: When working with well-designed REST APIs that use proper cache headers

### When to Use FilterPolicy

- **GraphQL APIs**: When you need to inspect query bodies to determine cacheability
- **Custom business logic**: When caching decisions depend on application-specific rules
- **Legacy APIs**: When working with APIs that don't properly implement HTTP caching headers
- **Fine-grained control**: When you need to cache based on response content, not just headers
- **POST request caching**: When you want to cache POST requests based on their content

### Performance Considerations

1. **Body Inspection**: Filters that set `needs_body() = True` will read the entire request/response body into memory. Use sparingly for large payloads.

2. **Filter Order**: Place cheaper filters (header-based) before expensive ones (body-based) to short-circuit early.

3. **Caching Strategy**: 
   - Use `SpecificationPolicy` for standard HTTP caching (faster, battle-tested)
   - Use `FilterPolicy` only when you need custom logic

4. **Memory Usage**: FilterPolicy may consume more memory when inspecting bodies. Consider implementing size limits in your filters.

## See Also

- [RFC 9111: HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111.html)
- [Specification State Machine](specification.md)
- [Storage Backends](storages.md)
- [GraphQL Integration](integrations/graphql.md)
