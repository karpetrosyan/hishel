---
icon: material/database
---

# Storage Backends

Hishel provides storage backends for persisting HTTP request-response pairs. These storages are designed to work with the RFC 9111-compliant state machine and support both synchronous and asynchronous operations.

## Overview

Storage backends handle:

- ✅ **Pair Management**: Store incomplete and complete request-response pairs
- ✅ **Stream Handling**: Efficiently store and retrieve large request/response bodies
- ✅ **TTL Management**: Automatic expiration and cleanup of old entries
- ✅ **Soft Deletion**: Mark entries as deleted without immediate removal
- ✅ **Cache Keys**: Group multiple pairs under a single cache key

## Available Storages

Currently available:
- **SQLite Storage** - Persistent storage using SQLite database (async and sync)

Coming soon:

- Memory Storage - In-memory storage for testing and non-persistent caching
- any more...?
---

## SQLite Storage

SQLite storage provides persistent, file-based caching with excellent performance characteristics. It uses two tables: one for request-response pairs and another for streaming data chunks.

### Initialization

=== "Async"

    ```python
    from hishel.beta import AsyncSqliteStorage
    
    # Default configuration (creates hishel_cache.db in cache directory)
    storage = AsyncSqliteStorage()
    
    # Custom database path
    storage = AsyncSqliteStorage(database_path="my_cache.db")
    
    # With TTL configuration
    storage = AsyncSqliteStorage(
        default_ttl=3600.0,  # 1 hour default TTL
        refresh_ttl_on_access=True  # Reset TTL on access
    )
    
    # Custom connection (advanced usage)
    import anysqlite
    conn = await anysqlite.connect("custom_cache.db")
    storage = AsyncSqliteStorage(connection=conn)
    ```

=== "Sync"

    ```python
    from hishel.beta import SyncSqliteStorage
    
    # Default configuration (creates hishel_cache.db in cache directory)
    storage = SyncSqliteStorage()
    
    # Custom database path
    storage = SyncSqliteStorage(database_path="my_cache.db")
    
    # With TTL configuration
    storage = SyncSqliteStorage(
        default_ttl=3600.0,  # 1 hour default TTL
        refresh_ttl_on_access=True  # Reset TTL on access
    )
    
    # Custom connection (advanced usage)
    import sqlite3
    conn = sqlite3.connect("custom_cache.db")
    storage = SyncSqliteStorage(connection=conn)
    ```

### Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `connection` | `Connection | None` | `None` | Pre-existing database connection. If `None`, a new connection is created. |
| `database_path` | `str` | `"hishel_cache.db"` | Path to the SQLite database file (relative to cache directory). |
| `default_ttl` | `float | None` | `None` | Default time-to-live in seconds for cached entries. `None` means no expiration. |
| `refresh_ttl_on_access` | `bool` | `True` | Whether to reset the TTL when an entry is accessed. |

---

## Basic Usage

### Creating Pairs

A "pair" consists of an HTTP request and response. Storage operations start by creating an incomplete pair (request only), then adding the response later.

=== "Async"

    ```python
    from hishel.beta import AsyncSqliteStorage, Request, Headers
    
    storage = AsyncSqliteStorage()
    
    # Create incomplete pair with request
    incomplete_pair = await storage.create_pair(
        request=Request(
            method="GET",
            url="https://api.example.com/users",
            headers=Headers({"User-Agent": "MyApp/1.0"})
        )
    )
    
    # incomplete_pair has:
    # - id: UUID
    # - request: Request
    # - meta: PairMeta (created_at timestamp)
    
    print(f"Created pair with ID: {incomplete_pair.id}")
    ```

=== "Sync"

    ```python
    from hishel.beta import SyncSqliteStorage, Request, Headers
    
    storage = SyncSqliteStorage()
    
    # Create incomplete pair with request
    incomplete_pair = storage.create_pair(
        request=Request(
            method="GET",
            url="https://api.example.com/users",
            headers=Headers({"User-Agent": "MyApp/1.0"})
        )
    )
    
    # incomplete_pair has:
    # - id: UUID
    # - request: Request
    # - meta: PairMeta (created_at timestamp)
    
    print(f"Created pair with ID: {incomplete_pair.id}")
    ```

### Adding Responses

After receiving a response from the origin server, complete the pair by adding the response.

=== "Async"

    ```python
    from hishel.beta import Response, Headers
    
    # Add response to complete the pair
    complete_pair = await storage.add_response(
        pair_id=incomplete_pair.id,
        response=Response(
            status_code=200,
            headers=Headers({"Content-Type": "application/json"}),
            stream=...,  # Response body stream
        ),
        key="GET:https://api.example.com/users"  # Cache key
    )
    
    # complete_pair has:
    # - id: UUID
    # - request: Request
    # - response: Response
    # - cache_key: bytes
    # - meta: PairMeta
    
    print(f"Stored response with status {complete_pair.response.status_code}")
    ```

=== "Sync"

    ```python
    from hishel.beta import Response, Headers
    
    # Add response to complete the pair
    complete_pair = storage.add_response(
        pair_id=incomplete_pair.id,
        response=Response(
            status_code=200,
            headers=Headers({"Content-Type": "application/json"}),
            stream=...,  # Response body stream
        ),
        key="GET:https://api.example.com/users"  # Cache key
    )
    
    # complete_pair has:
    # - id: UUID
    # - request: Request
    # - response: Response
    # - cache_key: bytes
    # - meta: PairMeta
    
    print(f"Stored response with status {complete_pair.response.status_code}")
    ```

### Retrieving Cached Pairs

Retrieve all complete pairs associated with a cache key.

=== "Async"

    ```python
    # Get all pairs for a cache key
    cache_key = "GET:https://api.example.com/users"
    pairs = await storage.get_pairs(cache_key)
    
    # pairs is a list of CompletePair objects
    for pair in pairs:
        print(f"Cached response: {pair.response.status_code}")
        
        # Access request/response bodies through streams
        async for chunk in pair.request.aiter_stream():
            print(f"Request chunk: {chunk}")
        
        async for chunk in pair.response.aiter_stream():
            print(f"Response chunk: {chunk}")
    ```

=== "Sync"

    ```python
    # Get all pairs for a cache key
    cache_key = "GET:https://api.example.com/users"
    pairs = storage.get_pairs(cache_key)
    
    # pairs is a list of CompletePair objects
    for pair in pairs:
        print(f"Cached response: {pair.response.status_code}")
        
        # Access request/response bodies through streams
        for chunk in pair.request.iter_stream():
            print(f"Request chunk: {chunk}")
        
        for chunk in pair.response.iter_stream():
            print(f"Response chunk: {chunk}")
    ```

### Updating Pairs

Update an existing pair with new information.

=== "Async"

    ```python
    import time
    from dataclasses import replace
    
    # Option 1: Update with a new pair object
    updated_pair = replace(
        complete_pair,
        meta=replace(complete_pair.meta, created_at=time.time())
    )
    result = await storage.update_pair(complete_pair.id, updated_pair)
    
    # Option 2: Update using a callable
    def update_cache_key(pair):
        return replace(pair, cache_key=b"new_key")
    
    result = await storage.update_pair(complete_pair.id, update_cache_key)
    
    if result is None:
        print("Pair not found or is incomplete")
    ```

=== "Sync"

    ```python
    from dataclasses import replace
    
    # Option 1: Update with a new pair object
    updated_pair = replace(
        complete_pair,
        response=replace(complete_pair.response, status_code=304)
    )
    result = storage.update_pair(complete_pair.id, updated_pair)
    
    # Option 2: Update using a callable
    def update_cache_key(pair):
        return replace(pair, cache_key=b"new_key")
    
    result = storage.update_pair(complete_pair.id, update_cache_key)
    
    if result is None:
        print("Pair not found or is incomplete")
    ```

### Removing Pairs

Remove pairs from the cache (soft deletion - marked as deleted but not immediately removed).

=== "Async"

    ```python
    # Soft delete a pair
    await storage.remove(pair_id=complete_pair.id)
    
    # The pair is marked as deleted and will be removed during cleanup
    ```

=== "Sync"

    ```python
    # Soft delete a pair
    storage.remove(pair_id=complete_pair.id)
    
    # The pair is marked as deleted and will be removed during cleanup
    ```

---

## Complete Example

Here's a complete example showing the full lifecycle of cache storage:

=== "Async"

    ```python
    import uuid
    from hishel.beta import AsyncSqliteStorage, Request, Response, Headers
    from hishel._utils import make_async_iterator
    
    # Initialize storage
    storage = AsyncSqliteStorage(
        database_path="my_app_cache.db",
        default_ttl=3600.0  # 1 hour
    )
    
    # Create cache key
    cache_key = "GET:https://api.example.com/users"
    
    # Step 1: Create incomplete pair
    incomplete_pair = await storage.create_pair(
        request=Request(
            method="GET",
            url="https://api.example.com/users",
            stream=make_async_iterator([b"request body"]),
        )
    )
    
    # Consume request stream to store it
    async for chunk in incomplete_pair.request.aiter_stream():
        pass  # Storage automatically saves chunks
    
    # Step 2: Add response to complete the pair
    complete_pair = await storage.add_response(
        pair_id=incomplete_pair.id,
        response=Response(
            status_code=200,
            headers=Headers({"Content-Type": "application/json"}),
            stream=make_async_iterator([
                b'{"users": [',
                b'{"id": 1, "name": "Alice"},',
                b'{"id": 2, "name": "Bob"}',
                b']}',
            ]),
        ),
        key=cache_key,
    )
    
    # Consume response stream to store it
    async for chunk in complete_pair.response.aiter_stream():
        pass  # Storage automatically saves chunks
    
    # Step 3: Retrieve cached pairs
    cached_pairs = await storage.get_pairs(cache_key)
    
    print(f"Found {len(cached_pairs)} cached pair(s)")
    
    for pair in cached_pairs:
        print(f"Request: {pair.request.method} {pair.request.url}")
        print(f"Response: {pair.response.status_code}")
        
        # Read response body
        body_chunks = []
        async for chunk in pair.response.aiter_stream():
            body_chunks.append(chunk)
        body = b"".join(body_chunks)
        print(f"Body: {body.decode()}")
    
    # Step 4: Update pair if needed
    from dataclasses import replace
    
    updated_pair = replace(
        complete_pair,
        cache_key=b"updated_key"
    )
    await storage.update_pair(complete_pair.id, updated_pair)
    
    # Step 5: Remove pair when no longer needed
    await storage.remove(complete_pair.id)
    ```

=== "Sync"

    ```python
    import uuid
    from hishel.beta import SyncSqliteStorage, Request, Response, Headers
    from hishel._utils import make_iterator
    
    # Initialize storage
    storage = SyncSqliteStorage(
        database_path="my_app_cache.db",
        default_ttl=3600.0  # 1 hour
    )
    
    # Create cache key
    cache_key = "GET:https://api.example.com/users"
    
    # Step 1: Create incomplete pair
    incomplete_pair = storage.create_pair(
        request=Request(
            method="GET",
            url="https://api.example.com/users",
            stream=make_iterator([b"request body"]),
        )
    )
    
    # Consume request stream to store it
    for chunk in incomplete_pair.request.iter_stream():
        pass  # Storage automatically saves chunks
    
    # Step 2: Add response to complete the pair
    complete_pair = storage.add_response(
        pair_id=incomplete_pair.id,
        response=Response(
            status_code=200,
            headers=Headers({"Content-Type": "application/json"}),
            stream=make_iterator([
                b'{"users": [',
                b'{"id": 1, "name": "Alice"},',
                b'{"id": 2, "name": "Bob"}',
                b']}',
            ]),
        ),
        key=cache_key,
    )
    
    # Consume response stream to store it
    for chunk in complete_pair.response.iter_stream():
        pass  # Storage automatically saves chunks
    
    # Step 3: Retrieve cached pairs
    cached_pairs = storage.get_pairs(cache_key)
    
    print(f"Found {len(cached_pairs)} cached pair(s)")
    
    for pair in cached_pairs:
        print(f"Request: {pair.request.method} {pair.request.url}")
        print(f"Response: {pair.response.status_code}")
        
        # Read response body
        body_chunks = []
        for chunk in pair.response.iter_stream():
            body_chunks.append(chunk)
        body = b"".join(body_chunks)
        print(f"Body: {body.decode()}")
    
    # Step 4: Update pair if needed
    from dataclasses import replace
    
    updated_pair = replace(
        complete_pair,
        cache_key=b"updated_key"
    )
    storage.update_pair(complete_pair.id, updated_pair)
    
    # Step 5: Remove pair when no longer needed
    storage.remove(complete_pair.id)
    ```

---

## Advanced Topics

### Stream Handling

Hishel storages efficiently handle large request and response bodies using streams. Streams are automatically chunked and stored as you consume them.

**Important**: You must consume streams (iterate through them) for the data to be stored. Simply creating a pair with a stream doesn't store the stream data.

=== "Async"

    ```python
    # Create pair with streaming body
    incomplete_pair = await storage.create_pair(
        request=Request(
            method="POST",
            url="https://api.example.com/upload",
            stream=make_async_iterator([
                b"chunk1",
                b"chunk2",
                b"chunk3",
            ])
        )
    )
    
    # IMPORTANT: Consume the stream to store it
    async for chunk in incomplete_pair.request.aiter_stream():
        # Each chunk is stored as you iterate
        pass
    
    # Now the request stream is fully stored
    # You can retrieve it later:
    pairs = await storage.get_pairs(cache_key)
    async for chunk in pairs[0].request.aiter_stream():
        print(f"Chunk: {chunk}")
    ```

=== "Sync"

    ```python
    # Create pair with streaming body
    incomplete_pair = storage.create_pair(
        request=Request(
            method="POST",
            url="https://api.example.com/upload",
            stream=make_iterator([
                b"chunk1",
                b"chunk2",
                b"chunk3",
            ])
        )
    )
    
    # IMPORTANT: Consume the stream to store it
    for chunk in incomplete_pair.request.iter_stream():
        # Each chunk is stored as you iterate
        pass
    
    # Now the request stream is fully stored
    # You can retrieve it later:
    pairs = storage.get_pairs(cache_key)
    for chunk in pairs[0].request.iter_stream():
        print(f"Chunk: {chunk}")
    ```

### TTL and Expiration

Control how long cached entries remain valid:

=== "Async"

    ```python
    # Set default TTL for all entries
    storage = AsyncSqliteStorage(default_ttl=3600.0)  # 1 hour
    
    # Override TTL for specific requests using metadata
    incomplete_pair = await storage.create_pair(
        request=Request(
            method="GET",
            url="https://api.example.com/data",
            metadata={"hishel_ttl": 7200.0}  # 2 hours for this entry
        )
    )
    
    # Disable TTL refresh on access
    storage = AsyncSqliteStorage(
        default_ttl=3600.0,
        refresh_ttl_on_access=False  # TTL won't reset when accessed
    )
    ```

=== "Sync"

    ```python
    # Set default TTL for all entries
    storage = SyncSqliteStorage(default_ttl=3600.0)  # 1 hour
    
    # Override TTL for specific requests using metadata
    incomplete_pair = storage.create_pair(
        request=Request(
            method="GET",
            url="https://api.example.com/data",
            metadata={"hishel_ttl": 7200.0}  # 2 hours for this entry
        )
    )
    
    # Disable TTL refresh on access
    storage = SyncSqliteStorage(
        default_ttl=3600.0,
        refresh_ttl_on_access=False  # TTL won't reset when accessed
    )
    ```

### Cleanup and Maintenance

Storage automatically performs cleanup operations to remove expired and deleted entries. Cleanup runs periodically when storage operations are performed.

**Cleanup removes:**

- Expired entries (past their TTL)
- Entries marked as deleted for more than 7 days
- Incomplete pairs older than 1 hour (considered corrupted)
- Pairs with missing or incomplete streams

The cleanup process is automatic and doesn't require manual intervention.

### Custom Pair IDs

By default, pair IDs are auto-generated UUIDs. You can provide custom IDs if needed:

=== "Async"

    ```python
    import uuid
    
    # Provide custom UUID
    custom_id = uuid.uuid4()
    incomplete_pair = await storage.create_pair(
        request=Request(method="GET", url="https://api.example.com"),
        id=custom_id
    )
    
    assert incomplete_pair.id == custom_id
    ```

=== "Sync"

    ```python
    import uuid
    
    # Provide custom UUID
    custom_id = uuid.uuid4()
    incomplete_pair = storage.create_pair(
        request=Request(method="GET", url="https://api.example.com"),
        id=custom_id
    )
    
    assert incomplete_pair.id == custom_id
    ```

---

## Database Schema

For reference, here's the SQLite database schema used by the storage:

### `entries` Table
Stores request-response pair metadata.

| Column | Type | Description |
|--------|------|-------------|
| `id` | BLOB | Primary key - UUID of the pair |
| `cache_key` | BLOB | Cache key for grouping pairs (NULL for incomplete pairs) |
| `data` | BLOB | Serialized pair data (request, response, metadata) |
| `created_at` | REAL | Timestamp when the pair was created |
| `deleted_at` | REAL | Timestamp when soft deleted (NULL if not deleted) |

**Indexes:**
- `idx_entries_cache_key` - Fast lookups by cache key
- `idx_entries_deleted_at` - Efficient cleanup queries

### `streams` Table
Stores request and response body chunks.

| Column | Type | Description |
|--------|------|-------------|
| `entry_id` | BLOB | Foreign key to entries.id |
| `kind` | INTEGER | Stream type: 0 = request, 1 = response |
| `chunk_number` | INTEGER | Chunk sequence number (0, 1, 2, ... or -1 for completion marker) |
| `chunk_data` | BLOB | The actual chunk data |

**Primary Key:** `(entry_id, kind, chunk_number)`

**Special Values:**
- `chunk_number = -1` - Completion marker (empty data, signals end of stream)
- `kind = 0` - Request stream
- `kind = 1` - Response stream

---

## Integration with State Machine

Storage is designed to work seamlessly with Hishel's RFC 9111 state machine. Here's how they integrate:

=== "Async"

    ```python
    from hishel.beta import (
        create_idle_state,
        CacheMiss,
        FromCache,
        StoreAndUse,
        AsyncSqliteStorage,
        Request,
    )
    
    storage = AsyncSqliteStorage()
    
    # Get cache key for request
    cache_key = "GET:https://api.example.com/users"
    
    # Retrieve cached pairs
    cached_pairs = await storage.get_pairs(cache_key)
    
    # Start state machine
    state = create_idle_state("client")
    request = Request(method="GET", url="https://api.example.com/users")
    
    # Transition based on cached pairs
    next_state = state.next(request, cached_pairs)
    
    if isinstance(next_state, FromCache):
        # Use cached response
        response = next_state.pair.response
    
    elif isinstance(next_state, CacheMiss):
        # Fetch from origin and store
        origin_response = ...  # fetch from server
        
        # Create pair in storage
        incomplete_pair = await storage.create_pair(request)
        async for _ in incomplete_pair.request.aiter_stream():
            pass
        
        # Evaluate if we should store it
        storage_state = next_state.next(origin_response, incomplete_pair.id)
        
        if isinstance(storage_state, StoreAndUse):
            # Add response to storage
            complete_pair = await storage.add_response(
                pair_id=incomplete_pair.id,
                response=origin_response,
                key=cache_key,
            )
            async for _ in complete_pair.response.aiter_stream():
                pass
        
        response = origin_response
    ```

=== "Sync"

    ```python
    from hishel.beta import (
        create_idle_state,
        CacheMiss,
        FromCache,
        StoreAndUse,
        SyncSqliteStorage,
        Request,
    )
    
    storage = SyncSqliteStorage()
    
    # Get cache key for request
    cache_key = "GET:https://api.example.com/users"
    
    # Retrieve cached pairs
    cached_pairs = storage.get_pairs(cache_key)
    
    # Start state machine
    state = create_idle_state("client")
    request = Request(method="GET", url="https://api.example.com/users")
    
    # Transition based on cached pairs
    next_state = state.next(request, cached_pairs)
    
    if isinstance(next_state, FromCache):
        # Use cached response
        response = next_state.pair.response
    
    elif isinstance(next_state, CacheMiss):
        # Fetch from origin and store
        origin_response = ...  # fetch from server
        
        # Create pair in storage
        incomplete_pair = storage.create_pair(request)
        for _ in incomplete_pair.request.iter_stream():
            pass
        
        # Evaluate if we should store it
        storage_state = next_state.next(origin_response, incomplete_pair.id)
        
        if isinstance(storage_state, StoreAndUse):
            # Add response to storage
            complete_pair = storage.add_response(
                pair_id=incomplete_pair.id,
                response=origin_response,
                key=cache_key,
            )
            for _ in complete_pair.response.iter_stream():
                pass
        
        response = origin_response
    ```
