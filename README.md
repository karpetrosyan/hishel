<p align="center" class="logo">
    <div align="center">
        <picture>
            <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/karpetrosyan/hishel/master/docs/static/Shelkopryad_350x250_yellow.png">
            <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/karpetrosyan/hishel/master/docs/static/Shelkopryad_350x250_black.png">
            <img alt="Logo" src="https://raw.githubusercontent.com/karpetrosyan/hishel/master/docs/static/Shelkopryad_350x250_yellow.png">
        </picture>
    </div>
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

  <a href="https://github.com/karpetrosyan/hishel">
      <img src="https://img.shields.io/pypi/dm/hishel.svg" alt="Downloads">
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
    - Built-in support for [File system](https://en.wikipedia.org/wiki/File_system), [Redis](https://en.wikipedia.org/wiki/Redis), [SQLite](https://en.wikipedia.org/wiki/SQLite), and [AWS S3](https://aws.amazon.com/s3/) backends.
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

## Configurations

Configure when and how you want to store your responses.

```python
import hishel

# All the specification configs
controller = hishel.Controller(
        # Cache only GET and POST methods
        cacheable_methods=["GET", "POST"],

        # Cache only 200 status codes
        cacheable_status_codes=[200],

        # Use the stale response if there is a connection issue and the new response cannot be obtained.
        allow_stale=True,

        # First, revalidate the response and then utilize it.
        # If the response has not changed, do not download the
        # entire response data from the server; instead,
        # use the one you have because you know it has not been modified.
        always_revalidate=True,
)

# All the storage configs
storage = hishel.S3Storage(
        bucket_name="my_bucket_name", # store my cache files in the `my_bucket_name` bucket
        ttl=3600, # delete the response if it is in the cache for more than an hour
)
client = hishel.CacheClient(controller=controller, storage=storage)


# Ignore the fact that the server does not recommend you cache this request!
client.post(
        "https://example.com",
        extensions={"force_cache": True}
)


# Return a regular response if it is in the cache; else, return a 504 status code. DO NOT SEND A REQUEST!
client.post(
        "https://example.com",
        headers=[("Cache-Control", "only-if-cached")]
)


# Ignore cached responses and do not store incoming responses!
response = client.post(
        "https://example.com",
        extensions={"cache_disabled": True}
)
```

## How and where are the responses saved?

The responses are stored by `Hishel` in [storages](https://hishel.com/userguide/#storages).
You have complete control over them; you can change storage or even write your own if necessary.


## Support the project

You can support the project by simply leaving a GitHub star ⭐ or by [contributing](https://hishel.com/contributing/).
Help us grow and continue developing good software for you ❤️

