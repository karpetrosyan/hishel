
<p align="center">
  <img alt="Hishel Logo" width="350" src="https://raw.githubusercontent.com/karpetrosyan/hishel/master/docs/static/Shelkopryad_350x250_yellow.png#gh-dark-mode-only">
  <img alt="Hishel Logo" width="350" src="https://raw.githubusercontent.com/karpetrosyan/hishel/master/docs/static/Shelkopryad_350x250_black.png#gh-light-mode-only">
</p>

<h1 align="center">Hishel</h1>

<p align="center">
  <strong>Elegant HTTP Caching for Python</strong>
</p>

<p align="center">
  <a href="https://pypi.org/project/hishel">
    <img src="https://img.shields.io/pypi/v/hishel.svg" alt="PyPI version">
  </a>
  <a href="https://pypi.org/project/hishel">
    <img src="https://img.shields.io/pypi/pyversions/hishel.svg" alt="Python versions">
  </a>
  <a href="https://github.com/karpetrosyan/hishel/blob/master/LICENSE">
    <img src="https://img.shields.io/pypi/l/hishel" alt="License">
  </a>
  <a href="https://coveralls.io/github/karpetrosyan/hishel">
    <img src="https://img.shields.io/coverallsCoverage/github/karpetrosyan/hishel" alt="Coverage">
  </a>
  <a href="https://static.pepy.tech/badge/hishel/month">
    <img src="https://static.pepy.tech/badge/hishel/month" alt="Downloads">
  </a>
</p>

---

**Hishel** (հիշել, *to remember* in Armenian) is a modern HTTP caching library for Python that implements [RFC 9111](https://www.rfc-editor.org/rfc/rfc9111.html) specifications. It provides seamless caching integration for popular HTTP clients with minimal code changes.

## ✨ Features

- 🎯 **RFC 9111 Compliant** - Fully compliant with the latest HTTP caching specification
- 🔌 **Easy Integration** - Drop-in support for HTTPX and Requests
- 💾 **Flexible Storage** - SQLite backend with more coming soon
- ⚡ **High Performance** - Efficient caching with minimal overhead
- 🔄 **Async & Sync** - Full support for both synchronous and asynchronous workflows
- 🎨 **Type Safe** - Fully typed with comprehensive type hints
- 🧪 **Well Tested** - Extensive test coverage and battle-tested
- 🎛️ **Configurable** - Fine-grained control over caching behavior
- 🌐 **Future Ready** - Designed for easy integration with any HTTP client/server

## 📦 Installation

```bash
pip install hishel
```

### Optional Dependencies

Install with specific HTTP client support:

```bash
pip install hishel[httpx]      # For HTTPX support
pip install hishel[requests]   # For Requests support
```

Or install both:

```bash
pip install hishel[httpx,requests]
```

## 🚀 Quick Start

### With HTTPX

**Synchronous:**

```python
from hishel.httpx import SyncCacheClient

client = SyncCacheClient()

# First request - fetches from origin
response = client.get("https://api.example.com/data")
print(response.extensions["hishel_from_cache"])  # False

# Second request - served from cache
response = client.get("https://api.example.com/data")
print(response.extensions["hishel_from_cache"])  # True
```

**Asynchronous:**

```python
from hishel.httpx import AsyncCacheClient

async with AsyncCacheClient() as client:
    # First request - fetches from origin
    response = await client.get("https://api.example.com/data")
    print(response.extensions["hishel_from_cache"])  # False
    
    # Second request - served from cache
    response = await client.get("https://api.example.com/data")
    print(response.extensions["hishel_from_cache"])  # True
```

### With Requests

```python
import requests
from hishel.requests import CacheAdapter

session = requests.Session()
session.mount("https://", CacheAdapter())
session.mount("http://", CacheAdapter())

# First request - fetches from origin
response = session.get("https://api.example.com/data")

# Second request - served from cache
response = session.get("https://api.example.com/data")
print(response.headers.get("X-Hishel-From-Cache"))  # "True"
```

## 🎛️ Advanced Configuration

### Custom Cache Options

```python
from hishel import CacheOptions
from hishel.httpx import SyncCacheClient

client = SyncCacheClient(
    cache_options=CacheOptions(
        shared=False,                              # Use as private cache (browser-like)
        supported_methods=["GET", "HEAD", "POST"], # Cache GET, HEAD, and POST
        allow_stale=True                           # Allow serving stale responses
    )
)
```

### Custom Storage Backend

```python
from hishel import SyncSqliteStorage
from hishel.httpx import SyncCacheClient

storage = SyncSqliteStorage(
    database_path="my_cache.db",
    default_ttl=7200.0,           # Cache entries expire after 2 hours
    refresh_ttl_on_access=True    # Reset TTL when accessing cached entries
)

client = SyncCacheClient(storage=storage)
```

## 🏗️ Architecture

Hishel uses a **sans-I/O state machine** architecture that separates HTTP caching logic from I/O operations:

- ✅ **Correct** - Fully RFC 9111 compliant
- ✅ **Testable** - Easy to test without network dependencies
- ✅ **Flexible** - Works with any HTTP client or server
- ✅ **Type Safe** - Clear state transitions with full type hints

## 🔮 Roadmap

While Hishel currently supports HTTPX and Requests, we're actively working on:

- 🎯 Additional HTTP client integrations
- 🎯 Server-side caching support
- 🎯 More storage backends
- 🎯 Advanced caching strategies
- 🎯 Performance optimizations

## 📚 Documentation

Comprehensive documentation is available at [https://hishel.com/dev](https://hishel.com/dev)

- [Getting Started](https://hishel.com)
- [HTTPX Integration](https://hishel.com/dev/integrations/httpx)
- [Requests Integration](https://hishel.com/dev/integrations/requests)
- [Storage Backends](https://hishel.com/dev/storages)
- [RFC 9111 Specification](https://hishel.com/dev/specification)

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request. For major changes, please open an issue first to discuss what you would like to change.

See our [Contributing Guide](https://hishel.com/dev/contributing) for more details.

## 📄 License

This project is licensed under the BSD-3-Clause License - see the [LICENSE](LICENSE) file for details.

## 💖 Support

If you find Hishel useful, please consider:

- ⭐ Starring the repository
- 🐛 Reporting bugs and issues
- 💡 Suggesting new features
- 📖 Improving documentation
- ☕ [Buying me a coffee](https://buymeacoffee.com/karpetrosyan)

## 🙏 Acknowledgments

Hishel is inspired by and builds upon the excellent work in the Python HTTP ecosystem, particularly:

- [HTTPX](https://github.com/encode/httpx) - A next-generation HTTP client for Python
- [Requests](https://github.com/psf/requests) - The classic HTTP library for Python
- [RFC 9111](https://www.rfc-editor.org/rfc/rfc9111.html) - HTTP Caching specification

---

<p align="center">
  <strong>Made with ❤️ by <a href="https://github.com/karpetrosyan">Kar Petrosyan</a></strong>
</p>

