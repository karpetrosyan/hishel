# Zapros Integration (Recommended)

[Zapros](https://zapros.dev/) is a modern Python HTTP client developed by the same author as Hishel. It uses **Hishel as its native caching library** out of the box, providing the best integration experience with RFC 9111-compliant HTTP caching without any additional setup.

## Installation

```bash
pip install zapros[caching]
```

## Quick Start

::: code-group

```python [Sync]
from zapros import Client, CacheMiddleware, StdNetworkHandler

client = Client(handler=CacheMiddleware(StdNetworkHandler()))

response = client.get("https://api.example.com/data")
print(response.context.get("caching"))  # {'from_cache': False, ...}

response = client.get("https://api.example.com/data")
print(response.context.get("caching"))  # {'from_cache': True, ...}
```

```python [Async]
from zapros import AsyncClient, CacheMiddleware, AsyncStdNetworkHandler

client = AsyncClient(handler=CacheMiddleware(AsyncStdNetworkHandler()))

response = await client.get("https://api.example.com/data")
print(response.context.get("caching"))  # {'from_cache': False, ...}

response = await client.get("https://api.example.com/data")
print(response.context.get("caching"))  # {'from_cache': True, ...}
```

:::

## Learn More

For caching policies, storage options, per-request configuration, and more, see the [Zapros Caching Guide](https://zapros.dev/caching.html).
