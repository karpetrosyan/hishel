---
icon: material/database
---

# Storage Backends

Hishel provides storage backends for persisting HTTP request-response pairs. These storages are designed to work with the RFC 9111-compliant state machine and support both synchronous and asynchronous operations.

## Overview

Storage backends handle:

- ✅ **Entry Management**: Store complete request-response pairs (entries)
- ✅ **Stream Handling**: Efficiently store and retrieve large response bodies
- ✅ **TTL Management**: Automatic expiration and cleanup of old entries
- ✅ **Soft Deletion**: Mark entries as deleted without immediate removal
- ✅ **Cache Keys**: Group multiple entries under a single cache key

## Available Storages

Currently available:
- **SQLite Storage** - Persistent storage using SQLite database (async and sync)

Coming soon:

- Memory Storage - In-memory storage for testing and non-persistent caching
- any more...?
---

## SQLite Storage

SQLite storage provides persistent, file-based caching with excellent performance characteristics. It uses two tables: one for request-response entries and another for streaming data chunks.

### Initialization

=== "Async"

    ```python
    from hishel import AsyncSqliteStorage
    
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
    from hishel import SyncSqliteStorage
    
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

### Creating Entries

An "entry" consists of an HTTP request and its corresponding response. With the new API, you create a complete entry in one operation by providing both the request and response together.

=== "Async"

    ```python
    from hishel import AsyncSqliteStorage, Request, Response, Headers
    from hishel._utils import make_async_iterator
    
    storage = AsyncSqliteStorage()
    
    # Create a complete entry with request and response
    entry = await storage.create_entry(
        request=Request(
            method="GET",
            url="https://api.example.com/users",
            headers=Headers({"User-Agent": "MyApp/1.0"})
        ),
        response=Response(
            status_code=200,
            headers=Headers({"Content-Type": "application/json"}),
            stream=make_async_iterator([b'{"users": []}'])
        ),
        key="GET:https://api.example.com/users"  # Cache key
    )
    
    # Consume the response stream to save it
    async for _ in entry.response.aiter_stream():
        pass
    
    # entry has:
    # - id: UUID
    # - request: Request
    # - response: Response
    # - cache_key: bytes
    # - meta: EntryMeta (created_at timestamp)

    print(f"Created entry with ID: {entry.id}")
    print(f"Response status: {entry.response.status_code}")
    ```

=== "Sync"

    ```python
    from hishel import SyncSqliteStorage, Request, Response, Headers
    from hishel._utils import make_iterator
    
    storage = SyncSqliteStorage()
    
    # Create a complete entry with request and response
    entry = storage.create_entry(
        request=Request(
            method="GET",
            url="https://api.example.com/users",
            headers=Headers({"User-Agent": "MyApp/1.0"})
        ),
        response=Response(
            status_code=200,
            headers=Headers({"Content-Type": "application/json"}),
            stream=make_iterator([b'{"users": []}'])
        ),
        key="GET:https://api.example.com/users"  # Cache key
    )
    
    # Consume the response stream to save it
    for _ in entry.response.iter_stream():
        pass
    
    # entry has:
    # - id: UUID
    # - request: Request
    # - response: Response
    # - cache_key: bytes
    # - meta: EntryMeta (created_at timestamp)
    
    print(f"Created entry with ID: {entry.id}")
    print(f"Response status: {entry.response.status_code}")
    ```

### Custom Entry IDs

You can optionally provide a custom UUID for the entry (useful for testing or specific use cases):

=== "Async"

    ```python
    import uuid
    
    entry = await storage.create_entry(
        request=request,
        response=response,
        key="my_cache_key",
        id_=uuid.UUID(int=0)  # Custom UUID
    )
    ```

=== "Sync"

    ```python
    import uuid
    
    entry = storage.create_entry(
        request=request,
        response=response,
        key="my_cache_key",
        id_=uuid.UUID(int=0)  # Custom UUID
    )
    ```

### Retrieving Cached Entries

Retrieve all entries associated with a cache key.

=== "Async"

    ```python
    # Get all entries for a cache key
    cache_key = "GET:https://api.example.com/users"
    entries = await storage.get_entries(cache_key)
    
    # entries is a list of Entry objects
    for entry in entries:
        print(f"Cached response: {entry.response.status_code}")
        
        # Access response body through stream
        async for chunk in entry.response.aiter_stream():
            print(f"Response chunk: {chunk}")
    ```

=== "Sync"

    ```python
    # Get all entries for a cache key
    cache_key = "GET:https://api.example.com/users"
    entries = storage.get_entries(cache_key)
    
    # entries is a list of Entry objects
    for entry in entries:
        print(f"Cached response: {entry.response.status_code}")
        
        # Access response body through stream
        for chunk in entry.response.iter_stream():
            print(f"Response chunk: {chunk}")
    ```

### Updating Entries

Update an existing entry with new information.

=== "Async"

    ```python
    import time
    from dataclasses import replace
    
    # Option 1: Update with a new entry object
    updated_entry = replace(
        entry,
        meta=replace(entry.meta, created_at=time.time())
    )
    result = await storage.update_entry(entry.id, updated_entry)
    
    # Option 2: Update using a callable
    def update_cache_key(entry):
        return replace(entry, cache_key=b"new_key")
    
    result = await storage.update_entry(entry.id, update_cache_key)
    
    if result is None:
        print("Entry not found")
    ```

=== "Sync"

    ```python
    from dataclasses import replace
    
    # Option 1: Update with a new entry object
    updated_entry = replace(
        entry,
        response=replace(entry.response, status_code=304)
    )
    result = storage.update_entry(entry.id, updated_entry)
    
    # Option 2: Update using a callable
    def update_cache_key(entry):
        return replace(entry, cache_key=b"new_key")
    
    result = storage.update_entry(entry.id, update_cache_key)
    
    if result is None:
        print("Entry not found")
    ```

### Removing Entries

Remove entries from the cache (soft deletion - marked as deleted but not immediately removed).

=== "Async"

    ```python
    # Soft delete an entry
    await storage.remove_entry(entry_id=entry.id)
    
    # The entry is marked as deleted and will be removed during cleanup
    ```

=== "Sync"

    ```python
    # Soft delete an entry
    storage.remove_entry(entry_id=entry.id)
    
    # The entry is marked as deleted and will be removed during cleanup
    ```

---

## Complete Example

Here's a complete example showing the full lifecycle of cache storage:

=== "Async"

    ```python
    import uuid
    from hishel import AsyncSqliteStorage, Request, Response, Headers
    from hishel._utils import make_async_iterator
    
    # Initialize storage
    storage = AsyncSqliteStorage(
        database_path="my_app_cache.db",
        default_ttl=3600.0  # 1 hour
    )
    
    # Create cache key
    cache_key = "GET:https://api.example.com/users"
    
    # Step 1: Create a complete entry with request and response
    entry = await storage.create_entry(
        request=Request(
            method="GET",
            url="https://api.example.com/users",
            stream=make_async_iterator([b"request body"]),
        ),
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
    
    # Consume streams to store them
    async for chunk in entry.request.aiter_stream():
        pass  # Storage automatically saves chunks
    
    async for chunk in entry.response.aiter_stream():
        pass  # Storage automatically saves chunks
    
    # Step 2: Retrieve cached entries
    cached_entries = await storage.get_entries(cache_key)
    
    print(f"Found {len(cached_entries)} cached entry/entries")
    
    for entry in cached_entries:
        print(f"Request: {entry.request.method} {entry.request.url}")
        print(f"Response: {entry.response.status_code}")
        
        # Read response body
        body_chunks = []
        async for chunk in entry.response.aiter_stream():
            body_chunks.append(chunk)
        body = b"".join(body_chunks)
        print(f"Body: {body.decode()}")
    
    # Step 3: Update entry if needed
    from dataclasses import replace
    
    updated_entry = replace(
        entry,
        cache_key=b"updated_key"
    )
    await storage.update_entry(entry.id, updated_entry)
    
    # Step 4: Remove entry when no longer needed
    await storage.remove_entry(entry.id)
    ```

=== "Sync"

    ```python
    import uuid
    from hishel import SyncSqliteStorage, Request, Response, Headers
    from hishel._utils import make_iterator
    
    # Initialize storage
    storage = SyncSqliteStorage(
        database_path="my_app_cache.db",
        default_ttl=3600.0  # 1 hour
    )
    
    # Create cache key
    cache_key = "GET:https://api.example.com/users"
    
    # Step 1: Create a complete entry with request and response
    entry = storage.create_entry(
        request=Request(
            method="GET",
            url="https://api.example.com/users",
            stream=make_iterator([b"request body"]),
        ),
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
    
    # Consume streams to store them
    for chunk in entry.request.iter_stream():
        pass  # Storage automatically saves chunks
    
    for chunk in entry.response.iter_stream():
        pass  # Storage automatically saves chunks
    
    # Step 2: Retrieve cached entries
    cached_entries = storage.get_entries(cache_key)
    
    print(f"Found {len(cached_entries)} cached entry/entries")
    
    for entry in cached_entries:
        print(f"Request: {entry.request.method} {entry.request.url}")
        print(f"Response: {entry.response.status_code}")
        
        # Read response body
        body_chunks = []
        for chunk in entry.response.iter_stream():
            body_chunks.append(chunk)
        body = b"".join(body_chunks)
        print(f"Body: {body.decode()}")
    
    # Step 3: Update entry if needed
    from dataclasses import replace
    
    updated_entry = replace(
        entry,
        cache_key=b"updated_key"
    )
    storage.update_entry(entry.id, updated_entry)
    
    # Step 4: Remove entry when no longer needed
    storage.remove_entry(entry.id)
    ```

---

## Advanced Topics

### Stream Handling

Hishel storages efficiently handle large request and response bodies using streams. Streams are automatically chunked and stored as you consume them.

**Important**: You must consume streams (iterate through them) for the data to be stored. Simply creating an entry with a stream doesn't store the stream data.

=== "Async"

    ```python
    # Create entry with streaming body
    entry = await storage.create_entry(
        request=Request(
            method="POST",
            url="https://api.example.com/upload",
            stream=make_async_iterator([
                b"chunk1",
                b"chunk2",
                b"chunk3",
            ])
        ),
        response=Response(
            status_code=200,
            headers=Headers({}),
            stream=make_async_iterator([b"OK"])
        ),
        key=cache_key
    )
    
    # IMPORTANT: Consume the streams to store them
    async for chunk in entry.request.aiter_stream():
        # Each chunk is stored as you iterate
        pass
    
    async for chunk in entry.response.aiter_stream():
        pass
    
    # Now the streams are fully stored
    # You can retrieve them later:
    entries = await storage.get_entries(cache_key)
    async for chunk in entries[0].request.aiter_stream():
        print(f"Chunk: {chunk}")
    ```

=== "Sync"

    ```python
    # Create entry with streaming body
    entry = storage.create_entry(
        request=Request(
            method="POST",
            url="https://api.example.com/upload",
            stream=make_iterator([
                b"chunk1",
                b"chunk2",
                b"chunk3",
            ])
        ),
        response=Response(
            status_code=200,
            headers=Headers({}),
            stream=make_iterator([b"OK"])
        ),
        key=cache_key
    )
    
    # IMPORTANT: Consume the streams to store them
    for chunk in entry.request.iter_stream():
        # Each chunk is stored as you iterate
        pass
    
    for chunk in entry.response.iter_stream():
        pass
    
    # Now the streams are fully stored
    # You can retrieve them later:
    entries = storage.get_entries(cache_key)
    for chunk in entries[0].request.iter_stream():
        print(f"Chunk: {chunk}")
    ```

### TTL and Expiration

Control how long cached entries remain valid:

=== "Async"

    ```python
    # Set default TTL for all entries
    storage = AsyncSqliteStorage(default_ttl=3600.0)  # 1 hour
    
    # Override TTL for specific requests using metadata
    entry = await storage.create_entry(
        request=Request(
            method="GET",
            url="https://api.example.com/data",
            metadata={"hishel_ttl": 7200.0}  # 2 hours for this entry
        ),
        response=response,
        key=cache_key
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
    entry = storage.create_entry(
        request=Request(
            method="GET",
            url="https://api.example.com/data",
            metadata={"hishel_ttl": 7200.0}  # 2 hours for this entry
        ),
        response=response,
        key=cache_key
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
- Entries with missing or incomplete streams

The cleanup process is automatic and doesn't require manual intervention.

### Custom Entry IDs

By default, entry IDs are auto-generated UUIDs. You can provide custom IDs if needed:

=== "Async"

    ```python
    import uuid
    
    # Provide custom UUID
    custom_id = uuid.uuid4()
    entry = await storage.create_entry(
        request=Request(method="GET", url="https://api.example.com"),
        response=response,
        key=cache_key,
        id_=custom_id
    )
    
    assert entry.id == custom_id
    ```

=== "Sync"

    ```python
    import uuid
    
    # Provide custom UUID
    custom_id = uuid.uuid4()
    entry = storage.create_entry(
        request=Request(method="GET", url="https://api.example.com"),
        response=response,
        key=cache_key,
        id_=custom_id
    )
    
    assert entry.id == custom_id
    ```

---

## Database Schema

For reference, here's the SQLite database schema used by the storage:

### `entries` Table
Stores request-response entry metadata.

| Column | Type | Description |
|--------|------|-------------|
| `id` | BLOB | Primary key - UUID of the entry |
| `cache_key` | BLOB | Cache key for grouping entries |
| `data` | BLOB | Serialized entry data (request, response, metadata) |
| `created_at` | REAL | Timestamp when the entry was created |
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
