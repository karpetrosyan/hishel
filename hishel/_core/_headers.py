from __future__ import annotations

from dataclasses import dataclass
from typing import (
    Any,
    Iterator,
    List,
    Literal,
    Mapping,
    MutableMapping,
    Optional,
    Union,
    cast,
)

"""
HTTP token and quoted-string parsing utilities.

These functions implement RFC 7230 parsing rules for HTTP/1.1 tokens
and quoted strings.
"""


def is_char(c: str) -> bool:
    """
    Check if character is a valid ASCII character (0-127).

    Per RFC 7230: CHAR = any US-ASCII character (octets 0 - 127)

    Args:
        c: Single character string

    Returns:
        True if character is valid ASCII (0-127), False otherwise
    """
    if not c:
        return False
    return ord(c) <= 127


def is_ctl(c: str) -> bool:
    """
    Check if character is a control character.

    Per RFC 7230: CTL = control characters (0-31 and 127)

    Args:
        c: Single character string

    Returns:
        True if character is a control character, False otherwise
    """
    if not c:
        return False
    b = ord(c)
    return b <= 31 or b == 127


def is_separator(c: str) -> bool:
    """
    Check if character is an HTTP separator.

    Per RFC 2616 Section 2.2:
    separators = "(" | ")" | "<" | ">" | "@"
               | "," | ";" | ":" | "\" | <">
               | "/" | "[" | "]" | "?" | "="
               | "{" | "}" | SP | HT

    Args:
        c: Single character string

    Returns:
        True if character is a separator, False otherwise
    """
    if not c:
        return False
    return c in '()<>@,;:\\"/[]?={} \t'


def is_token(c: str) -> bool:
    """
    Check if character is valid in an HTTP token.

    Per RFC 7230 Section 3.2.6:
    token = 1*tchar
    tchar = "!" / "#" / "$" / "%" / "&" / "'" / "*"
          / "+" / "-" / "." / "0"-"9" / "A"-"Z"
          / "^" / "_" / "`" / "a"-"z" / "|" / "~"

    Implementation: token chars are CHAR but not CTL or separators

    Args:
        c: Single character string

    Returns:
        True if character is valid in a token, False otherwise

    Examples:
        >>> is_token('a')
        True
        >>> is_token('Z')
        True
        >>> is_token('5')
        True
        >>> is_token('-')
        True
        >>> is_token('!')
        True
        >>> is_token(' ')
        False
        >>> is_token(',')
        False
        >>> is_token('=')
        False
    """
    return is_char(c) and not is_ctl(c) and not is_separator(c)


def is_qd_text(c: str) -> bool:
    r"""
    Check if character is valid in quoted-text.

    Per RFC 7230 Section 3.2.6:
    quoted-string = DQUOTE *( qdtext / quoted-pair ) DQUOTE
    qdtext = HTAB / SP / %x21 / %x23-5B / %x5D-7E / obs-text
    obs-text = %x80-FF

    In other words:
    - HTAB (0x09)
    - SP (0x20)
    - 0x21 (!)
    - 0x23-0x5B (# to [, excluding " which is 0x22)
    - 0x5D-0x7E (] to ~, excluding \ which is 0x5C)
    - 0x80-0xFF (obs-text, extended ASCII)

    Args:
        c: Single character string

    Returns:
        True if character is valid quoted-text, False otherwise
    """
    if not c:
        return False

    b = ord(c)
    return (
        b == 0x09  # HTAB
        or b == 0x20  # SP
        or b == 0x21  # !
        or (0x23 <= b <= 0x5B)  # # to [ (skips " which is 0x22)
        or (0x5D <= b <= 0x7E)  # ] to ~ (skips \ which is 0x5C)
        or b >= 0x80
    )  # obs-text


def http_unquote_pair(c: str) -> str:
    """
    Unquote a single escaped character from a quoted-pair.

    Per RFC 7230 Section 3.2.6:
    quoted-pair = "\" ( HTAB / SP / VCHAR / obs-text )
    VCHAR = visible characters (0x21-0x7E)

    Valid escaped characters:
    - HTAB (0x09)
    - SP (0x20)
    - VCHAR (0x21-0x7E)
    - obs-text (0x80-0xFF)

    Invalid characters are replaced with '?'

    Args:
        c: Single character string (the character after the backslash)

    Returns:
        The unquoted character, or '?' if invalid

    Examples:
        >>> http_unquote_pair('"')
        '"'
        >>> http_unquote_pair('n')
        'n'
        >>> http_unquote_pair('\\')
        '\\'
    """
    if not c:
        return "?"

    b = ord(c)
    # Valid characters that can be escaped
    if b == 0x09 or b == 0x20 or (0x21 <= b <= 0x7E) or b >= 0x80:
        return c
    return "?"


def http_unquote(raw: str) -> tuple[int, str]:
    """
    Unquote an HTTP quoted-string.

    Per RFC 7230 Section 3.2.6:
    quoted-string = DQUOTE *( qdtext / quoted-pair ) DQUOTE
    quoted-pair = "\" ( HTAB / SP / VCHAR / obs-text )

    The raw string must begin with a double quote ("). Only the first
    quoted string is parsed. The function returns the number of characters
    consumed and the unquoted result.

    Args:
        raw: String that must start with a double quote

    Returns:
        Tuple of (eaten, result) where:
        - eaten: number of characters consumed, or -1 on failure
        - result: the unquoted string, or empty string on failure

    Examples:
        >>> http_unquote('"hello"')
        (7, 'hello')
        >>> http_unquote('"hello world"')
        (13, 'hello world')
        >>> http_unquote('"hello\\"world"')
        (14, 'hello"world')
        >>> http_unquote('"test')
        (-1, '')
        >>> http_unquote('not quoted')
        (-1, '')
    """
    if not raw or raw[0] != '"':
        return -1, ""

    buf: list[str] = []
    i = 1  # Start after opening quote

    while i < len(raw):
        b = raw[i]

        if b == '"':
            # Found closing quote - success
            return i + 1, "".join(buf)

        elif b == "\\":
            # Escaped character (quoted-pair)
            if i + 1 >= len(raw):
                # Backslash at end of string - invalid
                return -1, ""

            # Unquote the next character
            buf.append(http_unquote_pair(raw[i + 1]))
            i += 2  # Skip both backslash and escaped char

        else:
            # Regular character
            if is_qd_text(b):
                buf.append(b)
            else:
                # Invalid character in quoted text
                buf.append("?")
            i += 1

    # Reached end without finding closing quote - invalid
    return -1, ""


class Headers(MutableMapping[str, str]):
    def __init__(self, headers: Mapping[str, Union[str, List[str]]]) -> None:
        self._headers = {k.lower(): ([v] if isinstance(v, str) else v[:]) for k, v in headers.items()}

    def get_list(self, key: str) -> Optional[List[str]]:
        return self._headers.get(key.lower(), None)

    def __getitem__(self, key: str) -> str:
        return ", ".join(self._headers[key.lower()])

    def __setitem__(self, key: str, value: str) -> None:
        self._headers.setdefault(key.lower(), []).append(value)

    def __delitem__(self, key: str) -> None:
        del self._headers[key.lower()]

    def __iter__(self) -> Iterator[str]:
        return iter(self._headers)

    def __len__(self) -> int:
        return len(self._headers)

    def __repr__(self) -> str:
        return repr(self._headers)

    def __str__(self) -> str:
        return str(self._headers)

    def __eq__(self, other_headers: Any) -> bool:
        return isinstance(other_headers, Headers) and self._headers == other_headers._headers  # type: ignore


class Vary:
    def __init__(self, values: List[str]) -> None:
        self.values = values

    @classmethod
    def from_value(cls, vary_value: str) -> "Vary":
        values = []

        for field_name in vary_value.split(","):
            field_name = field_name.strip()
            values.append(field_name)
        return Vary(values)


@dataclass
class Range:
    unit: Literal["bytes"]
    range: tuple[int | None, int | None]

    @classmethod
    def try_from_str(cls, range_header: str) -> "Range" | None:
        # Example: "bytes=0-99,200-299,-500,100-"
        unit, values = range_header.split("=")
        unit = unit.strip()
        parts = [p.strip() for p in values.split(",")]

        parsed: list[tuple[int | None, int | None]] = []
        for part in parts:
            if "-" not in part:
                raise ValueError(f"Invalid range part: {part}")
            start_str, end_str = part.split("-", 1)
            start = int(start_str) if start_str else None
            end = int(end_str) if end_str else None
            parsed.append((start, end))

        if len(parsed) != 1:
            # we don't support multiple ranges
            return None

        return cls(
            unit=cast(Literal["bytes"], unit),
            range=parsed[0],
        )


class CacheControl:
    """
    Unified Cache-Control directives for both requests and responses.

    Supports all standard directives from RFC9111 and experimental directives.
    Uses None for unset values instead of -1.

    Supported Directives:
    - immutable [RFC8246]
    - max-age [RFC9111, Section 5.2.1.1, 5.2.2.1]
    - max-stale [RFC9111, Section 5.2.1.2]
    - min-fresh [RFC9111, Section 5.2.1.3]
    - must-revalidate [RFC9111, Section 5.2.2.2]
    - must-understand [RFC9111, Section 5.2.2.3]
    - no-cache [RFC9111, Section 5.2.1.4, 5.2.2.4]
    - no-store [RFC9111, Section 5.2.1.5, 5.2.2.5]
    - no-transform [RFC9111, Section 5.2.1.6, 5.2.2.6]
    - only-if-cached [RFC9111, Section 5.2.1.7]
    - private [RFC9111, Section 5.2.2.7]
    - proxy-revalidate [RFC9111, Section 5.2.2.8]
    - public [RFC9111, Section 5.2.2.9]
    - s-maxage [RFC9111, Section 5.2.2.10]
    - stale-if-error [RFC5861, Section 4]
    - stale-while-revalidate [RFC5861, Section 3]

    no_cache and private can be:
        - None: directive not present
        - True: directive present without field names
        - List[str]: directive present with specific field names
    """

    def __init__(self) -> None:
        # Common directives
        self.max_age: Optional[int] = None
        self.no_store: bool = False
        self.no_transform: bool = False

        # Request-specific
        self.max_stale: Optional[int] = None
        self.min_fresh: Optional[int] = None
        self.only_if_cached: bool = False

        # Response-specific
        self.must_revalidate: bool = False
        self.must_understand: bool = False
        self.public: bool = False
        self.proxy_revalidate: bool = False
        self.s_maxage: Optional[int] = None
        self.immutable: bool = False

        # Can be boolean or contain field names
        self.no_cache: Union[bool, List[str]] = False
        self.private: Union[bool, List[str]] = False

        # Experimental
        self.stale_if_error: Optional[int] = None
        self.stale_while_revalidate: Optional[int] = None

        # Extensions (unrecognized directives)
        self.extensions: List[str] = []


def parse_int_value(value: str) -> Optional[int]:
    """Parse integer value, return None if invalid."""
    try:
        val = int(value)
        # Cap at max int32 for compatibility
        return min(val, 2147483647) if val >= 0 else None
    except (ValueError, OverflowError):
        return None


def parse_field_names(value: str) -> List[str]:
    """Parse comma-separated field names and canonicalize them."""
    fields = []
    for field in value.split(","):
        field = field.strip()
        if field:
            # Convert to canonical header form (Title-Case)
            canonical = "-".join(word.capitalize() for word in field.split("-"))
            fields.append(canonical)
    return fields


def has_field_names(token: str) -> bool:
    """Check if token can have comma-separated field names."""
    return token in ("no-cache", "private")


def parse(value: str) -> CacheControl:
    """
    Parse a Cache-Control header value character by character.

    This parser handles quoted values and field names correctly,
    allowing commas within field name lists.

    Args:
        value: The Cache-Control header value string

    Returns:
        CacheControl object with parsed directives
    """
    cc = CacheControl()

    if not value:
        return cc

    i = 0
    length = len(value)

    while i < length:
        # Skip leading whitespace and commas
        while i < length and (value[i] in (" ", "\t", ",")):
            i += 1

        if i >= length:
            break

        # Find end of token
        j = i
        while j < length and is_token(value[j]):
            j += 1

        if j == i:
            # No valid token found, skip this character
            i += 1
            continue

        token = value[i:j].lower()
        token_has_fields = has_field_names(token)

        # Skip whitespace after token
        while j < length and value[j] in (" ", "\t"):
            j += 1

        # Check if token has a value (token=value)
        if j < length and value[j] == "=":
            k = j + 1

            # Skip whitespace after equals sign
            while k < length and value[k] in (" ", "\t"):
                k += 1

            if k >= length:
                # Directive ends with '=' but no value
                i = k
                continue

            # Check for quoted value
            if value[k] == '"':
                eaten, result = http_unquote(value[k:])
                if eaten == -1:
                    # Quote mismatch, skip to next directive
                    i = k + 1
                    continue

                i = k + eaten
                handle_directive_with_value(cc, token, result)
            else:
                # Unquoted value
                z = k
                while z < length:
                    if token_has_fields:
                        # For directives with field names, stop only at whitespace
                        if value[z] in (" ", "\t"):
                            break
                    else:
                        # For other directives, stop at whitespace or comma
                        if value[z] in (" ", "\t", ","):
                            break
                    z += 1

                result = value[k:z]

                # Remove trailing comma if present
                if result and result[-1] == ",":
                    result = result[:-1]

                i = z
                handle_directive_with_value(cc, token, result)
        else:
            # Token without value
            handle_directive_without_value(cc, token)
            i = j

    return cc


def handle_directive_with_value(cc: CacheControl, token: str, value: str) -> None:
    """Handle a directive that has a value."""
    if token == "max-age":
        cc.max_age = parse_int_value(value)

    elif token == "s-maxage":
        cc.s_maxage = parse_int_value(value)

    elif token == "max-stale":
        cc.max_stale = parse_int_value(value)

    elif token == "min-fresh":
        cc.min_fresh = parse_int_value(value)

    elif token == "stale-if-error":
        cc.stale_if_error = parse_int_value(value)

    elif token == "stale-while-revalidate":
        cc.stale_while_revalidate = parse_int_value(value)

    elif token == "no-cache":
        # no-cache with field names
        cc.no_cache = parse_field_names(value)

    elif token == "private":
        # private with field names
        cc.private = parse_field_names(value)

    else:
        # Unrecognized directive with value
        cc.extensions.append(f"{token}={value}")


def handle_directive_without_value(cc: CacheControl, token: str) -> None:
    """Handle a directive that doesn't have a value."""
    if token == "max-stale":
        # max-stale without value means accept any stale response
        cc.max_stale = 2147483647  # max int32

    elif token == "no-cache":
        cc.no_cache = True

    elif token == "private":
        cc.private = True

    elif token == "no-store":
        cc.no_store = True

    elif token == "no-transform":
        cc.no_transform = True

    elif token == "only-if-cached":
        cc.only_if_cached = True

    elif token == "must-revalidate":
        cc.must_revalidate = True

    elif token == "must-understand":
        cc.must_understand = True

    elif token == "public":
        cc.public = True

    elif token == "proxy-revalidate":
        cc.proxy_revalidate = True

    elif token == "immutable":
        cc.immutable = True

    else:
        # Unrecognized directive without value
        cc.extensions.append(token)


def parse_cache_control(value: str | None) -> CacheControl:
    """
    Parse a Cache-Control header from either a request or response.

    This is the main entry point for parsing.

    Args:
        value: The Cache-Control header value

    Returns:
        CacheControl object containing all parsed directives

    Examples:
        >>> # Response example
        >>> cc = parse_cache_control("public, max-age=3600, must-revalidate")
        >>> cc.public
        True
        >>> cc.max_age
        3600
        >>> cc.must_revalidate
        True

        >>> # Request example
        >>> cc = parse_cache_control("max-age=0, no-cache")
        >>> cc.max_age
        0
        >>> cc.no_cache
        True

        >>> # With field names
        >>> cc = parse_cache_control('no-cache="Set-Cookie, Authorization"')
        >>> cc.no_cache
        ['Set-Cookie', 'Authorization']

        >>> # Experimental directives
        >>> cc = parse_cache_control("immutable, stale-while-revalidate=86400")
        >>> cc.immutable
        True
        >>> cc.stale_while_revalidate
        86400
    """
    if value is None:
        return CacheControl()
    return parse(value)
