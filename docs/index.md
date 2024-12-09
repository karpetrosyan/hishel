<p align="center" class="logo">
    <div align="center">
        <a href=""><img width="350" height="250" src="https://raw.githubusercontent.com/karpetrosyan/hishel/master/docs/static/Shelkopryad_350x250_yellow.png#only-dark" alt='HTTPX'></a>
        <a href=""><img width="350" height="250" src="https://raw.githubusercontent.com/karpetrosyan/hishel/master/docs/static/Shelkopryad_350x250_black.png#only-light" alt='HTTPX'></a>
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

  <a href="https://static.pepy.tech/badge/hishel/month">
      <img src="https://static.pepy.tech/badge/hishel/month" alt="Downloads">
  </a>
</p>

-----

**Hishel (հիշել, remember)** is a library that implements HTTP Caching for [HTTPX](https://github.com/encode/httpx) and [HTTP Core](https://github.com/encode/httpcore) libraries in accordance with [**RFC 9111**](https://www.rfc-editor.org/rfc/rfc9111.html), the most recent caching specification.

## Features

- :floppy_disk: **Persistence**: Responses are cached in the [**persistent memory**](https://en.m.wikipedia.org/wiki/Persistent_memory) for later use.
- :handshake: **Compatibility**: It is completely compatible with your existing transports or connection pools, *whether they are default, custom, or provided by third-party libraries.*
- :hugging: **Easy to use**: You continue to use httpx while also enabling [web cache](https://en.wikipedia.org/wiki/Web_cache).
- :brain: **Smart**: Attempts to clearly implement RFC 9111, understands `Vary`, `Etag`, `Last-Modified`,  `Cache-Control`, and `Expires` headers, and *handles response re-validation automatically*.
- :gear: **Configurable**: You have complete control over how the responses are stored and serialized.
- :package: **From the package**:
    - Built-in support for [File system](https://en.wikipedia.org/wiki/File_system) :file_folder: , [Redis](https://en.wikipedia.org/wiki/Redis) :simple-redis:, [SQLite](https://en.wikipedia.org/wiki/SQLite) :simple-sqlite: , and [AWS S3](https://aws.amazon.com/s3/) :material-aws: backends.
    - Built-in support for [JSON](https://en.wikipedia.org/wiki/JSON) :simple-json: , [YAML](https://en.wikipedia.org/wiki/YAML) :simple-yaml:, and [pickle](https://docs.python.org/3/library/pickle.html) serializers.
- :rocket: **Very fast**: Your requests will be even faster if there are *no IO operations*.

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

## Support the project

You can support the project by simply leaving a GitHub star ⭐ or by [contributing](https://hishel.com/contributing/).
Help us grow and continue developing good software for you ❤️

