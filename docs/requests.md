# Requests Integration

Hishel adds HTTP caching to your [Requests](https://requests.readthedocs.io/) applications with a transport adapter.

## Installation

```bash
pip install "hishel[requests]"
```

## Quick Start

Mount `CacheAdapter` on a session:

```python
import requests
from hishel.requests import CacheAdapter

session = requests.Session()
adapter = CacheAdapter()
session.mount("https://", adapter)
session.mount("http://", adapter)

# First request - fetches from origin
session.get("https://api.example.com/data")

# Second request - served from cache
session.get("https://api.example.com/data")

session.close()
```

## Caching Modes

The two modes work the same as they do [with HTTPX](/httpx#caching-modes). By default, successful `GET` and `HEAD` responses are kept until the storage expires them, ignoring HTTP caching headers. To follow RFC 9111 instead, pass `rfc`:

```python
from hishel import CacheOptions
from hishel.requests import CacheAdapter

adapter = CacheAdapter(rfc=True)

# Or with options
adapter = CacheAdapter(rfc=CacheOptions(shared=False))
```

## Choosing a Storage

`CacheAdapter` uses a `SyncSqliteStorage` unless you pass another. See [Storages](/storages) for the options.

```python
from hishel import SyncSqliteStorage
from hishel.requests import CacheAdapter

adapter = CacheAdapter(storage=SyncSqliteStorage(default_ttl=3600))
```

The other arguments, `pool_connections`, `pool_maxsize`, `max_retries` and `pool_block`, are the same as on Requests' `HTTPAdapter`.

## Per-Request Expiry

Use the `X-Hishel-Ttl` and `X-Hishel-Tti` headers to override the storage's `default_ttl` and `default_tti` for a single request:

```python
import requests
from hishel.requests import CacheAdapter

session = requests.Session()
session.mount("https://", CacheAdapter())

# Expire this response after 1 hour, or after 5 minutes without being used
session.get("https://api.example.com/data", headers={"X-Hishel-Ttl": "3600", "X-Hishel-Tti": "300"})
```

The values are numbers of seconds, and fractions are fine. Anything else, including a negative number, raises a `ValueError` before the request is sent.

The adapter removes these headers, so they don't reach the server. They only do that where a `CacheAdapter` is mounted: a URL handled by another adapter sends them along like any other header.

They apply when a response is stored, so a request answered by an existing entry doesn't change when that entry expires. They can't remove a limit set on the storage.

## Per-Request Cache Key

Use the `X-Hishel-Key` header to replace the usual cache key, which is a hash of the method and URL in the default mode, and of the URL in RFC mode. For example, this keeps one user's entries apart from another's in the default mode:

```python
import requests
from hishel.requests import CacheAdapter

session = requests.Session()
session.mount("https://", CacheAdapter())

session.get("https://api.example.com/data", headers={"X-Hishel-Key": "user-42:data"})
```

An empty value raises a `ValueError`. Like the expiry headers, this one is removed by the adapter, and is only sent to the server if no `CacheAdapter` handles the URL.

- **Lookup and store:** the key is used as given, for finding entries and for storing a new one. A response stored under it isn't found by requests without it.
- **Shared keys:** in the default mode, requests with the same key and method get the same entry, whatever their URL. In RFC mode, an entry is only served to its own URL, so the other URLs store entries of their own under that key.
- **Methods:** `GET` and `HEAD` can share a key, but don't answer each other. A key doesn't make `POST` responses cacheable.
- **Invalidation:** in RFC mode, a request with an unsafe method, such as `POST`, removes the entries of its URL unless the response is an error. It only finds the entries under its own key, so it has to use the same key as the requests it should invalidate.
- **Redirects:** the key also applies to the requests that follow a redirect. In the default mode, the final response is stored under it, so the next request gets that response directly, without the redirect in its history.

## Different Settings for Different URLs

The caching mode and the storage can't be set per request. To use different ones for part of your traffic, mount another adapter on a more specific prefix:

```python
import requests
from hishel.requests import CacheAdapter

session = requests.Session()
session.mount("https://", CacheAdapter())
session.mount("https://api.example.com/", CacheAdapter(rfc=True))
```

To skip caching for a URL, mount a plain `requests.adapters.HTTPAdapter` on its prefix.

## Things to Know

- **Cookies:** a response from the server updates the session's cookies as usual. A response served from the cache doesn't, although its `Set-Cookie` header is still there.
- **Closing:** closing the session closes the adapter, which closes its storage too. Don't share a storage with a session that will close before you are done with it.
