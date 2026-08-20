"""Restricted RFC 8785 JSON Canonicalization Scheme support.

The protocol wire format currently permits only JSON integers in the I-JSON exact
integer range.  This module implements the complete RFC 8785 behavior for that
allowed number subset and deliberately rejects every floating-point value.  Adding
RFC 8785 floating-point serialization later requires a separately reviewed and
versioned implementation; silently using Python's float formatting is forbidden.

Canonical output is UTF-8, contains no BOM, and has no trailing line feed.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Iterable, Tuple, Union


IJSON_INTEGER_MIN = -(2**53) + 1
IJSON_INTEGER_MAX = (2**53) - 1


class CanonicalizationError(ValueError):
    """Raised when input is outside the protocol's canonical JSON subset."""


class DuplicateKeyError(CanonicalizationError):
    """Raised when a parsed JSON object contains a duplicate member name."""


class UnsupportedNumberError(CanonicalizationError):
    """Raised for floats, non-finite tokens, or non-I-JSON integers."""


def _reject_float(token: str) -> Any:
    raise UnsupportedNumberError(
        "floating-point JSON values are not supported by this protocol version: "
        + token
    )


def _reject_constant(token: str) -> Any:
    raise UnsupportedNumberError("non-finite JSON value is forbidden: " + token)


def _parse_integer(token: str) -> int:
    value = int(token, 10)
    if not IJSON_INTEGER_MIN <= value <= IJSON_INTEGER_MAX:
        raise UnsupportedNumberError(
            "integer is outside the exact I-JSON range: " + token
        )
    return value


def _object_without_duplicates(pairs: Iterable[Tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError("duplicate JSON object key: " + repr(key))
        result[key] = value
    return result


def _ensure_scalar_unicode(text: str, *, where: str) -> None:
    for character in text:
        codepoint = ord(character)
        if 0xD800 <= codepoint <= 0xDFFF:
            raise CanonicalizationError(
                "lone UTF-16 surrogate is forbidden in " + where
            )


def _validate_json_value(value: Any, *, path: str = "$") -> None:
    if value is None or type(value) is bool:
        return
    if type(value) is int:
        if not IJSON_INTEGER_MIN <= value <= IJSON_INTEGER_MAX:
            raise UnsupportedNumberError(
                "integer outside the exact I-JSON range at " + path
            )
        return
    if type(value) is float:
        raise UnsupportedNumberError(
            "floating-point value is unsupported at " + path
        )
    if type(value) is str:
        _ensure_scalar_unicode(value, where=path)
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise CanonicalizationError(
                    "JSON object key is not a string at " + path
                )
            _ensure_scalar_unicode(key, where=path + " object key")
            _validate_json_value(item, path=path + "[" + repr(key) + "]")
        return
    raise CanonicalizationError(
        "unsupported non-JSON value at " + path + ": " + type(value).__name__
    )


def loads_strict(data: Union[str, bytes, bytearray, memoryview]) -> Any:
    """Parse JSON while rejecting duplicate keys and unsupported JCS values."""

    if type(data) is str:
        text = data
    elif type(data) in (bytes, bytearray, memoryview):
        raw = bytes(data)
        if raw.startswith(b"\xef\xbb\xbf"):
            raise CanonicalizationError("UTF-8 BOM is forbidden")
        try:
            text = raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise CanonicalizationError("input is not valid UTF-8") from exc
    else:
        raise TypeError("JSON input must be str or bytes-like")

    if text.startswith("\ufeff"):
        raise CanonicalizationError("Unicode BOM is forbidden")

    try:
        value = json.loads(
            text,
            object_pairs_hook=_object_without_duplicates,
            parse_float=_reject_float,
            parse_int=_parse_integer,
            parse_constant=_reject_constant,
        )
    except CanonicalizationError:
        raise
    except (json.JSONDecodeError, UnicodeError, ValueError) as exc:
        raise CanonicalizationError("invalid JSON input") from exc

    _validate_json_value(value)
    return value


def _utf16_sort_key(text: str) -> bytes:
    _ensure_scalar_unicode(text, where="object key")
    return text.encode("utf-16-be", errors="strict")


def _serialize_string(text: str) -> str:
    _ensure_scalar_unicode(text, where="string")
    output: list[str] = ['"']
    short_escapes = {
        0x08: "\\b",
        0x09: "\\t",
        0x0A: "\\n",
        0x0C: "\\f",
        0x0D: "\\r",
    }
    for character in text:
        codepoint = ord(character)
        if character == '"':
            output.append('\\"')
        elif character == "\\":
            output.append("\\\\")
        elif codepoint in short_escapes:
            output.append(short_escapes[codepoint])
        elif codepoint <= 0x1F:
            output.append("\\u" + format(codepoint, "04x"))
        else:
            output.append(character)
    output.append('"')
    return "".join(output)


def _serialize(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if type(value) is int:
        if not IJSON_INTEGER_MIN <= value <= IJSON_INTEGER_MAX:
            raise UnsupportedNumberError("integer outside the exact I-JSON range")
        return str(value)
    if type(value) is float:
        raise UnsupportedNumberError(
            "floating-point values are unsupported by this protocol version"
        )
    if type(value) is str:
        return _serialize_string(value)
    if type(value) is list:
        return "[" + ",".join(_serialize(item) for item in value) + "]"
    if type(value) is dict:
        members: list[str] = []
        for key in sorted(value, key=_utf16_sort_key):
            if type(key) is not str:
                raise CanonicalizationError("JSON object key is not a string")
            members.append(_serialize_string(key) + ":" + _serialize(value[key]))
        return "{" + ",".join(members) + "}"
    raise CanonicalizationError(
        "unsupported non-JSON value: " + type(value).__name__
    )


def canonicalize_text(value: Any) -> str:
    """Return restricted RFC 8785 canonical JSON as Unicode text."""

    _validate_json_value(value)
    return _serialize(value)


def canonicalize(value: Any) -> bytes:
    """Return restricted RFC 8785 canonical JSON as exact UTF-8 bytes."""

    return canonicalize_text(value).encode("utf-8", errors="strict")


def canonicalize_json(data: Union[str, bytes, bytearray, memoryview]) -> bytes:
    """Strictly parse JSON and return its exact canonical UTF-8 bytes."""

    return canonicalize(loads_strict(data))


def sha256_hex(data: Union[bytes, bytearray, memoryview]) -> str:
    """Return a lowercase SHA-256 hexadecimal digest for exact bytes."""

    if type(data) not in (bytes, bytearray, memoryview):
        raise TypeError("SHA-256 input must be bytes-like")
    return hashlib.sha256(bytes(data)).hexdigest()


def sha256_digest(data: Union[bytes, bytearray, memoryview]) -> str:
    """Return the protocol's ``sha256:<lowercase-hex>`` digest form."""

    return "sha256:" + sha256_hex(data)
