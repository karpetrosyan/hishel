"""
Comprehensive pytest tests for HTTP Cache-Control parser.

Run with: pytest test_cache_control.py -v
"""

from hishel.beta._core._headers import CacheControl, parse_cache_control


class TestBasicParsing:
    """Test basic parsing functionality."""

    def test_empty_string(self):
        """Empty string should return default CacheControl."""
        cc = parse_cache_control("")
        assert cc.max_age is None
        assert cc.no_cache is None
        assert cc.no_store is False

    def test_whitespace_only(self):
        """Whitespace-only string should return default CacheControl."""
        cc = parse_cache_control("   ")
        assert cc.max_age is None
        assert cc.no_cache is None

    def test_single_directive(self):
        """Single directive without value."""
        cc = parse_cache_control("no-store")
        assert cc.no_store is True

    def test_multiple_directives(self):
        """Multiple directives separated by commas."""
        cc = parse_cache_control("no-store, no-transform, must-revalidate")
        assert cc.no_store is True
        assert cc.no_transform is True
        assert cc.must_revalidate is True


class TestMaxAge:
    """Test max-age directive [RFC9111, Section 5.2.1.1, 5.2.2.1]."""

    def test_max_age_valid(self):
        """Valid max-age value."""
        cc = parse_cache_control("max-age=3600")
        assert cc.max_age == 3600

    def test_max_age_zero(self):
        """max-age can be zero."""
        cc = parse_cache_control("max-age=0")
        assert cc.max_age == 0

    def test_max_age_large_value(self):
        """Large max-age value."""
        cc = parse_cache_control("max-age=31536000")
        assert cc.max_age == 31536000

    def test_max_age_overflow(self):
        """max-age should cap at max int32."""
        cc = parse_cache_control("max-age=9999999999999")
        assert cc.max_age == 2147483647

    def test_max_age_invalid(self):
        """Invalid max-age should result in None."""
        cc = parse_cache_control("max-age=invalid")
        assert cc.max_age is None

    def test_max_age_negative(self):
        """Negative max-age should result in None."""
        cc = parse_cache_control("max-age=-100")
        assert cc.max_age is None

    def test_max_age_with_other_directives(self):
        """max-age combined with other directives."""
        cc = parse_cache_control("max-age=3600, public, must-revalidate")
        assert cc.max_age == 3600
        assert cc.public is True
        assert cc.must_revalidate is True


class TestSMaxAge:
    """Test s-maxage directive [RFC9111, Section 5.2.2.10]."""

    def test_s_maxage_valid(self):
        """Valid s-maxage value."""
        cc = parse_cache_control("s-maxage=7200")
        assert cc.s_maxage == 7200

    def test_s_maxage_with_max_age(self):
        """s-maxage and max-age can coexist."""
        cc = parse_cache_control("max-age=3600, s-maxage=7200")
        assert cc.max_age == 3600
        assert cc.s_maxage == 7200

    def test_s_maxage_zero(self):
        """s-maxage can be zero."""
        cc = parse_cache_control("s-maxage=0")
        assert cc.s_maxage == 0

    def test_s_maxage_invalid(self):
        """Invalid s-maxage should result in None."""
        cc = parse_cache_control("s-maxage=bad")
        assert cc.s_maxage is None


class TestMaxStale:
    """Test max-stale directive [RFC9111, Section 5.2.1.2]."""

    def test_max_stale_with_value(self):
        """max-stale with specific value."""
        cc = parse_cache_control("max-stale=600")
        assert cc.max_stale == 600

    def test_max_stale_without_value(self):
        """max-stale without value means accept any stale."""
        cc = parse_cache_control("max-stale")
        assert cc.max_stale == 2147483647

    def test_max_stale_zero(self):
        """max-stale can be zero."""
        cc = parse_cache_control("max-stale=0")
        assert cc.max_stale == 0

    def test_max_stale_invalid(self):
        """Invalid max-stale should result in None."""
        cc = parse_cache_control("max-stale=xyz")
        assert cc.max_stale is None


class TestMinFresh:
    """Test min-fresh directive [RFC9111, Section 5.2.1.3]."""

    def test_min_fresh_valid(self):
        """Valid min-fresh value."""
        cc = parse_cache_control("min-fresh=300")
        assert cc.min_fresh == 300

    def test_min_fresh_zero(self):
        """min-fresh can be zero."""
        cc = parse_cache_control("min-fresh=0")
        assert cc.min_fresh == 0

    def test_min_fresh_invalid(self):
        """Invalid min-fresh should result in None."""
        cc = parse_cache_control("min-fresh=bad")
        assert cc.min_fresh is None


class TestNoCache:
    """Test no-cache directive [RFC9111, Section 5.2.1.4, 5.2.2.4]."""

    def test_no_cache_without_fields(self):
        """no-cache without field names."""
        cc = parse_cache_control("no-cache")
        assert cc.no_cache is True

    def test_no_cache_with_single_field(self):
        """no-cache with single field name."""
        cc = parse_cache_control('no-cache="Set-Cookie"')
        assert isinstance(cc.no_cache, list)
        assert "Set-Cookie" in cc.no_cache

    def test_no_cache_with_multiple_fields(self):
        """no-cache with multiple field names."""
        cc = parse_cache_control('no-cache="Set-Cookie, Authorization"')
        assert isinstance(cc.no_cache, list)
        assert "Set-Cookie" in cc.no_cache
        assert "Authorization" in cc.no_cache

    def test_no_cache_field_canonicalization(self):
        """Field names should be canonicalized to Title-Case."""
        cc = parse_cache_control('no-cache="set-cookie, authorization"')
        assert "Set-Cookie" in cc.no_cache
        assert "Authorization" in cc.no_cache

    def test_no_cache_with_whitespace(self):
        """no-cache with whitespace around field names."""
        cc = parse_cache_control('no-cache=" Set-Cookie , Authorization "')
        assert "Set-Cookie" in cc.no_cache
        assert "Authorization" in cc.no_cache


class TestPrivate:
    """Test private directive [RFC9111, Section 5.2.2.7]."""

    def test_private_without_fields(self):
        """private without field names."""
        cc = parse_cache_control("private")
        assert cc.private is True

    def test_private_with_single_field(self):
        """private with single field name."""
        cc = parse_cache_control('private="Set-Cookie"')
        assert isinstance(cc.private, list)
        assert "Set-Cookie" in cc.private

    def test_private_with_multiple_fields(self):
        """private with multiple field names."""
        cc = parse_cache_control('private="Set-Cookie, X-Custom-Header"')
        assert isinstance(cc.private, list)
        assert "Set-Cookie" in cc.private
        assert "X-Custom-Header" in cc.private

    def test_private_field_canonicalization(self):
        """Field names should be canonicalized."""
        cc = parse_cache_control('private="x-custom-header"')
        assert "X-Custom-Header" in cc.private


class TestBooleanDirectives:
    """Test boolean directives without values."""

    def test_no_store(self):
        """no-store directive [RFC9111, Section 5.2.1.5, 5.2.2.5]."""
        cc = parse_cache_control("no-store")
        assert cc.no_store is True

    def test_no_transform(self):
        """no-transform directive [RFC9111, Section 5.2.1.6, 5.2.2.6]."""
        cc = parse_cache_control("no-transform")
        assert cc.no_transform is True

    def test_only_if_cached(self):
        """only-if-cached directive [RFC9111, Section 5.2.1.7]."""
        cc = parse_cache_control("only-if-cached")
        assert cc.only_if_cached is True

    def test_must_revalidate(self):
        """must-revalidate directive [RFC9111, Section 5.2.2.2]."""
        cc = parse_cache_control("must-revalidate")
        assert cc.must_revalidate is True

    def test_must_understand(self):
        """must-understand directive [RFC9111, Section 5.2.2.3]."""
        cc = parse_cache_control("must-understand")
        assert cc.must_understand is True

    def test_public(self):
        """public directive [RFC9111, Section 5.2.2.9]."""
        cc = parse_cache_control("public")
        assert cc.public is True

    def test_proxy_revalidate(self):
        """proxy-revalidate directive [RFC9111, Section 5.2.2.8]."""
        cc = parse_cache_control("proxy-revalidate")
        assert cc.proxy_revalidate is True

    def test_immutable(self):
        """immutable directive [RFC8246]."""
        cc = parse_cache_control("immutable")
        assert cc.immutable is True


class TestExperimentalDirectives:
    """Test experimental directives from RFC5861."""

    def test_stale_if_error(self):
        """stale-if-error directive [RFC5861, Section 4]."""
        cc = parse_cache_control("stale-if-error=86400")
        assert cc.stale_if_error == 86400

    def test_stale_if_error_invalid(self):
        """Invalid stale-if-error value."""
        cc = parse_cache_control("stale-if-error=bad")
        assert cc.stale_if_error is None

    def test_stale_while_revalidate(self):
        """stale-while-revalidate directive [RFC5861, Section 3]."""
        cc = parse_cache_control("stale-while-revalidate=120")
        assert cc.stale_while_revalidate == 120

    def test_stale_while_revalidate_invalid(self):
        """Invalid stale-while-revalidate value."""
        cc = parse_cache_control("stale-while-revalidate=xyz")
        assert cc.stale_while_revalidate is None


class TestExtensions:
    """Test handling of unrecognized directives."""

    def test_unknown_directive_without_value(self):
        """Unknown directive without value."""
        cc = parse_cache_control("custom-directive")
        assert "custom-directive" in cc.extensions

    def test_unknown_directive_with_value(self):
        """Unknown directive with value."""
        cc = parse_cache_control("custom-directive=value")
        assert "custom-directive=value" in cc.extensions

    def test_multiple_extensions(self):
        """Multiple unknown directives."""
        cc = parse_cache_control("ext1=val1, ext2, ext3=val3")
        assert "ext1=val1" in cc.extensions
        assert "ext2" in cc.extensions
        assert "ext3=val3" in cc.extensions

    def test_extensions_with_known_directives(self):
        """Mix of known and unknown directives."""
        cc = parse_cache_control("max-age=3600, custom-ext=foo, no-cache")
        assert cc.max_age == 3600
        assert cc.no_cache is True
        assert "custom-ext=foo" in cc.extensions


class TestQuotedValues:
    """Test handling of quoted values."""

    def test_quoted_field_names(self):
        """Quoted field names in no-cache."""
        cc = parse_cache_control('no-cache="Set-Cookie"')
        assert "Set-Cookie" in cc.no_cache

    def test_quoted_extension_value(self):
        """Quoted extension value."""
        cc = parse_cache_control('custom="quoted value"')
        assert "custom=quoted value" in cc.extensions

    def test_escaped_quotes_in_value(self):
        """Escaped quotes within quoted value."""
        cc = parse_cache_control('custom="value with \\"quotes\\""')
        assert any('value with "quotes"' in ext for ext in cc.extensions)


class TestWhitespaceHandling:
    """Test handling of whitespace."""

    def test_spaces_around_commas(self):
        """Spaces around commas."""
        cc = parse_cache_control("max-age=3600 , no-cache , public")
        assert cc.max_age == 3600
        assert cc.no_cache is True
        assert cc.public is True

    def test_spaces_around_equals(self):
        """Spaces around equals sign."""
        cc = parse_cache_control("max-age = 3600")
        assert cc.max_age == 3600

    def test_leading_trailing_spaces(self):
        """Leading and trailing spaces."""
        cc = parse_cache_control("  max-age=3600, no-cache  ")
        assert cc.max_age == 3600
        assert cc.no_cache is True

    def test_multiple_spaces(self):
        """Multiple consecutive spaces."""
        cc = parse_cache_control("max-age=3600,    no-cache,   public")
        assert cc.max_age == 3600
        assert cc.no_cache is True
        assert cc.public is True


class TestRequestDirectives:
    """Test typical request Cache-Control headers."""

    def test_request_no_cache(self):
        """Request with no-cache."""
        cc = parse_cache_control("no-cache")
        assert cc.no_cache is True

    def test_request_max_age_zero(self):
        """Request with max-age=0 (force revalidation)."""
        cc = parse_cache_control("max-age=0")
        assert cc.max_age == 0

    def test_request_no_store(self):
        """Request with no-store."""
        cc = parse_cache_control("no-store")
        assert cc.no_store is True

    def test_request_max_age_and_max_stale(self):
        """Request with max-age and max-stale."""
        cc = parse_cache_control("max-age=600, max-stale=300")
        assert cc.max_age == 600
        assert cc.max_stale == 300

    def test_request_only_if_cached(self):
        """Request with only-if-cached."""
        cc = parse_cache_control("only-if-cached")
        assert cc.only_if_cached is True

    def test_request_min_fresh(self):
        """Request with min-fresh."""
        cc = parse_cache_control("min-fresh=300")
        assert cc.min_fresh == 300


class TestResponseDirectives:
    """Test typical response Cache-Control headers."""

    def test_response_public_max_age(self):
        """Public cacheable response."""
        cc = parse_cache_control("public, max-age=3600")
        assert cc.public is True
        assert cc.max_age == 3600

    def test_response_private(self):
        """Private response."""
        cc = parse_cache_control("private, max-age=0")
        assert cc.private is True
        assert cc.max_age == 0

    def test_response_no_cache_must_revalidate(self):
        """Response requiring revalidation."""
        cc = parse_cache_control("no-cache, must-revalidate")
        assert cc.no_cache is True
        assert cc.must_revalidate is True

    def test_response_immutable(self):
        """Immutable response."""
        cc = parse_cache_control("public, max-age=31536000, immutable")
        assert cc.public is True
        assert cc.max_age == 31536000
        assert cc.immutable is True

    def test_response_s_maxage(self):
        """Response with s-maxage for shared caches."""
        cc = parse_cache_control("public, max-age=600, s-maxage=3600")
        assert cc.public is True
        assert cc.max_age == 600
        assert cc.s_maxage == 3600

    def test_response_proxy_revalidate(self):
        """Response with proxy-revalidate."""
        cc = parse_cache_control("public, max-age=3600, proxy-revalidate")
        assert cc.public is True
        assert cc.max_age == 3600
        assert cc.proxy_revalidate is True

    def test_response_must_understand(self):
        """Response with must-understand."""
        cc = parse_cache_control("must-understand, no-store")
        assert cc.must_understand is True
        assert cc.no_store is True


class TestRealWorldExamples:
    """Test real-world Cache-Control header examples."""

    def test_cdn_static_asset(self):
        """Typical CDN static asset header."""
        cc = parse_cache_control("public, max-age=31536000, immutable")
        assert cc.public is True
        assert cc.max_age == 31536000
        assert cc.immutable is True

    def test_api_no_cache(self):
        """API endpoint that shouldn't be cached."""
        cc = parse_cache_control("no-store, no-cache, must-revalidate, proxy-revalidate")
        assert cc.no_store is True
        assert cc.no_cache is True
        assert cc.must_revalidate is True
        assert cc.proxy_revalidate is True

    def test_private_user_data(self):
        """Private user data response."""
        cc = parse_cache_control("private, max-age=0, no-cache")
        assert cc.private is True
        assert cc.max_age == 0
        assert cc.no_cache is True

    def test_cdn_with_stale_while_revalidate(self):
        """CDN with stale-while-revalidate."""
        cc = parse_cache_control("max-age=3600, stale-while-revalidate=86400")
        assert cc.max_age == 3600
        assert cc.stale_while_revalidate == 86400

    def test_cdn_with_stale_if_error(self):
        """CDN with stale-if-error fallback."""
        cc = parse_cache_control("max-age=600, stale-if-error=86400")
        assert cc.max_age == 600
        assert cc.stale_if_error == 86400

    def test_aws_cloudfront_example(self):
        """AWS CloudFront example header."""
        cc = parse_cache_control("public, max-age=0, s-maxage=2592000")
        assert cc.public is True
        assert cc.max_age == 0
        assert cc.s_maxage == 2592000

    def test_github_static_asset(self):
        """GitHub static asset header."""
        cc = parse_cache_control("max-age=31536000, immutable")
        assert cc.max_age == 31536000
        assert cc.immutable is True


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_duplicate_directives(self):
        """Duplicate directives (last one wins for values)."""
        cc = parse_cache_control("max-age=100, max-age=200")
        assert cc.max_age == 200

    def test_case_insensitive_directives(self):
        """Directives should be case-insensitive."""
        cc = parse_cache_control("MAX-AGE=3600, NO-CACHE, PUBLIC")
        assert cc.max_age == 3600
        assert cc.no_cache is True
        assert cc.public is True

    def test_empty_directive(self):
        """Empty directive between commas."""
        cc = parse_cache_control("max-age=3600,, no-cache")
        assert cc.max_age == 3600
        assert cc.no_cache is True

    def test_directive_with_empty_value(self):
        """Directive with empty value."""
        cc = parse_cache_control("max-age=")
        assert cc.max_age is None

    def test_malformed_equals(self):
        """Multiple equals signs."""
        cc = parse_cache_control("max-age==3600")
        # Should handle gracefully
        assert isinstance(cc, CacheControl)

    def test_only_commas(self):
        """String with only commas."""
        cc = parse_cache_control(",,,")
        assert cc.max_age is None
        assert cc.no_cache is None

    def test_trailing_comma(self):
        """Trailing comma."""
        cc = parse_cache_control("max-age=3600, no-cache,")
        assert cc.max_age == 3600
        assert cc.no_cache is True

    def test_leading_comma(self):
        """Leading comma."""
        cc = parse_cache_control(",max-age=3600, no-cache")
        assert cc.max_age == 3600
        assert cc.no_cache is True


class TestComplexCombinations:
    """Test complex combinations of directives."""

    def test_all_request_directives(self):
        """Combine all request directives."""
        cc = parse_cache_control(
            "max-age=100, max-stale=200, min-fresh=300, no-cache, no-store, no-transform, only-if-cached"
        )
        assert cc.max_age == 100
        assert cc.max_stale == 200
        assert cc.min_fresh == 300
        assert cc.no_cache is True
        assert cc.no_store is True
        assert cc.no_transform is True
        assert cc.only_if_cached is True

    def test_all_response_directives(self):
        """Combine multiple response directives."""
        cc = parse_cache_control("public, max-age=3600, s-maxage=7200, must-revalidate, proxy-revalidate, immutable")
        assert cc.public is True
        assert cc.max_age == 3600
        assert cc.s_maxage == 7200
        assert cc.must_revalidate is True
        assert cc.proxy_revalidate is True
        assert cc.immutable is True

    def test_mixed_with_extensions(self):
        """Mix standard directives with extensions."""
        cc = parse_cache_control("max-age=3600, custom-ext=foo, no-cache, another-ext, stale-while-revalidate=120")
        assert cc.max_age == 3600
        assert cc.no_cache is True
        assert cc.stale_while_revalidate == 120
        assert "custom-ext=foo" in cc.extensions
        assert "another-ext" in cc.extensions


class TestDefaultValues:
    """Test that unset directives have correct default values."""

    def test_all_defaults(self):
        """Check all default values for empty header."""
        cc = parse_cache_control("")

        # Time-based directives should be None
        assert cc.max_age is None
        assert cc.max_stale is None
        assert cc.min_fresh is None
        assert cc.s_maxage is None
        assert cc.stale_if_error is None
        assert cc.stale_while_revalidate is None

        # Boolean directives should be False
        assert cc.no_store is False
        assert cc.no_transform is False
        assert cc.only_if_cached is False
        assert cc.must_revalidate is False
        assert cc.must_understand is False
        assert cc.public is False
        assert cc.proxy_revalidate is False
        assert cc.immutable is False

        # Special directives should be None
        assert cc.no_cache is None
        assert cc.private is None

        # Extensions should be empty list
        assert cc.extensions == []
