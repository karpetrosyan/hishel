import pytest

from hishel import ParseError, ValidationError, Vary
from hishel._headers import parse_cache_control


def test_blank_directive():
    header = [","]
    with pytest.raises(ParseError, match="The directive should not be left blank."):
        parse_cache_control(header)

def test_blank_directive_after_ows_stripping():
    header = [" ,"]
    with pytest.raises(ParseError, match="The directive should not contain only whitespaces."):
        parse_cache_control(header)

def test_invalid_key_symbol():
    header = ["\x12 ,"]
    with pytest.raises(ParseError, match=r"The character ''\\x12'' is not permitted in the directive name."):
        parse_cache_control(header)

def test_blank_directive_value():
    header = ["max-age= ,"]
    with pytest.raises(ParseError, match="The directive value cannot be left blank."):
        parse_cache_control(header)

def test_blank_invalid_quotes():
    header = ["max-age=\"123,"]
    with pytest.raises(ParseError, match="Invalid quotes around the value."):
        parse_cache_control(header)

def test_invalid_symbol_in_unquoted():
    header = ["max-age=1\x123,"]
    with pytest.raises(ParseError, match=r"The character ''\\x12'' is not permitted for the unquoted values."):
        parse_cache_control(header)

def test_invalid_symbol_in_quoted():
    header = ["max-age=\"\x123\","]
    with pytest.raises(ParseError, match=r"The character ''\\x12'' is not permitted for the quoted values."):
        parse_cache_control(header)



def test_time_field_without_value():
    header = ["max-age"]
    with pytest.raises(ValidationError, match="The directive 'max_age' necessitates a value."):
        parse_cache_control(header)

def test_time_field_with_quote():
    header = ["max-age=\"123\""]
    with pytest.raises(ValidationError, match="The argument 'max_age' should be an "
                                                "integer, but a quote was found."):
        parse_cache_control(header)

def test_time_field_invalid_int():
    header = ["max-age=123t1"]
    with pytest.raises(ValidationError, match="The argument 'max_age' should be an integer, but got ''123t1''."):
        parse_cache_control(header)

def test_boolean_fields_with_value():
    header = ["no-store=1"]
    with pytest.raises(ValidationError, match="The directive 'no_store' should have no value, but it does."):
        parse_cache_control(header)

def test_list_value_empty():
    header = ["no-cache=\",\" "]
    with pytest.raises(ValidationError, match="The list value must not be empty."):
        parse_cache_control(header)


def test_single_directive_parsing():
    header = ["max-age=3600"]
    cache_control = parse_cache_control(header)
    assert cache_control.max_age == 3600

def test_multiple_directives_parsing():
    header = ["max-age=3600", "s-maxage=3600"]
    cache_control = parse_cache_control(header)
    assert cache_control.max_age == 3600
    assert cache_control.s_maxage == 3600

def test_boolean_directives_parsing():
    header = ["no-store", "public"]
    cache_control = parse_cache_control(header)
    assert cache_control.no_store
    assert cache_control.public

def test_list_directives_parsing():
    header = ["no-cache=\"age, authorization\""]
    cache_control = parse_cache_control(header)
    assert cache_control.no_cache == ["age", "authorization"]

def test_multiple_list_directives_parsing():
    header = ["no-cache=\"age, authorization\"", "private=\"age, authorization\""]
    cache_control = parse_cache_control(header)
    assert cache_control.no_cache == ["age", "authorization"]
    assert cache_control.private == ["age", "authorization"]

def test_blank_list_directives():
    header = ["no-cache, private"]
    cache_control = parse_cache_control(header)
    assert cache_control.no_cache == True  # noqa: E712
    assert cache_control.private == True  # noqa: E712


def test_single_vary_header():
    header = ["Accept, Location"]
    vary = Vary.from_value(header)
    assert vary._values == ["Accept", "Location"]

def test_multiple_vary_headers():
    header = ["Accept", "Location"]
    vary = Vary.from_value(header)
    assert vary._values == ["Accept", "Location"]

def test_multiple_vary_headers_with_multiple_values():
    header = ["Accept, Location", "Transfer-Encoding"]
    vary = Vary.from_value(header)
    assert vary._values == ["Accept", "Location", "Transfer-Encoding"]
