"""
Declarative RFC 9111 rule tables.

Each record captures one spec sentence: given a cache configuration and
optional stored entries, a request and (where applicable) an origin response,
the expected outcome. The `rfc` and `quote` fields tie every record back to
the exact wording of https://www.rfc-editor.org/rfc/rfc9111.html.

The runners drive the whole state machine through the bdd DSL and assert the
full metadata-flag triple (stored/from_cache/revalidated) on every record.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Optional

import pytest

from hishel._core._spec import HEURISTICALLY_CACHEABLE_STATUS_CODES
from tests._core.spec.bdd import CacheScenario, http_date

# Expected outcomes
STORED = "stored"
NOT_STORED = "not-stored"
MISS = "miss"
FROM_CACHE = "from-cache"
REVALIDATE = "revalidate"
SERVED_STALE = "served-stale"
FROM_CACHE_REVALIDATED = "from-cache-revalidated"


@dataclass(frozen=True)
class Rule:
    id: str
    rfc: str
    quote: str
    expect: str
    options: Dict[str, Any] = field(default_factory=dict)  # CacheScenario kwargs
    stored: List[Dict[str, Any]] = field(default_factory=list)  # cache.seed kwargs per entry
    request: Dict[str, Any] = field(default_factory=dict)  # cache.get kwargs
    response: Dict[str, Any] = field(default_factory=dict)  # exchange.responds kwargs
    refetch: Optional[Dict[str, Any]] = None  # second responds() after invalidation
    freshened: FrozenSet[int] = frozenset()  # stored indices whose headers get refreshed
    invalidated: FrozenSet[int] = frozenset()  # stored indices removed from storage
    min_age: int = 0  # for SERVED_STALE


def as_params(rules: List[Rule]) -> List[Any]:
    return [pytest.param(rule, id=rule.id) for rule in rules]


def fresh(**response_kwargs: Any) -> Dict[str, Any]:
    """A seed stored 1800s ago with max-age=3600 — comfortably fresh."""
    return {"response": {"max_age": 3600, "age_seconds": 1800, **response_kwargs}}


# All stale seeds share one Date value so that multi-entry records keep their
# insertion order through IdleClient's most-recent-first sort (stable sort on
# equal dates) — expectations below index into `stored` by position.
STALE_DATE = http_date(7200)


def stale(**response_kwargs: Any) -> Dict[str, Any]:
    """A seed stored 7200s ago with max-age=100 — definitely stale."""
    return {"response": {"max_age": 100, "headers": {"date": STALE_DATE}, **response_kwargs}}


# =============================================================================
# RFC 9111 §3 — Storing Responses in Caches
# (empty cache, one exchange: does the origin response get stored?)
# =============================================================================

STORAGE_RULES = [
    Rule(
        id="max-age-directive-allows-storage",
        rfc="§5.2.2.1",
        quote="The max-age response directive indicates that the response is to be "
        "considered stale after its age is greater than the specified number of seconds.",
        response={"max_age": 3600},
        expect=STORED,
    ),
    Rule(
        id="expires-header-allows-storage",
        rfc="§5.3",
        quote="The Expires header field gives the date/time after which the response is considered stale.",
        response={"expires_in": 3600},
        expect=STORED,
    ),
    Rule(
        id="public-directive-allows-storage",
        rfc="§5.2.2.9",
        quote="The public response directive indicates that a cache MAY store the response "
        "even if it would otherwise be prohibited.",
        response={"cache_control": "public"},
        expect=STORED,
    ),
    Rule(
        id="s-maxage-allows-storage-in-shared-cache",
        rfc="§5.2.2.10",
        quote="The s-maxage response directive indicates that, for a shared cache, the maximum age "
        "specified by this directive overrides the maximum age specified by either the max-age "
        "directive or the Expires header field.",
        response={"s_maxage": 7200},
        expect=STORED,
    ),
    Rule(
        id="private-response-stored-in-private-cache",
        rfc="§5.2.2.7",
        quote="The unqualified private response directive... indicates that... a private cache MAY store the response.",
        options={"shared": False},
        response={"cache_control": "private", "max_age": 3600},
        expect=STORED,
    ),
    Rule(
        id="multiple-caching-directives-allow-storage",
        rfc="§3",
        quote="the response contains at least one of the following: ...",
        response={"cache_control": "public", "max_age": 3600, "s_maxage": 7200, "expires_in": 7200},
        expect=STORED,
    ),
    Rule(
        id="unsupported-method-prevents-storage",
        rfc="§3",
        quote="the request method is understood by the cache",
        request={"method": "POST"},
        response={"max_age": 3600},
        expect=NOT_STORED,
    ),
    Rule(
        id="no-store-directive-prevents-storage",
        rfc="§5.2.2.5",
        quote="The no-store response directive indicates that a cache MUST NOT store "
        "any part of either the immediate request or the response.",
        response={"cache_control": "no-store"},
        expect=NOT_STORED,
    ),
    Rule(
        id="no-store-overrides-other-directives",
        rfc="§5.2.2.5",
        quote="The no-store response directive indicates that a cache MUST NOT store "
        "any part of either the immediate request or the response.",
        response={"cache_control": "no-store", "max_age": 3600},
        expect=NOT_STORED,
    ),
    Rule(
        id="private-directive-prevents-storage-in-shared-cache",
        rfc="§5.2.2.7",
        quote="The unqualified private response directive indicates that a shared cache MUST NOT store the response.",
        response={"cache_control": "private", "max_age": 3600},
        expect=NOT_STORED,
    ),
    Rule(
        id="authorization-prevents-storage-in-shared-cache",
        rfc="§3.5",
        quote="A shared cache MUST NOT use a cached response to a request with an Authorization "
        "header field unless... a response directive is present that explicitly allows shared caching.",
        request={"headers": {"authorization": "Bearer token123"}},
        response={"max_age": 3600},
        expect=NOT_STORED,
    ),
    Rule(
        id="authorization-with-public-directive-allows-storage",
        rfc="§3.5",
        quote="unless a cache directive that allows such responses to be stored is present "
        "in the response (e.g. public, must-revalidate, s-maxage).",
        request={"headers": {"authorization": "Bearer token123"}},
        response={"cache_control": "public"},
        expect=STORED,
    ),
    Rule(
        id="no-caching-metadata-and-non-heuristic-status-prevents-storage",
        rfc="§3",
        quote="the response contains at least one of the following: ... a status code that is "
        "defined as heuristically cacheable.",
        response={"status": 201},
        expect=NOT_STORED,
    ),
    Rule(
        id="s-maxage-does-not-apply-to-private-cache",
        rfc="§5.2.2.10",
        quote="The s-maxage response directive indicates that, for a shared cache...",
        options={"shared": False},
        response={"status": 201, "s_maxage": 3600},
        expect=NOT_STORED,
    ),
    *[
        Rule(
            id=f"informational-status-{status}-prevents-storage",
            rfc="§3",
            quote="the response status code is final (see Section 15 of [HTTP])",
            response={"status": status, "max_age": 3600},
            expect=NOT_STORED,
        )
        for status in (100, 101, 102, 103)
    ],
    *[
        Rule(
            id=f"not-understood-status-{status}-prevents-storage",
            rfc="§3",
            quote="if the response status code is 206 or 304... the cache understands the response status code",
            response={"status": status, "max_age": 3600},
            expect=NOT_STORED,
        )
        for status in (206, 304)
    ],
    *[
        Rule(
            id=f"heuristically-cacheable-status-{status}-allows-storage",
            rfc="§4.2.2",
            quote="a cache MAY assign a heuristic expiration time when an explicit time is not specified",
            response={"status": status},
            expect=STORED,
        )
        for status in HEURISTICALLY_CACHEABLE_STATUS_CODES
    ],
]


@pytest.mark.parametrize("rule", as_params(STORAGE_RULES))
def test_storage_rules(rule: Rule) -> None:
    cache = CacheScenario(**rule.options)
    exchange = cache.get(**rule.request)
    exchange.assert_cache_miss()
    exchange.responds(**rule.response)
    if rule.expect == STORED:
        exchange.assert_stored()
    elif rule.expect == NOT_STORED:
        exchange.assert_not_stored()
    else:
        raise AssertionError(f"unknown expectation: {rule.expect}")


# =============================================================================
# RFC 9111 §4 — Constructing Responses from Caches
# (seeded storage, one request: served, revalidated, or missed?)
# =============================================================================

LAST_WEEK = http_date(7 * 24 * 3600)

REUSE_RULES = [
    Rule(
        id="empty-cache-misses",
        rfc="§4.1",
        quote="If no stored response matches, the cache cannot satisfy the presented request.",
        expect=MISS,
    ),
    Rule(
        id="range-request-misses",
        rfc="§3.3",
        quote="(simplified implementation: all range requests are forwarded to the origin)",
        stored=[fresh()],
        request={"headers": {"range": "bytes=0-1023"}},
        expect=MISS,
    ),
    *[
        Rule(
            id=f"unsafe-method-{method.lower()}-misses",
            rfc="§4",
            quote="the presented request does not contain the no-cache directive... "
            "(unsafe methods must be written through to the origin)",
            stored=[fresh()],
            request={"method": method},
            expect=MISS,
        )
        for method in ("POST", "PUT", "DELETE", "PATCH")
    ],
    Rule(
        id="url-mismatch-misses",
        rfc="§4",
        quote="the presented target URI and that of the stored response match",
        stored=[{"request": {"url": "https://example.com/resource-b"}, "response": {"max_age": 3600}}],
        request={"url": "https://example.com/resource-a"},
        expect=MISS,
    ),
    Rule(
        id="method-mismatch-misses",
        rfc="§4",
        quote="the request method associated with the stored response allows it to be used for the presented request",
        stored=[fresh()],
        request={"method": "HEAD"},
        expect=MISS,
    ),
    *[
        Rule(
            id=f"safe-method-{method.lower()}-served-from-cache",
            rfc="§4",
            quote="the request method associated with the stored response allows it to be used "
            "for the presented request",
            stored=[{"request": {"method": method}, "response": {"max_age": 3600, "age_seconds": 1800}}],
            request={"method": method},
            expect=FROM_CACHE,
        )
        for method in ("GET", "HEAD")
    ],
    Rule(
        id="fresh-response-served-from-cache",
        rfc="§4.2",
        quote="A fresh response is one whose age has not yet exceeded its freshness lifetime.",
        stored=[fresh()],
        expect=FROM_CACHE,
    ),
    Rule(
        id="stale-response-demoted-to-revalidation",
        rfc="§4.2",
        quote="A stale response is one where the freshness lifetime has been exceeded.",
        stored=[stale()],
        expect=REVALIDATE,
    ),
    Rule(
        id="stale-response-served-when-stale-allowed",
        rfc="§4.2.4",
        quote="A cache MUST NOT generate a stale response unless it is disconnected or doing so "
        "is explicitly permitted by the client or origin server.",
        options={"allow_stale": True},
        stored=[stale()],
        expect=SERVED_STALE,
        min_age=7200,
    ),
    Rule(
        id="must-revalidate-overrides-allow-stale",
        rfc="§5.2.2.2",
        quote="the must-revalidate response directive indicates that once the response has become "
        "stale, a cache MUST NOT reuse that response... without forwarding it to the origin server "
        "for validation.",
        options={"allow_stale": True},
        stored=[stale(cache_control="must-revalidate")],
        expect=REVALIDATE,
    ),
    Rule(
        id="response-no-cache-demoted-to-revalidation",
        rfc="§5.2.2.4",
        quote="The no-cache response directive... indicates that the response MUST NOT be used to "
        "satisfy any other request without forwarding it for validation.",
        stored=[fresh(cache_control="no-cache")],
        expect=REVALIDATE,
    ),
    Rule(
        id="request-no-cache-forces-revalidation-of-fresh-response",
        rfc="§5.2.1.4",
        quote="The no-cache request directive indicates that the client prefers a stored response "
        "not be used to satisfy the request without successful validation on the origin server.",
        stored=[fresh(etag='"abc123"')],
        request={"cache_control": "no-cache"},
        expect=REVALIDATE,
    ),
    Rule(
        id="vary-mismatch-demoted-to-revalidation",
        rfc="§4.1",
        quote="the presented request... and the stored request... match... (selecting header fields "
        "nominated by the stored response)",
        stored=[
            {
                "request": {"headers": {"accept-encoding": "gzip"}},
                "response": {"max_age": 3600, "vary": "Accept-Encoding"},
            }
        ],
        request={"headers": {"accept-encoding": "br"}},
        expect=REVALIDATE,
    ),
    Rule(
        id="vary-star-never-matches",
        rfc="§4.1",
        quote="A stored response with a Vary header field value containing a member '*' always fails to match.",
        stored=[
            {
                "request": {"headers": {"accept-encoding": "gzip"}},
                "response": {"max_age": 3600, "vary": "*"},
            }
        ],
        request={"headers": {"accept-encoding": "gzip"}},
        expect=REVALIDATE,
    ),
    Rule(
        id="matching-vary-headers-served-from-cache",
        rfc="§4.1",
        quote="the presented request... and the stored request... match... (selecting header fields "
        "nominated by the stored response)",
        stored=[
            {
                "request": {"headers": {"accept-encoding": "gzip"}},
                "response": {"max_age": 3600, "vary": "Accept-Encoding"},
            }
        ],
        request={"headers": {"accept-encoding": "gzip"}},
        expect=FROM_CACHE,
    ),
    Rule(
        id="no-vary-header-ignores-request-headers",
        rfc="§4.1",
        quote="If the stored response has no Vary header field, the selecting header fields trivially match.",
        stored=[{"request": {"headers": {"accept": "text/html"}}, "response": {"max_age": 3600}}],
        request={"headers": {"accept": "application/json"}},
        expect=FROM_CACHE,
    ),
    Rule(
        id="all-reuse-conditions-met-served-from-cache",
        rfc="§4",
        quote="When presented with a request, a cache MUST NOT reuse a stored response unless...",
        stored=[
            {
                "request": {"headers": {"accept": "application/json", "accept-language": "en-US"}},
                "response": {"max_age": 3600, "age_seconds": 600, "vary": "Accept, Accept-Language"},
            }
        ],
        request={"headers": {"accept": "application/json", "accept-language": "en-US"}},
        expect=FROM_CACHE,
    ),
    Rule(
        id="heuristic-freshness-from-last-modified",
        rfc="§4.2.2",
        quote="If the response has a Last-Modified header field, caches are encouraged to use a "
        "heuristic expiration value that is no more than some fraction of the interval since "
        "that time.",
        stored=[{"response": {"last_modified": LAST_WEEK}}],
        expect=FROM_CACHE,
    ),
]


@pytest.mark.parametrize("rule", as_params(REUSE_RULES))
def test_reuse_rules(rule: Rule) -> None:
    cache = CacheScenario(**rule.options)
    for seed in rule.stored:
        cache.seed(**seed)
    exchange = cache.get(**rule.request)
    if rule.expect == MISS:
        exchange.assert_cache_miss()
    elif rule.expect == FROM_CACHE:
        exchange.assert_from_cache()
    elif rule.expect == SERVED_STALE:
        exchange.assert_served_stale(rule.min_age)
    elif rule.expect == REVALIDATE:
        exchange.assert_needs_revalidation()
    else:
        raise AssertionError(f"unknown expectation: {rule.expect}")


# =============================================================================
# RFC 9111 §4.3.3 / §4.3.4 — Handling a Validation Response / Freshening
# (seeded stale entries, one request that revalidates: what happens to storage
# and what does the client get?)
# =============================================================================

REVALIDATION_RULES = [
    Rule(
        id="304-with-weak-etag-falls-back-to-last-modified",
        rfc="§4.3.4",
        quote="If the new response contains a strong validator... (a weak entity tag never "
        "identifies stored responses; Last-Modified is used instead)",
        stored=[stale(last_modified=LAST_WEEK)],
        response={"status": 304, "etag": 'W/"weak1"', "last_modified": LAST_WEEK, "max_age": 7200},
        freshened=frozenset({0}),
        expect=FROM_CACHE_REVALIDATED,
    ),
    Rule(
        id="304-with-matching-last-modified-freshens",
        rfc="§4.3.4",
        quote="If the 304 response contains a Last-Modified value: the stored responses with "
        "the same Last-Modified value.",
        stored=[stale(last_modified=LAST_WEEK)],
        response={"status": 304, "last_modified": LAST_WEEK, "max_age": 7200},
        freshened=frozenset({0}),
        expect=FROM_CACHE_REVALIDATED,
    ),
    Rule(
        id="304-with-single-entry-and-no-validators-freshens-it",
        rfc="§4.3.4",
        quote="If there is only a single stored response: that response.",
        stored=[stale()],
        response={"status": 304, "max_age": 7200},
        freshened=frozenset({0}),
        expect=FROM_CACHE_REVALIDATED,
    ),
    Rule(
        id="304-strong-etag-matches-stored-weak-etag",
        rfc="§4.3.4",
        quote="two entity tags are equivalent if their opaque-tags match character-by-character, "
        "regardless of either or both being tagged as weak. (RFC 9110 §8.8.3.2)",
        stored=[stale(etag='W/"abc123"')],
        response={"status": 304, "etag": '"abc123"', "max_age": 7200},
        freshened=frozenset({0}),
        expect=FROM_CACHE_REVALIDATED,
    ),
    Rule(
        id="304-freshens-matching-and-invalidates-others",
        rfc="§4.3.4",
        quote="If the 304 response contains a strong entity tag: the stored responses with the same strong entity tag.",
        stored=[stale(etag='"match123"'), stale(etag='"nomatch456"')],
        response={"status": 304, "etag": '"match123"', "max_age": 7200},
        freshened=frozenset({0}),
        invalidated=frozenset({1}),
        expect=FROM_CACHE_REVALIDATED,
    ),
    Rule(
        id="304-with-multiple-entries-and-no-validators-invalidates-all",
        rfc="§4.3.4",
        quote="(no stored response can be identified: the cache conservatively invalidates them "
        "and refetches from the origin)",
        stored=[stale(), stale()],
        response={"status": 304, "max_age": 7200},
        invalidated=frozenset({0, 1}),
        refetch={"status": 200, "max_age": 3600},
        expect=STORED,
    ),
    Rule(
        id="304-with-non-matching-etag-invalidates-and-refetches",
        rfc="§4.3.4",
        quote="If the 304 response contains a strong entity tag: the stored responses with the "
        "same strong entity tag. (none match: invalidate and refetch)",
        stored=[stale(etag='"old123"')],
        response={"status": 304, "etag": '"new456"', "max_age": 7200},
        invalidated=frozenset({0}),
        refetch={"status": 200, "max_age": 3600},
        expect=STORED,
    ),
    *[
        Rule(
            id=f"full-{status}-response-replaces-stored-entries",
            rfc="§4.3.3",
            quote="A full response... indicates that none of the stored responses nominated in the "
            "conditional request are suitable. Instead, the cache MUST use the full response to "
            "satisfy the request.",
            stored=[stale(), stale()],
            response={"status": status, "max_age": 7200},
            invalidated=frozenset({0}),  # the machine keeps the most recent old entry
            expect=STORED,
        )
        for status in (200, 201, 202, 203, 204)
    ],
    Rule(
        id="full-206-response-cannot-be-stored",
        rfc="§4.3.3",
        quote="The cache MAY store such a full response, subject to its constraints (see Section 3).",
        stored=[stale(), stale()],
        response={"status": 206, "max_age": 7200},
        invalidated=frozenset({0}),
        expect=NOT_STORED,
    ),
    *[
        Rule(
            id=f"5xx-{status}-error-forwarded-to-client",
            rfc="§4.3.3",
            quote="if a cache receives a 5xx (Server Error) response while attempting to validate "
            "a response, it can either forward this response to the requesting client or act as "
            "if the server failed to respond.",
            stored=[stale()],
            response={"status": status, "cache_control": "no-store"},
            expect=NOT_STORED,
        )
        for status in (500, 502, 503, 504)
    ],
    Rule(
        id="5xx-with-two-entries-keeps-most-recent",
        rfc="§4.3.3",
        quote="(same invalidation behavior as a full response: all but the most recent stored entry are removed)",
        stored=[stale(), stale()],
        response={"status": 503, "cache_control": "no-store"},
        invalidated=frozenset({0}),
        expect=NOT_STORED,
    ),
    Rule(
        id="unexpected-301-during-revalidation-is-stored",
        rfc="§4.3.3",
        quote="(RFC 9111 does not define behavior for other status codes here; this implementation "
        "forwards them through the normal storage decision — 301 is heuristically cacheable)",
        stored=[stale()],
        response={"status": 301, "max_age": 3600},
        expect=STORED,
    ),
]


@pytest.mark.parametrize("rule", as_params(REVALIDATION_RULES))
def test_revalidation_rules(rule: Rule) -> None:
    cache = CacheScenario(**rule.options)
    seeded = [cache.seed(**seed) for seed in rule.stored]
    exchange = cache.get(**rule.request)
    exchange.assert_needs_revalidation()
    exchange.responds(**rule.response)
    if rule.refetch is not None:
        exchange.assert_cache_miss()
        exchange.responds(**rule.refetch)

    exchange.assert_invalidated(*[seeded[index] for index in rule.invalidated])
    surviving_ids = {entry.id for entry in cache.entries}
    for index, entry in enumerate(seeded):
        if index not in rule.invalidated:
            assert entry.id in surviving_ids, f"stored entry {index} should have been kept"

    # Freshened entries carry the 304's Cache-Control value in storage.
    freshening_cache_control = exchange.origin_responses[0].headers.get("cache-control")
    for index in rule.freshened:
        current = next(entry for entry in cache.entries if entry.id == seeded[index].id)
        assert current.response.headers.get("cache-control") == freshening_cache_control, (
            f"stored entry {index} was not freshened with the 304's headers"
        )

    if rule.expect == FROM_CACHE_REVALIDATED:
        exchange.assert_from_cache(revalidated=True)
    elif rule.expect == STORED:
        exchange.assert_stored(revalidated=True)
    elif rule.expect == NOT_STORED:
        exchange.assert_not_stored(revalidated=True)
        final = rule.refetch if rule.refetch is not None else rule.response
        assert exchange.response.status_code == final.get("status", 200)
    else:
        raise AssertionError(f"unknown expectation: {rule.expect}")
