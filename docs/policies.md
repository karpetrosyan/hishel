# Caching Policies

Hishel provides a flexible policy system that allows you to control caching behavior. 
Policies determine how requests and responses are cached, giving you fine-grained control over the caching strategy.

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

::: code-group

```python [HTTPX (Async)]
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

```python [HTTPX (Sync)]
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

```python [Requests]
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

```python [ASGI Middleware]
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

:::

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
