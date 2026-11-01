
<p align="center">
  <img alt="Hishel Logo" width="350" src="https://raw.githubusercontent.com/karpetrosyan/hishel/master/docs/static/Shelkopryad_350x250_yellow.png#gh-dark-mode-only">
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

**Hishel** (հիշել, *to remember* in Armenian) is a modern HTTP caching library for Python. It adds caching to [HTTPX](https://www.python-httpx.org/), [Requests](https://requests.readthedocs.io/) and ASGI applications with minimal code changes, either by your own limits or by following the [RFC 9111](https://www.rfc-editor.org/rfc/rfc9111.html) specification.

## ✨ Features

- 🎯 **RFC 9111 Mode** - Optionally follow the latest HTTP caching specification
- 🔌 **Easy Integration** - Drop-in support for HTTPX, HTTPX2, Requests, ASGI and FastAPI
- 💾 **Flexible Storage** - SQLite and Redis backends, or write your own
- ⚡ **High Performance** - Efficient caching with minimal overhead
- 🔄 **Async & Sync** - Full support for both synchronous and asynchronous workflows
- 🎨 **Type Safe** - Fully typed with comprehensive type hints
- 🧪 **Well Tested** - Extensive test coverage and battle-tested
- 🎛️ **Configurable** - TTL, TTI and size limits, with per-request overrides
- 💨 **Memory Efficient** - Streaming support prevents loading large payloads into memory

Documentation is available at: [https://hishel.com](https://hishel.com)