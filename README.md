# hishel

[![PyPI - Version](https://img.shields.io/pypi/v/hishel.svg)](https://pypi.org/project/hishel)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/hishel.svg)](https://pypi.org/project/hishel)

-----

**Hishel (հիշել, remember)** is a library that implements HTTP Caching for [HTTPX](https://github.com/encode/httpx) and [HTTP Core](https://github.com/encode/httpcore) libraries in accordance with **RFC 9111**, the most recent caching specification.

## Features

- 💾 Persistence: Responses are cached in the **persistent memory** for later use.
- 🤲 Compatibility: It is very simple to integrate with your **existing httpx client, transport, or httpcore pool.**
- 🤗 Easy to use: You continue to use the httpx and httpcore interfaces. **Can be integrated with no changes to the code.**
- 🧠 Smart: Attempts to clearly implement RFC 9111, understands `Vary`, `Etag`, `Last-Modified`,  `Cache-Control`, and `Expires` headers, and **handles response re-validation automatically**.

## QuickStart

Install `Hishel` using pip:
``` shell
$ pip install hishel
```

Let's begin with an example of a httpx client.

```python
import hishel

client = hishel.CacheClient()
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
            "Server",
            "nginx"
        ],
        [
            "Date",
            "Fri, 21 Jul 2023 14:23:50 GMT"
        ],
        [
            "Content-Length",
            "0"
        ],
        [
            "Connection",
            "keep-alive"
        ],
        [
            "Location",
            "https://httpbun.org"
        ],
        [
            "X-Powered-By",
            "httpbun/3c0dc05883dd9212ac38b04705037d50b02f2596"
        ]
    ],
    "content": "",
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

