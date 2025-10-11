---
icon: material/database
---

`Hishel` has beta storages that are meant to be the default in the future, and the reason is the limitations of the current storages.

Create an instance of a storage like this.

```python
from hishel.beta import SyncSqliteStorage, Request

storage = SyncSqliteStorage()
```

Create a new pair by calling the `create_pair` function, providing a key to group multiple pairs together, and the request you want to include in that pair.

```python

incomplete_pair = storage.create_pair(
    Request(
        method="GET",
        url="https://example.org"
    )
)
```

It returns an incomplete pair, which means you only have part of it (just the request).
Later, if you receive a response and want to complete the pair, you can call `add_response` like this.

```python
from hishel.beta import Response

complete_pair = storage.add_response(
    incomplete_pair.id,
    Response(
        status_code=200,
    ),
    "test_key",
)
```

Finally, get the grouped responses by calling the get_pairs function, which will return all the complete pairs stored under the particular key.

```python
pairs = storage.get_pairs("test_key")
```
