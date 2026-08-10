"""
Multi-step RFC 9111 scenarios written as full request/response exchanges.

Each test drives the whole cache state machine (via the bdd DSL) exactly the
way the production loop does: requests come in, origin responses are fed when
the machine asks for them, and outcomes are observed on the delivered
responses and the cache's storage.
"""

from __future__ import annotations

from typing import Dict

import pytest
import time_machine

from tests._core.spec.bdd import CacheScenario, http_date

LAST_WEEK = http_date(7 * 24 * 3600)


def test_304_freshens_stored_response(cache: CacheScenario) -> None:
    """
    RFC 9111 §4.3.4: "the cache MUST update the stored response as described
    in Section 3.2" — a 304 revalidation freshens the stored entry and serves
    it from cache.
    """
    cache.get().responds(200, etag='"abc"', max_age=0).assert_stored()

    exchange = cache.get()
    exchange.assert_needs_revalidation(if_none_match='"abc"')
    exchange.responds(304, etag='"abc"', max_age=7200)
    exchange.assert_from_cache(revalidated=True)

    # The freshened headers are visible in storage.
    assert cache.entry_for().response.headers["cache-control"] == "max-age=7200"


def test_full_response_during_revalidation_replaces_entry(cache: CacheScenario) -> None:
    """
    RFC 9111 §4.3.3: "the cache MUST use the full response to satisfy the
    request" — and the fed response object is marked as stored + revalidated.
    """
    cache.seed(response={"max_age": 0, "etag": '"old"'})

    exchange = cache.get()
    exchange.assert_needs_revalidation(if_none_match='"old"')
    exchange.responds(200, max_age=3600)
    exchange.assert_stored(revalidated=True)


def test_conditional_request_carries_validators(cache: CacheScenario) -> None:
    """
    RFC 9111 §4.3.1: a cache "MUST send the relevant entity tags (using
    If-None-Match)... SHOULD send the Last-Modified value (using
    If-Modified-Since)".
    """
    cache.seed(response={"max_age": 0, "etag": '"abc123"', "last_modified": LAST_WEEK})

    cache.get().assert_needs_revalidation(if_none_match='"abc123"', if_modified_since=LAST_WEEK)


@pytest.mark.parametrize("stored_age", [0, 1800])
def test_age_header_reflects_stored_age(cache: CacheScenario, stored_age: int) -> None:
    """
    RFC 9111 §4: "the cache MUST include a single Age header field in the
    response with a value equal to the stored response's current_age".
    """
    cache.get().responds(200, max_age=3600, age_seconds=stored_age).assert_stored()

    cache.get().assert_age(stored_age, stored_age + 6)


def test_most_recent_of_multiple_fresh_entries_is_served(cache: CacheScenario) -> None:
    """
    RFC 9111 §4: "When more than one suitable response is stored, a cache
    MUST use the most recent one (as determined by the Date header field)."
    """
    cache.seed(response={"max_age": 7200, "age_seconds": 3000})
    cache.seed(response={"max_age": 7200, "age_seconds": 1000})
    cache.seed(response={"max_age": 7200, "age_seconds": 2000})

    cache.get().assert_age(1000, 1006)


def test_missing_date_header_does_not_break_selection(cache: CacheScenario) -> None:
    """A stored response without a Date header must not break entry selection."""
    cache.seed(response={"max_age": 3600, "with_date": False})
    cache.seed(response={"max_age": 3600, "age_seconds": 100})

    cache.get().assert_from_cache()


@pytest.mark.parametrize(
    "vary,stored_headers,mismatching_headers",
    [
        pytest.param(
            "Accept",
            {"accept": "application/json"},
            {"accept": "text/xml"},
            id="accept",
        ),
        pytest.param(
            "Accept-Encoding",
            {"accept-encoding": "gzip"},
            {"accept-encoding": "br"},
            id="accept-encoding",
        ),
        pytest.param(
            "Accept, Accept-Encoding, Accept-Language",
            {"accept": "application/json", "accept-encoding": "gzip", "accept-language": "en-US"},
            {"accept": "application/json", "accept-encoding": "gzip", "accept-language": "fr-FR"},
            id="multiple-vary-headers",
        ),
    ],
)
def test_content_negotiation_with_vary(
    cache: CacheScenario,
    vary: str,
    stored_headers: Dict[str, str],
    mismatching_headers: Dict[str, str],
) -> None:
    """
    RFC 9111 §4.1: selecting header fields nominated by Vary must match for
    reuse; a mismatch demotes the entry to revalidation.
    """
    cache.get(headers=stored_headers).responds(200, max_age=3600, vary=vary).assert_stored()

    cache.get(headers=stored_headers).assert_from_cache()
    cache.get(headers=mismatching_headers).assert_needs_revalidation()


def test_lifecycle_fresh_to_stale(cache: CacheScenario) -> None:
    """
    RFC 9111 §4.2: the same stored response is served while fresh and demoted
    to revalidation once its age exceeds the freshness lifetime.
    """
    with time_machine.travel("2026-08-01 12:00 +0000", tick=False) as traveller:
        cache.get().responds(200, max_age=20).assert_stored()
        cache.get().assert_from_cache()

        traveller.shift(30)

        cache.get().assert_needs_revalidation()
