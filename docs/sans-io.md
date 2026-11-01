# Sans-IO

Hishel's RFC 9111 mode is built on a pure-Python state machine for HTTP caching. It does no I/O itself, so you can use it to integrate Hishel with any HTTP library.

The state machine tells you:

- what action to take next
- what to feed the state machine to transition to the next state
- what the current state indicates

You should not manually create a state, except for the initial state, which is called `IdleClient`.

Create your first state:

```python
from hishel import CacheOptions, IdleClient

state = IdleClient(options=CacheOptions())
```

Each state has a `next` method with the appropriate signature, returning another state, fully typed, and you can use it to move the state machine forward:

```python
from hishel import CacheOptions, IdleClient, Request

state = IdleClient(options=CacheOptions())
request = Request(method="GET", url="https://api.example.com/data")
next_state = state.next(request, associated_entries=[])
```

Here `next_state` will have a type of `CacheMiss`, `FromCache` or `NeedRevalidation`, each with its own properties and its own signature for the `next` method.

## States

What to do in each state:

- `IdleClient`: Look up the entries for the request, and call `next(request, entries)`.
- `CacheMiss`: Send `state.request` to the server, and call `next(response)`.
- `NeedRevalidation`: Send `state.request`, which includes the conditional headers, and call `next(response)`.
- `NeedToBeUpdated`: Save the headers of each entry in `state.updating_entries`, and call `next()`.
- `InvalidateEntries`: Remove each entry in `state.entry_ids`, and call `next()`.
- `StoreAndUse`: Store `state.response`, and return the stored response. **Final.**
- `CouldNotBeStored`: Return `state.response`. **Final.**
- `FromCache`: Return `state.entry.response`. **Final.**

## Writing an Integration

Here is the whole loop, using a storage and any `send` function that gets a response from the server:

```python
import hashlib
from typing import Callable

from hishel import (
    AnyState,
    CacheMiss,
    CacheOptions,
    CouldNotBeStored,
    FromCache,
    IdleClient,
    InvalidateEntries,
    NeedRevalidation,
    NeedToBeUpdated,
    Request,
    Response,
    StoreAndUse,
    SyncBaseStorage,
)


def handle_request(
    request: Request,
    send: Callable[[Request], Response],
    storage: SyncBaseStorage,
    options: CacheOptions,
) -> Response:
    # The key is the same for all methods, so that an unsafe request finds the entries it invalidates.
    key = hashlib.sha256(request.url.encode()).hexdigest()
    state: AnyState = IdleClient(options=options)

    while True:
        if isinstance(state, IdleClient):
            state = state.next(request, storage.get_entries(key))
        elif isinstance(state, (CacheMiss, NeedRevalidation)):
            state = state.next(send(state.request))
        elif isinstance(state, StoreAndUse):
            return storage.create_entry(request, state.response, key).response
        elif isinstance(state, CouldNotBeStored):
            return state.response
        elif isinstance(state, FromCache):
            return state.entry.response
        elif isinstance(state, NeedToBeUpdated):
            for entry in state.updating_entries:
                storage.update_headers(entry.id, entry.response.headers)
            state = state.next()
        elif isinstance(state, InvalidateEntries):
            for entry_id in state.entry_ids:
                storage.remove_entry(entry_id)
            state = state.next()
```

A stored response is only saved once its stream has been read to the end, so make sure whoever receives it reads the whole body.

The built-in integrations use this same loop, from the private modules `hishel._sync_rfc` and `hishel._async_rfc`.
