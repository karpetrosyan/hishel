<p align="center">
  <a href=""><img width="350" height="250" src="https://raw.githubusercontent.com/karosis88/hishel/master/.github/logo.jpg" alt='HTTPX'></a>
</p>


<p align="center"><strong>Hishel</strong> <em>- An elegant HTTP Cache implementation for httpx and httpcore.</em></p>


[![PyPI - Version](https://img.shields.io/pypi/v/hishel.svg)](https://pypi.org/project/hishel)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/hishel.svg)](https://pypi.org/project/hishel)
![PyPI - License](https://img.shields.io/pypi/l/hishel)
![Codecov](https://img.shields.io/codecov/c/github/karosis88/hishel)


-----

**Hishel (հիշել, remember)** is a library that implements HTTP Caching for [HTTPX](https://github.com/encode/httpx) and [HTTP Core](https://github.com/encode/httpcore) libraries in accordance with **RFC 9111**, the most recent caching specification.

## Features

- 💾 Persistence: Responses are cached in the [**persistent memory**](https://en.m.wikipedia.org/wiki/Persistent_memory) for later use.
- 🤲 Compatibility: It is very simple to integrate with your **existing httpx client, transport, or httpcore pool.**
- 🤗 Easy to use: You continue to use the httpx and httpcore interfaces. **Can be integrated with no changes to the code.**
- 🧠 Smart: Attempts to clearly implement RFC 9111, understands `Vary`, `Etag`, `Last-Modified`,  `Cache-Control`, and `Expires` headers, and **handles response re-validation automatically**.
- ⚙️ Configurable: You can specify the **backend** where the responses should be stored, the **serializer**, and you can write your own **backends and serializers**. You can also specify which parts of RFC 9111 **should be ignored and which should not**, for example, you can explicitly disable stale responses for your safety or enable re-validation for each response before using it. 
- 🚀 Very fast: When **IO is not required**, your requests are even faster.


## QuickStart

Install `Hishel` using pip:
``` shell
$ pip install hishel
```

Let's begin with an example of a httpx client.

```python
import hishel

with hishel.CacheClient() as client:
    client.get("https://www.github.com")
    client.get("https://www.github.com")  # takes from the cache (very fast!)
```

If the response is cacheable according to **RFC 9111**, hishel will save it for later use, so the user only needs to change the client and the rest of the staff will be done automatically.

By default, Hishel stores responses in the **./cache/hishel** directory, but this behavior can be overridden by explicitly specifying storage.

If we look, we can see that a new file was created in that directory. This is our serialized response. Hishel uses the json serializer by default, but we can explicitly set the other supported serializers, such as **YAML** and **Pickle** serializers.

This is how the file looks.

``` json
{
    "status": 301,
    "headers": [
        [
            "Location",
            "http://www.google.com/"
        ],
        [
            "Content-Type",
            "text/html; charset=UTF-8"
        ],
        [
            "Content-Security-Policy-Report-Only",
            "object-src 'none';base-uri 'self';script-src 'nonce-Ifk03ScgVPq-s5nrobBQVA' 'strict-dynamic' 'report-sample' 'unsafe-eval' 'unsafe-inline' https: http:;report-uri https://csp.withgoogle.com/csp/gws/other-hp"
        ],
        [
            "Date",
            "Tue, 25 Jul 2023 11:39:56 GMT"
        ],
        [
            "Expires",
            "Thu, 24 Aug 2023 11:39:56 GMT"
        ],
        [
            "Cache-Control",
            "public, max-age=2592000"
        ],
        [
            "Server",
            "gws"
        ],
        [
            "Content-Length",
            "219"
        ],
        [
            "X-XSS-Protection",
            "0"
        ],
        [
            "X-Frame-Options",
            "SAMEORIGIN"
        ]
    ],
    "content": "PEhUTUw+PEhFQUQ+PG1ldGEgaHR0cC1lcXVpdj0iY29udGVudC10eXBlIiBjb250ZW50PSJ0ZXh0L2h0bWw7Y2hhcnNldD11dGYtOCI+CjxUSVRMRT4zMDEgTW92ZWQ8L1RJVExFPjwvSEVBRD48Qk9EWT4KPEgxPjMwMSBNb3ZlZDwvSDE+ClRoZSBkb2N1bWVudCBoYXMgbW92ZWQKPEEgSFJFRj0iaHR0cDovL3d3dy5nb29nbGUuY29tLyI+aGVyZTwvQT4uDQo8L0JPRFk+PC9IVE1MPg0K",
    "extensions": {
        "http_version": "HTTP/1.1",
        "reason_phrase": "Moved Permanently"
    }
}
```

There is all the information required to rebuild the response, including the content value encoded in base64.

Hishel also works well with httpcore, and you can make your httpcore connection pools cacheable with a single line of code.

Your existing code
``` python
from httpcore import ConnectionPool

pool = ConnectionPool()

...
```

Adding HTTP caching to your program will make it much faster and more efficient.
``` python
import hishel
from httpcore import ConnectionPool

pool = ConnectionPool()
pool = hishel.CacheConnectionPool(pool=pool)
...
```

As you can see, it is **extremely simple to integrate**. 

Because `Hishel` respects your custom transports and connection pools, it requires the real **ConnectionPool** and the real **HTTPTransport** to work on top of it.

**Transports** example:

``` python
import httpx
import hishel

transport = httpx.HTTPTransport()
cache_transport = hishel.CacheTransport(transport=transport)

req = httpx.Request("GET",
                    "https://google.com")

cache_transport.handle_request(req)
cache_transport.handle_request(req)
```
