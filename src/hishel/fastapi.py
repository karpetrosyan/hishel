from __future__ import annotations

import typing as t

from hishel._utils import generate_http_date

try:
    import fastapi
except ImportError as e:
    raise ImportError(
        "fastapi is required to use hishel.fastapi module. "
        "Please install hishel with the 'fastapi' extra, "
        "e.g., 'pip install hishel[fastapi]'."
    ) from e


def cache(
    *,
    max_age: int | None = None,
    s_maxage: int | None = None,
    public: bool = False,
    private: bool | list[str] = False,
    no_cache: bool | list[str] = False,
    no_store: bool = False,
    no_transform: bool = False,
    must_revalidate: bool = False,
    must_understand: bool = False,
    proxy_revalidate: bool = False,
    immutable: bool = False,
    stale_while_revalidate: int | None = None,
    stale_if_error: int | None = None,
) -> t.Any:
    """
    Add HTTP Cache-Control headers to FastAPI responses.

    This function provides a convenient way to set cache control directives
    on FastAPI responses according to RFC 9111 (HTTP Caching) and related standards.

    Args:
        max_age: Maximum time in seconds a response can be cached.
            [RFC 9111, Section 5.2.2.1]
            Example: max_age=3600 sets "Cache-Control: max-age=3600"
            Use for both private and shared caches.

        s_maxage: Maximum time in seconds for shared caches (proxies, CDNs).
            [RFC 9111, Section 5.2.2.10]
            Overrides max_age for shared caches only.
            Example: s_maxage=7200 sets "s-maxage=7200"
            Private caches (browsers) ignore this directive.

        public: Marks response as cacheable by any cache.
            [RFC 9111, Section 5.2.2.9]
            Explicitly allows caching even if Authorization header is present.
            Example: public=True adds "public" to Cache-Control

        private: Marks response as cacheable only by private caches (browsers).
            [RFC 9111, Section 5.2.2.7]
            Shared caches (proxies, CDNs) MUST NOT store the response.
            Can be True (applies to entire response) or a list of field names
            (applies only to specific headers).
            Examples:
                - private=True adds "private" to Cache-Control
                - private=["Set-Cookie"] adds 'private="Set-Cookie"' to Cache-Control
            Useful for user-specific data.

        no_cache: Response can be cached but MUST be revalidated before use.
            [RFC 9111, Section 5.2.2.4]
            Cache MUST check with origin server before serving cached copy.
            Can be True (requires revalidation for entire response) or a list
            of field names (requires revalidation only for specific headers).
            Examples:
                - no_cache=True adds "no-cache" to Cache-Control
                - no_cache=["Set-Cookie", "Authorization"] adds 'no-cache="Set-Cookie, Authorization"'
            Different from no_store - allows caching with mandatory validation.

        no_store: Response MUST NOT be stored in any cache.
            [RFC 9111, Section 5.2.2.5]
            Most restrictive directive - prevents all caching.
            Example: no_store=True adds "no-store" to Cache-Control
            Use for sensitive data (passwords, personal information).

        no_transform: Prohibits any transformations to the response.
            [RFC 9111, Section 5.2.2.6]
            Prevents proxies from modifying content (compression, format conversion).
            Example: no_transform=True adds "no-transform" to Cache-Control

        must_revalidate: Cache MUST revalidate stale responses.
            [RFC 9111, Section 5.2.2.2]
            Prevents serving stale content even if client accepts it.
            Example: must_revalidate=True adds "must-revalidate" to Cache-Control
            Stronger than no-cache - applies only when response becomes stale.

        must_understand: Cache MUST understand response status code to cache it.
            [RFC 9111, Section 5.2.2.3]
            Prevents caching of responses with unknown status codes.
            Example: must_understand=True adds "must-understand" to Cache-Control

        proxy_revalidate: Like must_revalidate but only for shared caches.
            [RFC 9111, Section 5.2.2.8]
            Shared caches MUST revalidate stale responses.
            Private caches can serve stale content without revalidation.
            Example: proxy_revalidate=True adds "proxy-revalidate" to Cache-Control

        immutable: Response body will never change.
            [RFC 8246]
            Optimization hint that revalidation is unnecessary during freshness period.
            Example: immutable=True adds "immutable" to Cache-Control
            Useful for versioned assets (e.g., /static/app.v123.js)

        stale_while_revalidate: Allow stale response while revalidating in background.
            [RFC 5861, Section 3]
            Time in seconds cache can serve stale content while fetching fresh copy.
            Example: stale_while_revalidate=86400 adds "stale-while-revalidate=86400"
            Improves performance by avoiding cache misses.

        stale_if_error: Allow stale response if origin server returns error.
            [RFC 5861, Section 4]
            Time in seconds cache can serve stale content when origin is unavailable.
            Example: stale_if_error=3600 adds "stale-if-error=3600"
            Improves availability during server failures.

    Returns:
        A dependency function that adds Cache-Control headers to the response.

    Examples:
        >>> from fastapi import FastAPI
        >>> from hishel.fastapi import cache
        >>>
        >>> app = FastAPI()
        >>>
        >>> # Static assets - cache for 1 year, immutable
        >>> @app.get("/static/logo.png")
        >>> async def get_logo(
        ...     _: None = cache(max_age=31536000, public=True, immutable=True)
        ... ):
        ...     return {"image": "logo.png"}
        >>>
        >>> # API endpoint - cache for 5 minutes, private
        >>> @app.get("/api/user/profile")
        >>> async def get_profile(
        ...     _: None = cache(max_age=300, private=True)
        ... ):
        ...     return {"name": "John"}
        >>>
        >>> # CDN with shared cache - different TTLs for browsers and proxies
        >>> @app.get("/api/public/data")
        >>> async def get_data(
        ...     _: None = cache(max_age=300, s_maxage=3600, public=True)
        ... ):
        ...     return {"data": "public"}
        >>>
        >>> # Sensitive data - no caching
        >>> @app.get("/api/secrets")
        >>> async def get_secrets(
        ...     _: None = cache(no_store=True)
        ... ):
        ...     return {"secret": "value"}
        >>>
        >>> # Cacheable but must revalidate
        >>> @app.get("/api/critical")
        >>> async def get_critical(
        ...     _: None = cache(max_age=3600, must_revalidate=True)
        ... ):
        ...     return {"critical": "data"}
        >>>
        >>> # Stale-while-revalidate for better performance
        >>> @app.get("/api/news")
        >>> async def get_news(
        ...     _: None = cache(max_age=300, stale_while_revalidate=86400, public=True)
        ... ):
        ...     return {"news": "articles"}
        >>>
        >>> # Private directive with specific field names
        >>> @app.get("/api/user/data")
        >>> async def get_user_data(
        ...     _: None = cache(max_age=600, private=["Set-Cookie"])
        ... ):
        ...     return {"data": "user_specific"}
        >>>
        >>> # No-cache with field names - revalidate only specific headers
        >>> @app.get("/api/conditional")
        >>> async def get_conditional(
        ...     _: None = cache(max_age=3600, no_cache=["Set-Cookie", "Authorization"])
        ... ):
        ...     return {"data": "conditional_cache"}

    Notes:
        - Conflicting directives (e.g., public and private) will both be set.
          Choose appropriate combinations based on your caching strategy.
        - no_store is the strongest directive and prevents all caching.
        - For CDNs, use s_maxage to set different TTLs for proxies vs browsers.
        - Use immutable with versioned URLs for maximum cache efficiency.
        - Combine stale_while_revalidate with max_age for better UX.
        - private and no_cache can accept field names to apply directives
          selectively to specific headers rather than the entire response.

    See Also:
        - RFC 9111: HTTP Caching (https://www.rfc-editor.org/rfc/rfc9111.html)
        - RFC 8246: HTTP Immutable Responses (https://www.rfc-editor.org/rfc/rfc8246.html)
        - RFC 5861: HTTP Cache-Control Extensions (https://www.rfc-editor.org/rfc/rfc5861.html)
    """

    def add_cache_headers(response: fastapi.Response) -> t.Any:
        """Add Cache-Control headers to the response."""
        directives: list[str] = []

        # IMPORTANT
        response.headers["Date"] = generate_http_date()

        # Add directives with values
        if max_age is not None:
            directives.append(f"max-age={max_age}")

        if s_maxage is not None:
            directives.append(f"s-maxage={s_maxage}")

        if stale_while_revalidate is not None:
            directives.append(f"stale-while-revalidate={stale_while_revalidate}")

        if stale_if_error is not None:
            directives.append(f"stale-if-error={stale_if_error}")

        # Add boolean directives
        if public:
            directives.append("public")

        # Handle private (can be bool or list of field names)
        if private is True:
            directives.append("private")
        elif isinstance(private, list) and private:
            field_names = ", ".join(private)
            directives.append(f'private="{field_names}"')

        # Handle no_cache (can be bool or list of field names)
        if no_cache is True:
            directives.append("no-cache")
        elif isinstance(no_cache, list) and no_cache:
            field_names = ", ".join(no_cache)
            directives.append(f'no-cache="{field_names}"')

        if no_store:
            directives.append("no-store")

        if no_transform:
            directives.append("no-transform")

        if must_revalidate:
            directives.append("must-revalidate")

        if must_understand:
            directives.append("must-understand")

        if proxy_revalidate:
            directives.append("proxy-revalidate")

        if immutable:
            directives.append("immutable")

        # Set the Cache-Control header if any directives were specified
        if directives:
            response.headers["Cache-Control"] = ", ".join(directives)

    return fastapi.Depends(add_cache_headers)
