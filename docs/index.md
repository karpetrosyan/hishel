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
- 🤲 Compatibility: It is completely compatible with your existing transports or connection pools, **whether they are default, custom, or provided by third-party libraries.**
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

or in asynchronous context

```python
import hishel

async with hishel.AsyncCacheClient() as client:
    await client.get("https://www.github.com")
    await client.get("https://www.github.com")  # takes from the cache
```

## HTTPX and HTTP Core

`Hishel` also supports the transports of `HTTPX` and the connection pools of `HTTP Core`.

`Hishel` respects existing **transports** and **connection pools** and can therefore work **on top of them**, making hishel a very **compatible and flexible library**.


**Transports** example:

``` python
import httpx
import hishel

transport = httpx.HTTPTransport()
cache_transport = hishel.CacheTransport(transport=transport)

req = httpx.Request("GET", "https://www.github.com")

cache_transport.handle_request(req)
cache_transport.handle_request(req)  # takes from the cache
```

**Connection Pool** example:


```python
import httpcore
import hishel

pool = hishel.CacheConnectionPool(pool=httpcore.ConnectionPool())

pool.request("GET", "https://www.github.com")
pool.request("GET", "https://www.github.com")  # takes from the cache

```

## How and where are the responses saved?

The responses are stored by `Hishel` in [storages](TODO). `Hishel` has a variety of built-in storage options, but the default storage is a [filesystem storage](TODO). You can switch the storage to another one that `Hishel` offers or, if necessary, write your own; for more information, see the storage documentation.


## Contributing

`Hishel` is a powerful tool, but it is also a new project with potential flaws, so we welcome contributions!

You can open the pull request by following these instructions if you want to improve `Hishel`. 💓

- Fork the project.
- Make change.
- Open the pull request.

