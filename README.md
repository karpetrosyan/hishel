<p align="center">
  <a href=""><img width="350" height="250" src="https://raw.githubusercontent.com/karpetrosyan/hishel/master/.github/logo.jpg" alt='HTTPX'></a>
</p>


<p align="center"><strong>Hishel</strong> <em>- An elegant HTTP Cache implementation for httpx and httpcore.</em></p>

<p align="center">

  <a href="https://pypi.org/project/hishel">
      <img src="https://img.shields.io/pypi/v/hishel.svg" alt="pypi">
  </a>

  <a href="https://img.shields.io/pypi/l/hishel">
      <img src="https://img.shields.io/pypi/l/hishel" alt="license">
  </a>

  <a href="https://img.shields.io/codecov/c/github/karpetrosyan/hishel">
      <img src="https://img.shields.io/codecov/c/github/karpetrosyan/hishel" alt="license">
  </a>

  <a href="https://static.pepy.tech/badge/hishel/month">
      <img src="https://static.pepy.tech/badge/hishel/month" alt="Downloads">
  </a>
</p>

-----

**Hishel (հիշել, remember)** is a library that implements HTTP Caching for [HTTPX](https://github.com/encode/httpx) and [HTTP Core](https://github.com/encode/httpcore) libraries in accordance with [**RFC 9111**](https://www.rfc-editor.org/rfc/rfc9111.html), the most recent caching specification.

## Features

- 💾 **Persistence**: Responses are cached in the [**persistent memory**](https://en.m.wikipedia.org/wiki/Persistent_memory) for later use.
- 🤲 **Compatibility**: It is completely compatible with your existing transports or connection pools, *whether they are default, custom, or provided by third-party libraries.*
- 🤗 **Easy to use**: You continue to use httpx while also enabling [web cache](https://en.wikipedia.org/wiki/Web_cache).
- 🧠 **Smart**: Attempts to clearly implement RFC 9111, understands `Vary`, `Etag`, `Last-Modified`,  `Cache-Control`, and `Expires` headers, and *handles response re-validation automatically*.
- ⚙️  **Configurable**: You have complete control over how the responses are stored and serialized.
- 📦 **From the package**:
    - Built-in support for [File system](https://en.wikipedia.org/wiki/File_system), [Redis](https://en.wikipedia.org/wiki/Redis), and [SQLite](https://en.wikipedia.org/wiki/SQLite) backends.
    - Built-in support for [JSON](https://en.wikipedia.org/wiki/JSON), [YAML](https://en.wikipedia.org/wiki/YAML), and [pickle](https://docs.python.org/3/library/pickle.html) serializers.
- 🚀 **Very fast**: Your requests will be even faster if there are *no IO operations*.

## Documentation
Go through the [Hishel documentation](https://hishel.com).

## QuickStart

Install `Hishel` using pip:
``` shell
$ pip install hishel
```

Let's begin with an example of a httpx client.

```python
import hishel

with hishel.CacheClient() as client:
    client.get("https://hishel.com")  # 0.4749558370003797s
    client.get("https://hishel.com")  # 0.002873589000046195s (~250x faster!)
```

or in asynchronous context

```python
import hishel

async with hishel.AsyncCacheClient() as client:
    await client.get("https://hishel.com")
    await client.get("https://hishel.com")  # takes from the cache
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

req = httpx.Request("GET", "https://hishel.com")

cache_transport.handle_request(req)
cache_transport.handle_request(req)  # takes from the cache
```

**Connection Pool** example:


```python
import httpcore
import hishel

pool = hishel.CacheConnectionPool(pool=httpcore.ConnectionPool())

pool.request("GET", "https://hishel.com")
pool.request("GET", "https://hishel.com")  # takes from the cache

```

## How and where are the responses saved?

The responses are stored by `Hishel` in [storages](https://karpetrosyan.github.io/hishel/userguide/#storages).
You have complete control over them; you can change storage or even write your own if necessary.


## Contributing

You can open the pull request by following these instructions if you want to improve `Hishel`. 💓

- Fork the project.
- Make change.
- Open the pull request.

