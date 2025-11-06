---
icon: material/power-plug-battery
---

# Custom Integrations

Hishel is designed to be flexible and easy to integrate with any HTTP client or server. This guide will help you build custom integrations for libraries that aren't yet supported out of the box.

## Converting Request/Response Models

The core of any Hishel integration is converting your library's request/response models to Hishel's internal `Request` and `Response` models. This translation layer allows Hishel to cache responses regardless of which HTTP library you're using.

In the Hishel codebase, you'll find conversion methods like `httpx_to_internal`, `requests_to_internal`, etc. that handle popular libraries. You can use these as reference implementations when building your own integration.

### Core Conversion Principles

Follow these guidelines when converting models:

**Response Content**
: The response content should be the actual data, possibly compressed, but decoded if it was sent with transfer encoding (like chunked). This content must be reusable—if you store compressed data, also preserve the `Content-Encoding` header so it can be decoded later.

**Headers**
: Store headers as-is, except for headers that the HTTP specification doesn't allow caching. Important: If a response stream has already been consumed and decoded into memory before reaching the cache layer, you must remove the `Content-Encoding` header since the content is no longer encoded.

**Requests**
: Converting request models is simpler than responses. Hishel doesn't recreate requests from cache or store request body streams—only headers, method, and URL are needed. The converted request may be modified by Hishel before being sent to the server, but exact preservation of the request body isn't critical.

## Using Cache Proxy Classes

Hishel provides `AsyncCacheProxy` and `SyncCacheProxy` helper classes that handle all the caching logic for you. These classes are independent of any specific HTTP library and work only with Hishel's internal models, making them perfect for building new integrations.

### AsyncCacheProxy

The `AsyncCacheProxy` class manages the entire HTTP caching state machine. You simply provide it with a function that sends requests, and it handles:

- Cache key generation
- Storage operations
- RFC 9111 compliance
- State machine transitions
- TTL management

**Basic Usage:**

```python
from hishel import AsyncCacheProxy, AsyncSqliteStorage, CacheOptions, SpecificationPolicy

async def send_request(request: Request) -> Response:
    # Your code to send the HTTP request
    # This is where you convert from internal models to your library
    # and back
    pass

# Create the cache proxy
cache_proxy = AsyncCacheProxy(
    request_sender=send_request,
    storage=AsyncSqliteStorage(),  # Optional, defaults to AsyncSqliteStorage
    policy=SpecificationPolicy(),   # Optional, defaults to SpecificationPolicy()
)

# Handle a request with caching
response = await cache_proxy.handle_request(request)
```

**Key Features:**

- **Automatic cache key generation**: Based on URL and optional request body hashing
- **Spec-compliant caching**: Full RFC 9111 state machine handling
- **Spec-ignoring mode**: Simple cache lookup without RFC 9111 rules
- **TTL refresh**: Automatic TTL updates on cache access if configured
- **Vary header support**: Proper handling of content negotiation

### SyncCacheProxy

The synchronous version works identically but for blocking I/O:

```python
from hishel import SyncCacheProxy, SyncSqliteStorage, SpecificationPolicy

def send_request(request: Request) -> Response:
    # Your synchronous request sending code
    pass

cache_proxy = SyncCacheProxy(
    request_sender=send_request,
    storage=SyncSqliteStorage(),
    policy=SpecificationPolicy(),
)

response = cache_proxy.handle_request(request)
```

### Integration Example: httpx

Here's how the httpx integration uses `AsyncCacheProxy`:

```python
from hishel import AsyncCacheProxy, Request, Response
import httpx

class AsyncCacheTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        next_transport: httpx.AsyncBaseTransport,
        storage: AsyncBaseStorage | None = None,
        cache_options: CacheOptions | None = None,
    ):
        self._transport = next_transport
        
        # Define how to send a request using the underlying transport
        async def send_request(internal_request: Request) -> Response:
            # Convert internal Request to httpx.Request
            httpx_request = internal_to_httpx(internal_request)
            
            # Send using underlying transport
            httpx_response = await self._transport.handle_async_request(httpx_request)
            
            # Convert httpx.Response to internal Response
            return httpx_to_internal(httpx_response)
        
        # Create the cache proxy with our send function
        self._cache_proxy = AsyncCacheProxy(
            request_sender=send_request,
            storage=storage,
            cache_options=cache_options,
        )
    
    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        # Convert httpx.Request to internal Request
        internal_request = httpx_to_internal(request)
        
        # Let the cache proxy handle the request
        internal_response = await self._cache_proxy.handle_request(internal_request)
        
        # Convert internal Response back to httpx.Response
        return internal_to_httpx(internal_response)
```

### When to Use Cache Proxy Classes

**Use `AsyncCacheProxy`/`SyncCacheProxy` when:**

- ✅ Building a new integration from scratch
- ✅ You want automatic RFC 9111 compliance
- ✅ You need both spec-respecting and spec-ignoring modes
- ✅ You want to focus on model conversion, not caching logic


### Configuration Options

Both proxy classes accept these parameters:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `request_sender` | `Callable` | **Required** | Function that sends requests using your HTTP library |
| `storage` | `AsyncBaseStorage` / `SyncBaseStorage` | `AsyncSqliteStorage()` / `SyncSqliteStorage()` | Where to store cached responses |
| `policy` | `CachePolicy` | `SpecificationPolicy()` | Caching policy to use |

## Implementation Example

Here's how to translate synchronous httpx Request/Response models to Hishel's internal models:

```python
import httpx
from typing import Iterator, Union, cast, overload
from hishel.models import Request, Response, RequestMetadata, Headers
from hishel.utils import filter_mapping, make_sync_iterator

# 128 KB
CHUNK_SIZE = 131072


@overload
def httpx_to_internal(value: httpx.Request) -> Request: ...
@overload
def httpx_to_internal(value: httpx.Response) -> Response: ...
def httpx_to_internal(
    value: Union[httpx.Request, httpx.Response],
) -> Union[Request, Response]:
    """
    Convert httpx.Request/httpx.Response to internal Request/Response.
    """
    headers = Headers(
        filter_mapping(
            Headers({key: value for key, value in value.headers.items()}),
            ["Transfer-Encoding"],
        )
    )
    if isinstance(value, httpx.Request):
        extension_metadata = RequestMetadata(
            hishel_refresh_ttl_on_access=value.extensions.get("hishel_refresh_ttl_on_access"),
            hishel_ttl=value.extensions.get("hishel_ttl"),
            hishel_body_key=value.extensions.get("hishel_body_key"),
        )
        headers_metadata = extract_metadata_from_headers(value.headers)

        for key, val in extension_metadata.items():
            if key in value.extensions:
                headers_metadata[key] = val

        return Request(
            method=value.method,
            url=str(value.url),
            headers=headers,
            stream=cast(Iterator[bytes], value.stream),
            metadata=headers_metadata,
        )
    elif isinstance(value, httpx.Response):
        stream = (
            make_sync_iterator([value.content]) if value.is_stream_consumed else value.iter_raw(chunk_size=CHUNK_SIZE)
        )

        return Response(
            status_code=value.status_code,
            headers=headers,
            stream=stream,
            metadata={},
        )
```

!!! warning "Critical: Stream Must Be Available"
    If a stream was consumed without being read into memory, there's no way to access the data. Hishel will raise an error in this case to prevent silent data loss.

## Common Pitfalls and Solutions

### Stream Consumption

Always ensure consumed streams are stored in memory before conversion. Check your library's documentation for methods like `is_stream_consumed` or `content` that indicate whether data is still available.

**Best Practice**: Read the stream into memory before creating the Hishel Response:
```python
# Good: Stream is preserved
if response.is_stream_consumed:
    stream = make_iterator([response.content])
else:
    stream = response.iter_raw()

# Bad: Stream was consumed elsewhere without storing
# This will fail when Hishel tries to cache
```

### Header Filtering

!!! tip "Which Headers to Remove"
    Remove these headers when caching responses:
    
    **Hop-by-hop headers** (never cached):
    
    - `Connection`
    - `Keep-Alive`
    - `Proxy-Authenticate`
    - `Proxy-Authorization`
    - `TE`
    - `Trailers`
    - `Transfer-Encoding`
    - `Upgrade`
    
    **Encoding headers** (remove only if content is decoded):
    
    - `Content-Encoding` - Remove when you've decoded the content

## Testing Your Integration

When implementing a custom integration, test these scenarios:

1. **Basic caching flow** - Request → Response → Cache → Retrieve
2. **Compressed responses** - gzip, deflate, brotli
3. **Chunked transfer encoding** - Verify proper handling
4. **Stream states** - Both consumed and unconsumed streams
5. **HTTP status codes** - 200, 304, 404, 500, etc.
6. **Content types** - JSON, HTML, binary data, large files
7. **Request metadata** - Custom Hishel extensions and TTL settings

### Example Test Case

```python
def test_basic_caching():
    # Create a request
    request = mylib.Request("GET", "https://example.com")
    
    # Convert to internal model
    internal_request = mylib_to_internal(request)
    
    # Verify conversion
    assert internal_request.method == "GET"
    assert internal_request.url == "https://example.com"
    assert "Transfer-Encoding" not in internal_request.headers
```

## Integration Template

Here's a template to get started with integrating a new library:

```python
from typing import Union, overload
from hishel.models import Request, Response, Headers, RequestMetadata

@overload
def mylib_to_internal(value: MyLibRequest) -> Request: ...

@overload
def mylib_to_internal(value: MyLibResponse) -> Response: ...

def mylib_to_internal(
    value: Union[MyLibRequest, MyLibResponse],
) -> Union[Request, Response]:
    """Convert MyLib models to Hishel internal models."""
    
    if isinstance(value, MyLibRequest):
        # Extract method, URL, and headers
        method = value.method
        url = str(value.url)
        headers = Headers({k: v for k, v in value.headers.items()})
        
        # Create request stream if body exists
        stream = value.stream if hasattr(value, 'stream') else iter([])
        
        # Extract Hishel metadata from extensions/extras if available
        metadata = {}
        if hasattr(value, 'extensions'):
            metadata = {
                'hishel_ttl': value.extensions.get('hishel_ttl'),
                # Add other metadata as needed
            }
        
        return Request(
            method=method,
            url=url,
            headers=headers,
            stream=stream,
            metadata=metadata,
        )
    
    elif isinstance(value, MyLibResponse):
        # Extract status code
        status_code = value.status_code
        
        # Filter headers (remove hop-by-hop and encoding headers if needed)
        headers = Headers({k: v for k, v in value.headers.items()})
        # Remove Transfer-Encoding
        headers = filter_headers(headers, ["Transfer-Encoding"])
        
        # Handle stream consumption state
        if value.is_consumed:
            # Stream was consumed, use stored content
            stream = make_iterator([value.content])
            # Remove Content-Encoding if content was decoded
            headers = filter_headers(headers, ["Content-Encoding"])
        else:
            # Stream still available
            stream = value.iter_content(chunk_size=131072)
        
        return Response(
            status_code=status_code,
            headers=headers,
            stream=stream,
            metadata={},
        )
```

## Need Help?

If you're building an integration and encounter issues:

1. **Check existing integrations** - Look at httpx, requests, and aiohttp implementations in the Hishel codebase
2. **Open an issue** - Post your use case on [GitHub Issues](https://github.com/karpetrosyan/hishel/issues)
3. **Contribute back** - Consider contributing your integration to help others!

## Related Documentation

- [ASGI Integration](asgi.md) - Full ASGI middleware for caching
- [HTTPX Integration](httpx.md) - Async HTTP client with caching
- [Requests Integration](requests.md) - Synchronous HTTP client with caching