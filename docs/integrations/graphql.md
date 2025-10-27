---
icon: material/graphql
---

# GraphQL Integration

Hishel provides robust support for caching GraphQL queries through body-sensitive content caching. Since GraphQL typically uses POST requests with different query bodies to the same endpoint, standard URL-based caching won't work. Hishel solves this by including the request body in the cache key.

## Why Body-Sensitive Caching?

Traditional HTTP caching uses the URL as the cache key. However, GraphQL APIs typically:

- Use a single endpoint (e.g., `/graphql`)
- Send queries via POST requests with JSON bodies
- Have different queries/mutations that need separate cache entries

Hishel's body-sensitive caching creates unique cache keys based on the request body, allowing proper caching of GraphQL queries.

## Quick Start

### Per-Request Configuration

Enable body-based caching for specific GraphQL requests using the `X-Hishel-Body-Key` header:

```python
from hishel.httpx import SyncCacheClient

client = SyncCacheClient()

query = """
    query GetUser($userId: ID!) {
        user(id: $userId) {
            id
            name
            email
            avatar
        }
    }
"""

# First request - fetches from server
response = client.post(
    "https://api.example.com/graphql",
    json={
        "query": query,
        "variables": {"userId": "123"}
    },
    headers={"X-Hishel-Body-Key": "true"}
)

# Second request - served from cache
response = client.post(
    "https://api.example.com/graphql",
    json={
        "query": query,
        "variables": {"userId": "123"}
    },
    headers={"X-Hishel-Body-Key": "true"}
)

# Different variables - creates new cache entry
response = client.post(
    "https://api.example.com/graphql",
    json={
        "query": query,
        "variables": {"userId": "456"}
    },
    headers={"X-Hishel-Body-Key": "true"}
)
```

### Global Configuration

Enable body-based caching for all requests to simplify GraphQL API interactions:

```python
from hishel.httpx import SyncCacheClient

# All requests will use body in cache key
client = SyncCacheClient(use_body_key=True)

query = """
    query GetPosts($limit: Int!) {
        posts(limit: $limit) {
            id
            title
            content
        }
    }
"""

# No need to set headers - body caching is automatic
response = client.post(
    "https://api.example.com/graphql",
    json={
        "query": query,
        "variables": {"limit": 10}
    }
)
```

## Async Support

Hishel fully supports async GraphQL clients:

```python
from hishel.httpx import AsyncCacheClient

async def fetch_user_data():
    async with AsyncCacheClient(use_body_key=True) as client:
        query = """
            query GetUser($id: ID!) {
                user(id: $id) {
                    name
                    email
                    posts {
                        title
                        createdAt
                    }
                }
            }
        """
        
        response = await client.post(
            "https://api.example.com/graphql",
            json={
                "query": query,
                "variables": {"id": "user-123"}
            }
        )
        
        return response.json()
```

## Working with GraphQL Libraries

### GQL (gql) Library

The [gql](https://github.com/graphql-python/gql) library is a GraphQL client for Python that provides advanced features like query validation, automatic retries, and more. Hishel integrates seamlessly with gql through HTTPX transports.

#### Why Use Hishel with GQL?

- **Automatic Query Caching**: Cache identical GraphQL queries without manual implementation
- **Network Efficiency**: Reduce API calls and improve response times
- **Cost Savings**: Fewer requests to rate-limited or paid GraphQL APIs
- **Offline Support**: Serve cached responses when network is unavailable

#### Basic Integration

You can integrate Hishel with gql in two ways:

**Method 1: Using Cached HTTPX Client (Recommended)**

=== "Async"

    ```python
    import asyncio
    from gql import gql, Client
    from gql.transport.httpx import HTTPXAsyncTransport
    from hishel.httpx import AsyncCacheClient

    async def main():
        # Create a cached HTTPX client
        httpx_client = AsyncCacheClient(use_body_key=True)

        # Use it as transport for GQL
        transport = HTTPXAsyncTransport(
            url="https://api.example.com/graphql",
            client=httpx_client
        )

        async with Client(
            transport=transport,
            fetch_schema_from_transport=True
        ) as client:
            # Execute queries - automatic caching
            query = gql("""
                query GetCountries {
                    countries {
                        code
                        name
                        capital
                    }
                }
            """)

            result = await client.execute(query)
            print(result)

    asyncio.run(main())
    ```

=== "Sync"

    ```python
    from gql import gql, Client
    from gql.transport.httpx import HTTPXTransport
    from hishel.httpx import SyncCacheClient

    # Create a cached HTTPX client
    httpx_client = SyncCacheClient(use_body_key=True)

    # Use it as transport for GQL
    transport = HTTPXTransport(
        url="https://api.example.com/graphql",
        client=httpx_client
    )

    client = Client(transport=transport, fetch_schema_from_transport=True)

    # Execute queries - automatic caching
    query = gql("""
        query GetCountries {
            countries {
                code
                name
                capital
            }
        }
    """)

    result = client.execute(query)
    print(result)
    ```

**Method 2: Using CacheTransport (More Control)**

This approach gives you fine-grained control over the transport layer:

=== "Async"

    ```python
    import asyncio
    from gql import gql, Client
    from gql.transport.httpx import HTTPXAsyncTransport
    from httpx import AsyncHTTPTransport
    from hishel.httpx import AsyncCacheTransport
    from hishel import FilterPolicy

    async def main():
        # Create a caching transport
        transport = HTTPXAsyncTransport(
            url="https://countries.trevorblades.com/graphql",
            transport=AsyncCacheTransport(
                next_transport=AsyncHTTPTransport(),
                policy=FilterPolicy(),  # Customize caching policy as needed
            ),
        )

        # Create GQL client with caching transport
        async with Client(
            transport=transport,
            fetch_schema_from_transport=True,
        ) as session:
            # Execute query
            query = gql("""
                query getContinents {
                  continents {
                    code
                    name
                  }
                }
            """)

            # First execution - fetches from server
            result = await session.execute(query)
            print("First request:", result)

            # Second execution - served from cache
            result = await session.execute(query)
            print("Second request (cached):", result)

    asyncio.run(main())
    ```

=== "Sync"

    ```python
    from gql import gql, Client
    from gql.transport.httpx import HTTPXTransport
    from httpx import HTTPTransport
    from hishel.httpx import SyncCacheTransport
    from hishel import FilterPolicy

    # Create a caching transport
    transport = HTTPXTransport(
        url="https://countries.trevorblades.com/graphql",
        transport=SyncCacheTransport(
            next_transport=HTTPTransport(),
            use_body_key=True,  # Enable body-based caching for GraphQL
            policy=FilterPolicy()  # Customize caching policy as needed
        ),
    )

    # Create GQL client with caching transport
    with Client(
        transport=transport,
        fetch_schema_from_transport=True,
    ) as session:
        # Execute query
        query = gql("""
            query getContinents {
              continents {
                code
                name
              }
            }
        """)

        # First execution - fetches from server
        result = session.execute(query)
        print("First request:", result)

        # Second execution - served from cache
        result = session.execute(query)
        print("Second request (cached):", result)
    ```

#### Real-World Example: GitHub GraphQL API

Here's a complete example querying the GitHub GraphQL API with caching:

=== "Async"

    ```python
    import asyncio
    from gql import gql, Client
    from gql.transport.httpx import HTTPXAsyncTransport
    from hishel.httpx import AsyncCacheClient
    from hishel import AsyncSqliteStorage

    async def fetch_github_repos(username: str, token: str):
        # Create cached client with persistent storage
        client = AsyncCacheClient(
            use_body_key=True,
            storage=AsyncSqliteStorage(
                database_path="github_cache.db",
                default_ttl=3600.0  # Cache for 1 hour
            )
        )
        
        transport = HTTPXAsyncTransport(
            url="https://api.github.com/graphql",
            headers={"Authorization": f"Bearer {token}"},
            client=client
        )

        async with Client(
            transport=transport,
            fetch_schema_from_transport=False,  # GitHub doesn't support introspection
        ) as session:
            query = gql("""
                query GetUserRepos($username: String!) {
                  user(login: $username) {
                    repositories(first: 10, orderBy: {field: UPDATED_AT, direction: DESC}) {
                      nodes {
                        name
                        description
                        stargazerCount
                        url
                      }
                    }
                  }
                }
            """)

            result = await session.execute(
                query,
                variable_values={"username": username}
            )
            
            return result

    # Usage
    asyncio.run(fetch_github_repos("karpetrosyan", "your_token_here"))
    ```

=== "Sync"

    ```python
    from gql import gql, Client
    from gql.transport.httpx import HTTPXTransport
    from hishel.httpx import SyncCacheClient
    from hishel import SyncSqliteStorage

    def fetch_github_repos(username: str, token: str):
        # Create cached client with persistent storage
        client = SyncCacheClient(
            use_body_key=True,
            storage=SyncSqliteStorage(
                database_path="github_cache.db",
                default_ttl=3600.0  # Cache for 1 hour
            )
        )
        
        transport = HTTPXTransport(
            url="https://api.github.com/graphql",
            headers={"Authorization": f"Bearer {token}"},
            client=client
        )

        with Client(
            transport=transport,
            fetch_schema_from_transport=False,  # GitHub doesn't support introspection
        ) as session:
            query = gql("""
                query GetUserRepos($username: String!) {
                  user(login: $username) {
                    repositories(first: 10, orderBy: {field: UPDATED_AT, direction: DESC}) {
                      nodes {
                        name
                        description
                        stargazerCount
                        url
                      }
                    }
                  }
                }
            """)

            result = session.execute(
                query,
                variable_values={"username": username}
            )
            
            return result

    # Usage
    fetch_github_repos("karpetrosyan", "your_token_here")
    ```

## Best Practices

1. **Use `use_body_key=True`** for GraphQL clients to automatically enable body-based caching
2. **Don't cache mutations** - Use `Cache-Control: no-store` or disable caching for mutations
3. **Set appropriate TTLs** - GraphQL responses may vary in freshness requirements
4. **Monitor cache hit rates** - Check `hishel_from_cache` in response extensions
5. **Consider query complexity** - More complex queries benefit more from caching

## See Also

- [Request/Response Metadata](../metadata.md)
- [Storage Backends](../storages.md)
- [HTTPX Integration](httpx.md)
- [ASGI Integration](asgi.md)
