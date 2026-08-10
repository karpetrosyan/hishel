"""
BDD-style DSL for the RFC 9111 spec tests.

`CacheScenario` plays the role of a cache client with an in-memory storage
(`scenario.entries`), and `Exchange` drives one client request through the
whole state machine, mirroring the production loop in
`hishel._async_cache.AsyncCacheClient._handle_request_respecting_spec`
(src/hishel/_async_cache.py) handler-for-handler, minus I/O:

- `CacheMiss` / `NeedRevalidation` pause the exchange until the test feeds an
  origin response via `.responds(...)`.
- `StoreAndUse` appends a new entry built from the *original* client request
  (like `_handle_store_and_use`).
- `NeedToBeUpdated` replaces the stored entries' response headers only
  (like `_handle_update`).
- `InvalidateEntries` removes entries from the scenario storage
  (like `_handle_invalidate_entries`).

Unlike production, entries are NOT pre-filtered by cache key before being
passed to `IdleClient.next` — the whole entry list is handed over so tests
exercise `IdleClient`'s own URL/method hard conditions.

Assertion helpers check the resulting state *and* the full metadata-flag
triple (`hishel_stored`, `hishel_from_cache`, `hishel_revalidated`) in one
call. `assert_stored`/`assert_not_stored` read the flags from the exact
`Response` object fed via `.responds(...)`, preserving the guarantee that the
machine stamps metadata onto the caller's object.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Union

from hishel import Entry, EntryMeta, Request, Response
from hishel._core._headers import Headers
from hishel._core._spec import (
    AnyState,
    CacheMiss,
    CacheOptions,
    CouldNotBeStored,
    FromCache,
    IdleClient,
    InvalidateEntries,
    NeedRevalidation,
    NeedToBeUpdated,
    StoreAndUse,
)

DEFAULT_URL = "https://example.com/resource"


def http_date(seconds_ago: int = 0) -> str:
    """An HTTP-date string `seconds_ago` seconds in the past (negative = future)."""
    value = datetime.utcnow() - timedelta(seconds=seconds_ago)
    return value.strftime("%a, %d %b %Y %H:%M:%S GMT")


def build_request(
    method: str = "GET",
    url: str = DEFAULT_URL,
    headers: Optional[Dict[str, str]] = None,
    cache_control: Optional[str] = None,
) -> Request:
    final_headers = dict(headers or {})
    if cache_control is not None:
        final_headers["cache-control"] = cache_control
    return Request(method=method, url=url, headers=Headers(final_headers), metadata={})


def build_response(
    status: int = 200,
    *,
    headers: Optional[Dict[str, str]] = None,
    cache_control: Optional[str] = None,
    max_age: Optional[int] = None,
    s_maxage: Optional[int] = None,
    etag: Optional[str] = None,
    last_modified: Optional[str] = None,
    expires_in: Optional[int] = None,
    vary: Optional[str] = None,
    age_seconds: int = 0,
    with_date: bool = True,
) -> Response:
    """
    Build a Response from RFC-vocabulary keywords.

    `cache_control`, `max_age` and `s_maxage` are comma-merged into a single
    Cache-Control value (after any `headers["cache-control"]`). A `date`
    header is synthesized `age_seconds` in the past unless one is given
    explicitly or `with_date=False`.
    """
    final_headers = dict(headers or {})
    directives = [final_headers.pop("cache-control", None), cache_control]
    if max_age is not None:
        directives.append(f"max-age={max_age}")
    if s_maxage is not None:
        directives.append(f"s-maxage={s_maxage}")
    merged = ", ".join(directive for directive in directives if directive)
    if merged:
        final_headers["cache-control"] = merged
    if etag is not None:
        final_headers["etag"] = etag
    if last_modified is not None:
        final_headers["last-modified"] = last_modified
    if expires_in is not None:
        final_headers["expires"] = http_date(-expires_in)
    if vary is not None:
        final_headers["vary"] = vary
    if with_date:
        final_headers.setdefault("date", http_date(age_seconds))
    return Response(status_code=status, headers=Headers(final_headers), metadata={})


def build_entry(
    request: Optional[Request] = None,
    response: Optional[Response] = None,
    entry_id: Optional[uuid.UUID] = None,
) -> Entry:
    request = request or build_request()
    return Entry(
        id=entry_id or uuid.uuid4(),
        request=request,
        meta=EntryMeta(),
        response=response or build_response(),
        cache_key=request.url.encode(),
    )


def _assert_flags(response: Response, *, from_cache: bool, stored: bool, revalidated: bool) -> None:
    assert response.metadata.get("hishel_from_cache") is from_cache, (
        f"hishel_from_cache is {response.metadata.get('hishel_from_cache')!r}, expected {from_cache}"
    )
    assert response.metadata.get("hishel_stored") is stored, (
        f"hishel_stored is {response.metadata.get('hishel_stored')!r}, expected {stored}"
    )
    assert response.metadata.get("hishel_revalidated") is revalidated, (
        f"hishel_revalidated is {response.metadata.get('hishel_revalidated')!r}, expected {revalidated}"
    )


class CacheScenario:
    """A cache with in-memory storage; the Given/When entry point of every test."""

    def __init__(self, options: Optional[CacheOptions] = None, **option_kwargs: Any) -> None:
        self.options = options or CacheOptions(**option_kwargs)
        self.entries: list[Entry] = []

    def get(
        self,
        url: str = DEFAULT_URL,
        *,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        cache_control: Optional[str] = None,
    ) -> Exchange:
        return Exchange(self, build_request(method=method, url=url, headers=headers, cache_control=cache_control))

    def seed(
        self,
        request: Union[Request, Dict[str, Any], None] = None,
        response: Union[Response, Dict[str, Any], None] = None,
    ) -> Entry:
        """Append a stored entry directly, bypassing the machine (dicts go to the builders)."""
        if isinstance(request, dict):
            request = build_request(**request)
        if isinstance(response, dict):
            response = build_response(**response)
        entry = build_entry(request=request, response=response)
        self.entries.append(entry)
        return entry

    def entries_for(self, url: str = DEFAULT_URL) -> list[Entry]:
        return [entry for entry in self.entries if entry.request.url == url]

    def entry_for(self, url: str = DEFAULT_URL) -> Entry:
        matching = self.entries_for(url)
        assert len(matching) == 1, f"expected exactly one stored entry for {url}, found {len(matching)}"
        return matching[0]

    def _replace_headers(self, entry_id: uuid.UUID, headers: Headers) -> None:
        self.entries = [
            replace(entry, response=replace(entry.response, headers=headers)) if entry.id == entry_id else entry
            for entry in self.entries
        ]


class Exchange:
    """One client request driven through the state machine until it pauses or resolves."""

    def __init__(self, scenario: CacheScenario, request: Request) -> None:
        self._scenario = scenario
        self.request = request
        self.sent_request: Optional[Request] = None
        self.origin_responses: list[Response] = []
        self.removed_entry_ids: list[uuid.UUID] = []
        self.result: Union[FromCache, StoreAndUse, CouldNotBeStored, None] = None
        self._pending: Union[CacheMiss, NeedRevalidation, None] = None
        self._advance(IdleClient(options=scenario.options).next(request, list(scenario.entries)))

    @property
    def pending(self) -> bool:
        """True while the machine is waiting for an origin response (`.responds(...)`)."""
        return self._pending is not None

    @property
    def response(self) -> Response:
        """The response the cache would deliver to the client."""
        assert self.result is not None, f"exchange has not resolved yet ({self._describe()})"
        if isinstance(self.result, FromCache):
            return self.result.entry.response
        return self.result.response

    def responds(self, status: int = 200, **response_kwargs: Any) -> Exchange:
        """Feed the origin's response to the paused machine (kwargs go to `build_response`)."""
        assert self._pending is not None, f"exchange does not need an origin response ({self._describe()})"
        response = build_response(status, **response_kwargs)
        self.origin_responses.append(response)
        pending, self._pending = self._pending, None
        self._advance(pending.next(response))
        return self

    def _advance(self, state: AnyState) -> None:
        while True:
            if isinstance(state, (CacheMiss, NeedRevalidation)):
                self._pending = state
                self.sent_request = state.request
                return
            elif isinstance(state, StoreAndUse):
                self._scenario.entries.append(build_entry(request=self.request, response=state.response))
                self.result = state
                return
            elif isinstance(state, (CouldNotBeStored, FromCache)):
                self.result = state
                return
            elif isinstance(state, NeedToBeUpdated):
                for updated in state.updating_entries:
                    self._scenario._replace_headers(updated.id, updated.response.headers)
                state = state.next()
            elif isinstance(state, InvalidateEntries):
                self._scenario.entries = [entry for entry in self._scenario.entries if entry.id not in state.entry_ids]
                self.removed_entry_ids.extend(state.entry_ids)
                state = state.next()
            else:
                raise AssertionError(f"unexpected state: {state!r}")

    def _describe(self) -> str:
        if self._pending is not None:
            return f"pending on {type(self._pending).__name__}"
        if self.result is not None:
            return f"resolved as {type(self.result).__name__}"
        return "unresolved"

    def _fed_response(self) -> Response:
        assert self.origin_responses, "no origin response was fed to this exchange"
        return self.origin_responses[-1]

    # Then-assertions. Each checks the machine outcome AND the full metadata-flag triple.

    def assert_stored(self, *, revalidated: bool = False) -> Exchange:
        assert isinstance(self.result, StoreAndUse), f"expected the response to be stored, but {self._describe()}"
        _assert_flags(self._fed_response(), from_cache=False, stored=True, revalidated=revalidated)
        assert any(entry.request is self.request for entry in self._scenario.entries), (
            "no entry was stored for this exchange's request"
        )
        return self

    def assert_not_stored(self, *, revalidated: bool = False) -> Exchange:
        assert isinstance(self.result, CouldNotBeStored), (
            f"expected the response not to be stored, but {self._describe()}"
        )
        _assert_flags(self._fed_response(), from_cache=False, stored=False, revalidated=revalidated)
        assert all(entry.request is not self.request for entry in self._scenario.entries), (
            "an entry was unexpectedly stored for this exchange's request"
        )
        return self

    def assert_from_cache(self, *, revalidated: bool = False) -> Exchange:
        assert isinstance(self.result, FromCache), f"expected the response to come from cache, but {self._describe()}"
        _assert_flags(self.result.entry.response, from_cache=True, stored=False, revalidated=revalidated)
        return self

    def assert_age(self, low: int, high: int) -> Exchange:
        self.assert_from_cache()
        age = int(self.response.headers["age"])
        assert low <= age < high, f"expected age in [{low}, {high}), got {age}"
        return self

    def assert_served_stale(self, min_age: int) -> Exchange:
        self.assert_from_cache()
        age = int(self.response.headers["age"])
        assert age >= min_age, f"expected a stale response with age >= {min_age}, got {age}"
        return self

    def assert_cache_miss(self) -> Exchange:
        assert isinstance(self._pending, CacheMiss), f"expected an unconditional cache miss, but {self._describe()}"
        return self

    def assert_needs_revalidation(
        self,
        *,
        if_none_match: Optional[str] = None,
        if_modified_since: Optional[str] = None,
    ) -> Exchange:
        assert isinstance(self._pending, NeedRevalidation), f"expected a revalidation request, but {self._describe()}"
        assert self.sent_request is not None
        if if_none_match is not None:
            assert self.sent_request.headers.get("if-none-match") == if_none_match, (
                f"if-none-match is {self.sent_request.headers.get('if-none-match')!r}, expected {if_none_match!r}"
            )
        if if_modified_since is not None:
            assert self.sent_request.headers.get("if-modified-since") == if_modified_since, (
                f"if-modified-since is {self.sent_request.headers.get('if-modified-since')!r}, "
                f"expected {if_modified_since!r}"
            )
        return self

    def assert_invalidated(self, *entries: Entry) -> Exchange:
        for entry in entries:
            assert entry.id in self.removed_entry_ids, f"entry {entry.id} was not invalidated"
            assert all(stored.id != entry.id for stored in self._scenario.entries), (
                f"entry {entry.id} is still in storage"
            )
        return self
