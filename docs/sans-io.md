# Sans-IO

Hishel includes a pure-Python, fully RFC-compliant state machine for HTTP caching (RFC 9111).

The main thing you should know is that Hishel provides a pure-python state machine that tells you:

- what action to take next
- what to feed the state machine to transition to the next state
- what the current state indicates

You should not manually create a state, except for the initial state, which is called `IdleClient`.

Create your first state:

```python
from hishel import IdleClient

state = IdleClient()
```

Each state has `next` method with the appropriate signature, returning another State, fully typed, and you can use it to move the state machine forward:

```python
from hishel import IdleClient, Request

state = IdleClient()
request = Request(...)
next_state = state.next(request, associated_entries=[])
```

Here the next_state will have a type of `CacheMiss`, `FromCache` and `NeedRevalidation` each with it's own properties and own signature for the `next` method.
