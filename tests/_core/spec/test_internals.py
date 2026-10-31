"""
White-box tests for state-machine internals that are not observable through
full request/response exchanges (see test_storage_rules.py / test_scenarios.py
for the behavioral suites).
"""

from __future__ import annotations

from typing import Optional

import pytest

from hishel._core._spec import (
    CacheMiss,
    CacheOptions,
    CouldNotBeStored,
    IdleClient,
    InvalidateEntries,
    NeedRevalidation,
    NeedToBeUpdated,
    StoreAndUse,
)
from tests._core.spec.bdd import CacheScenario, build_entry, build_request, build_response


def test_options_propagated_through_all_transitions() -> None:
    options = CacheOptions()
    idle = IdleClient(options=options)

    assert idle.next(build_request(), []).options is options  # CacheMiss
    fresh_entry = build_entry(response=build_response(max_age=3600))
    assert idle.next(build_request(), [fresh_entry]).options is options  # FromCache
    stale_entry = build_entry(response=build_response(max_age=0))
    assert idle.next(build_request(), [stale_entry]).options is options  # NeedRevalidation

    cache_miss = CacheMiss(options=options, request=build_request())
    assert cache_miss.next(build_response(max_age=3600)).options is options  # StoreAndUse
    assert cache_miss.next(build_response(cache_control="no-store")).options is options  # CouldNotBeStored

    need_revalidation = NeedRevalidation(
        options=options,
        request=build_request(),
        original_request=build_request(),
        revalidating_entries=[build_entry(response=build_response(max_age=0))],
    )
    assert need_revalidation.next(build_response(304)).options is options  # NeedToBeUpdated
    assert need_revalidation.next(build_response(200, max_age=3600)).options is options  # InvalidateEntries


def test_original_request_identity_preserved_through_revalidation() -> None:
    options = CacheOptions()
    original_request = build_request()

    single = NeedRevalidation(
        options=options,
        request=build_request(),
        original_request=original_request,
        revalidating_entries=[build_entry()],
    )
    updated = single.next(build_response(304))
    assert isinstance(updated, NeedToBeUpdated)
    assert updated.original_request is original_request

    multiple = NeedRevalidation(
        options=options,
        request=build_request(),
        original_request=original_request,
        revalidating_entries=[build_entry(), build_entry()],
    )
    invalidated = multiple.next(build_response(304))
    assert isinstance(invalidated, InvalidateEntries)
    assert isinstance(invalidated.next_state, CacheMiss)
    assert invalidated.next_state.request is original_request


def test_empty_revalidating_entries_yields_cache_miss() -> None:
    empty = NeedRevalidation(
        options=CacheOptions(),
        request=build_request(),
        original_request=build_request(),
        revalidating_entries=[],
    )
    next_state = empty.next(build_response(304))
    assert isinstance(next_state, CacheMiss)
    assert next_state.after_revalidation is True


def test_stored_entry_created_from_original_request() -> None:
    """
    DSL-fidelity guard: like the production loop, the DSL stores new entries
    under the original client request, not the conditional wire request.
    """
    cache = CacheScenario()
    cache.seed(response={"max_age": 0, "etag": '"abc"'})

    exchange = cache.get()
    exchange.assert_needs_revalidation(if_none_match='"abc"')
    exchange.responds(200, max_age=3600)
    exchange.assert_stored(revalidated=True)

    assert exchange.sent_request is not exchange.request  # a conditional copy went to the origin
    new_entry = next(entry for entry in cache.entries if entry.request is exchange.request)
    assert new_entry.request is exchange.request


def _revalidate_stored_public_entry(
    status: int,
    authorization: Optional[str],
    cache_control: str,
) -> object:
    """A public entry stored without credentials gets revalidated by the given request."""
    headers = {"authorization": authorization} if authorization else {}
    request = build_request(headers=headers)
    return NeedRevalidation(
        options=CacheOptions(),
        request=request,
        original_request=request,
        revalidating_entries=[build_entry(response=build_response(max_age=0, etag='"abc"'))],
    ).next(build_response(status, cache_control=cache_control))


@pytest.mark.parametrize("status", [301, 404, 410])
def test_authenticated_revalidation_response_is_not_stored(status: int) -> None:
    """
    RFC 9111 §3.5: a shared cache must not store a response to a request with
    Authorization unless it allows that, so these statuses must be checked
    against the current request, not the stored one that had no credentials.
    """
    state = _revalidate_stored_public_entry(status, "Bearer alice", "max-age=3600")
    assert isinstance(state, CouldNotBeStored)


@pytest.mark.parametrize("status", [301, 404, 410])
def test_authenticated_revalidation_response_allowed_by_the_server_is_stored(status: int) -> None:
    state = _revalidate_stored_public_entry(status, "Bearer alice", "public, max-age=3600")
    assert isinstance(state, StoreAndUse)


@pytest.mark.parametrize("status", [301, 404, 410])
def test_anonymous_revalidation_response_is_still_stored(status: int) -> None:
    state = _revalidate_stored_public_entry(status, None, "max-age=3600")
    assert isinstance(state, StoreAndUse)
