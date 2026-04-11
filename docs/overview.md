# Overview

Hishel is a library that provides HTTP caching for both async and sync Python applications and for both clients and servers.
With Hishel you can easily cache either fully respecting the HTTP caching specification (RFC 9111) which browsers use by default, or you can cache by your own rules.

Hishel comes with a backend for storing/retrieving cached responses in a SQLite database, but it was built around fully Sans-IO core which you can use to implement your own caching logic or to integrate it with your library.


# Integrations

Hishel comes with a some integrations for popular HTTP libraries, currently supporting:

- [httpx](https://www.python-httpx.org/) (client)
- [requests](https://docs.python-requests.org/) (client)
- [FastAPI](https://fastapi.tiangolo.com/) (server)
- [BlackSheep](https://www.blacksheep.rest/) (server)

We also have an ASGI middleware you can use with any ASGI framework.

If you can't find an integration for your library/framework, you can easly implement it yourself, looking at the existing ones as examples or reading the documentation for the Sans-IO core.