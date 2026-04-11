
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

**Hishel** (հիշել, *to remember* in Armenian) is a modern HTTP caching library for Python that implements [RFC 9111](https://www.rfc-editor.org/rfc/rfc9111.html) specifications. It provides seamless caching integration for popular HTTP clients with minimal code changes.

## ✨ Features

- 🎯 **RFC 9111 Compliant** - Fully compliant with the latest HTTP caching specification
- 🔌 **Easy Integration** - Drop-in support for HTTPX, Requests, ASGI, FastAPI, and BlackSheep
- 💾 **Flexible Storage** - SQLite backend with more coming soon
- ⚡ **High Performance** - Efficient caching with minimal overhead
- 🔄 **Async & Sync** - Full support for both synchronous and asynchronous workflows
- 🎨 **Type Safe** - Fully typed with comprehensive type hints
- 🧪 **Well Tested** - Extensive test coverage and battle-tested
- 🎛️ **Configurable** - Fine-grained control over caching behavior with flexible policies
- 💨 **Memory Efficient** - Streaming support prevents loading large payloads into memory
- 🌐 **Universal** - Works with any ASGI application (Starlette, Litestar, BlackSheep, etc.)
- 🎯 **GraphQL Support** - Cache GraphQL queries with body-sensitive content caching

Documentation is available at: [https://hishel.com](https://hishel.com)