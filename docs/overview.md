# Overview

Hishel is an HTTP caching library for both async and sync Python applications.

It caches in one of two modes:

- **By default**, it keeps successful `GET` and `HEAD` responses for as long as you configure, ignoring HTTP caching headers. This is the simplest way to avoid repeating requests from a backend.
- **In RFC mode**, it follows the HTTP caching specification ([RFC 9111](https://www.rfc-editor.org/rfc/rfc9111.html)), so servers decide what is cached and for how long.

Responses are stored in a [SQLite database or Redis](/storages), and bodies are streamed rather than loaded fully into memory.

RFC mode is built on a [Sans-IO core](/sans-io), which you can use to implement your own caching logic or to integrate Hishel with your library.

# Integrations

Hishel comes with integrations for these clients:

- [HTTPX and HTTPX2](/httpx)
- [Requests](/requests)

And for these servers, to cache your application's responses:

- [ASGI](/asgi)
- [FastAPI](/fastapi)

If you can't find an integration for your library or framework, you can implement one yourself using the [Sans-IO core](/sans-io).
