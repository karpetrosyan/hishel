import pytest

from hishel import CacheControl, ParseError, ValidationError, Vary


class TestParsingErrors:

    def test_blank_directive(self):
        header = [","]
        with pytest.raises(ParseError, match="The directive should not be left blank."):
            CacheControl.from_value(header)

    def test_blank_directive_after_ows_stripping(self):
        header = [" ,"]
        with pytest.raises(ParseError, match="The directive should not contain only whitespaces."):
            CacheControl.from_value(header)

    def test_invalid_key_symbol(self):
        header = ["\x12 ,"]
        with pytest.raises(ParseError, match=r"The character ''\\x12'' is not permitted in the directive name."):
            CacheControl.from_value(header)

    def test_blank_directive_value(self):
        header = ["max-age= ,"]
        with pytest.raises(ParseError, match="The directive value cannot be left blank."):
            CacheControl.from_value(header)

    def test_blank_invalid_quotes(self):
        header = ["max-age=\"123,"]
        with pytest.raises(ParseError, match="Invalid quotes around the value."):
            CacheControl.from_value(header)

    def test_invalid_symbol_in_unquoted(self):
        header = ["max-age=1\x123,"]
        with pytest.raises(ParseError, match=r"The character ''\\x12'' is not permitted for the unquoted values."):
            CacheControl.from_value(header)

    def test_invalid_symbol_in_quoted(self):
        header = ["max-age=\"\x123\","]
        with pytest.raises(ParseError, match=r"The character ''\\x12'' is not permitted for the quoted values."):
            CacheControl.from_value(header)


class TestValidationErrors:

    def test_time_field_without_value(self):
        header = ["max-age"]
        with pytest.raises(ValidationError, match="The directive 'max_age' necessitates a value."):
            CacheControl.from_value(header)

    def test_time_field_with_quote(self):
        header = ["max-age=\"123\""]
        with pytest.raises(ValidationError, match="The argument 'max_age' should be an "
                                                  "integer, but a quote was found."):
            CacheControl.from_value(header)

    def test_time_field_invalid_int(self):
        header = ["max-age=123t1"]
        with pytest.raises(ValidationError, match="The argument 'max_age' should be an integer, but got ''123t1''."):
            CacheControl.from_value(header)

    def test_boolean_fields_with_value(self):
        header = ["no-store=1"]
        with pytest.raises(ValidationError, match="The directive 'no_store' should have no value, but it does."):
            CacheControl.from_value(header)

    def test_list_value_empty(self):
        header = ["no-cache=\",\" "]
        with pytest.raises(ValidationError, match="The list value must not be empty."):
            CacheControl.from_value(header)

class TestCacheControl:

    def test_single_directive_parsing(self):
        header = ["max-age=3600"]
        cache_control = CacheControl.from_value(header)
        assert cache_control.max_age == 3600

    def test_multiple_directives_parsing(self):
        header = ["max-age=3600", "s-maxage=3600"]
        cache_control = CacheControl.from_value(header)
        assert cache_control.max_age == 3600
        assert cache_control.s_maxage == 3600

    def test_boolean_directives_parsing(self):
        header = ["no-store", "public"]
        cache_control = CacheControl.from_value(header)
        assert cache_control.no_store
        assert cache_control.public

    def test_list_directives_parsing(self):
        header = ["no-cache=\"age, authorization\""]
        cache_control = CacheControl.from_value(header)
        assert cache_control.no_cache == ["age", "authorization"]

    def test_multiple_list_directives_parsing(self):
        header = ["no-cache=\"age, authorization\"", "private=\"age, authorization\""]
        cache_control = CacheControl.from_value(header)
        assert cache_control.no_cache == ["age", "authorization"]
        assert cache_control.private == ["age", "authorization"]

    def test_blank_list_directives(self):
        header = ["no-cache, private"]
        cache_control = CacheControl.from_value(header)
        assert cache_control.no_cache == True  # noqa: E712
        assert cache_control.private == True  # noqa: E712

class TestVary:

    def test_single_vary_header(self):
        header = ["Accept, Location"]
        vary = Vary.from_value(header)
        assert vary._values == ["Accept", "Location"]

    def test_multiple_vary_headers(self):
        header = ["Accept", "Location"]
        vary = Vary.from_value(header)
        assert vary._values == ["Accept", "Location"]

    def test_multiple_vary_headers_with_multiple_values(self):
        header = ["Accept, Location", "Transfer-Encoding"]
        vary = Vary.from_value(header)
        assert vary._values == ["Accept", "Location", "Transfer-Encoding"]
