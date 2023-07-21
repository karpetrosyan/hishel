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
```

If the response is cacheable according to **RFC 9111**, hishel will save it for later use, so the user only needs to change the client and the rest of the staff will be done automatically.

