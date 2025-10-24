---
icon: material/power-plug-battery
---

# Custom Integrations

Hishel was made to be very flexible and easy to integrate with any HTTP client or server.

## Converting Request/Response Models

One of the core part to integrate Hishel with any library is to convert its request/response models to Hishel's internal `Request` and `Response` models.

In the codebase, you find find methods like `httpx_to_internal`, `requests_to_internal`, etc. that convert popular libraries' models to Hishel's internal models.

There are some core principles to follow when converting models:

- **Response Content**: Note that the content of request should be the actual data of the content, possible compressed, but decoded if was sent with transfer-encoding like chunked. Note that this body should be re-usedable, so if we store the compressed data, we should also store content-encoding header to be able to decode it later.
- **Headers**: Headers are stored as-is, expect for headers that specification doesn't allow to be stored. Note that there is a case when before response reaches to the cache layer, it's stream already consumed and stored into a memory, in such cases, note that you can't create hishel Response model without removing content-encoding header, because the content is already decoded.
- **Request**: Converting request models is relatively simpler then responses, we don't re-create the request from the cache and we don't even store it's stream, we only store the headers, method and url. The converted request might be modified by the hishel and be requested to be sent to the server, which is the responsibility of the integration layer, so there is not a critical requirement to store the request body exactly as it was sent.

## Implementation Example

The method that translates synchronous httpx Request/Response models to Hishel's internal models could look like this:

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
            hishel_spec_ignore=value.extensions.get("hishel_spec_ignore"),
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
    If stream was consumed and was not read into memory, there is no way to access the data so hishel will raise an error.

## Common Pitfalls and Solutions

### Stream Consumption

Always ensure consumed streams are stored in memory before conversion. If the response stream was consumed **without** being read into memory, there's no way to access the data. Hishel will raise an error in this case.

### Header Filtering

!!! tip "Which Headers to Remove"
    Remove these headers when caching:
    
    - `Content-Encoding` - When you've decoded the content
    - `Transfer-Encoding` - Hop-by-hop header
    - `Connection` - Hop-by-hop header
    - `Keep-Alive` - Hop-by-hop header
    - `Proxy-Authenticate` - Proxy-specific
    - `Proxy-Authorization` - Proxy-specific
    - `TE` - Hop-by-hop header
    - `Trailers` - Hop-by-hop header
    - `Upgrade` - Hop-by-hop header

## Testing Your Integration

When implementing a custom integration, ensure you test:

1. **Basic caching** - Request → Response → Cache → Retrieve
2. **Compressed responses** - gzip, deflate, brotli
3. **Chunked transfer encoding**
4. **Consumed vs. unconsumed streams**
5. **Various status codes** - 200, 304, 404, 500, etc.
6. **Different content types** - JSON, HTML, binary data
7. **Request metadata** - Custom Hishel extensions

## Example Integration Template

Here's a template to get started with a new library:
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
        # TODO: Extract method, url, headers from your library's request
        # TODO: Handle request stream/body if needed
        # TODO: Extract any Hishel metadata from extensions/extras
        pass
    
    elif isinstance(value, MyLibResponse):
        # TODO: Extract status code and headers
        # TODO: Remove hop-by-hop and encoding headers if needed
        # TODO: Handle stream consumption state
        # TODO: Create appropriate stream iterator
        pass
```

## Need Help?

If you're building an integration and encounter issues:

1. Check existing integrations in the Hishel codebase for reference
2. Open an issue on GitHub with your use case
3. Consider contributing your integration back to Hishel!

## Related Documentation

- [Storage Backends](../storage/) - Understanding where responses are cached
- [Cache Policies](../policies/) - How Hishel decides what to cache
- [API Reference](../api/) - Detailed model specifications