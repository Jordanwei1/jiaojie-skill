"""Small Draft 2020-12 subset validator for the bundled v0.1 Schemas.

It implements every keyword used by the shipped Schema set.  Cross-object protocol
invariants remain in ``validate.py`` rather than being misrepresented as JSON Schema.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .canonicalize import canonicalize_text, loads_strict, sha256_digest

from .registry import (
    language_unicode_vector,
    profile_feature_registry,
    registry_lock,
    schema_catalog,
    vector_catalog,
)
from .util import LCHError


@dataclass(frozen=True)
class SchemaProblem:
    path: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"path": self.path, "message": self.message}


class SchemaStore:
    def __init__(self, directory: Path):
        self.directory = directory.resolve()
        self.documents: dict[Path, Any] = {}
        self.ids: dict[str, Path] = {}
        catalog = schema_catalog()
        entries = catalog.get("schemas")
        if not isinstance(entries, list):
            raise LCHError("SCHEMA_CATALOG_INVALID", "Schema catalog entries are missing")
        expected_names: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise LCHError("SCHEMA_CATALOG_INVALID", "Schema catalog entry is not an object")
            relative = entry.get("path")
            if not isinstance(relative, str) or not relative.startswith("schemas/"):
                raise LCHError("SCHEMA_CATALOG_INVALID", "Schema catalog path is invalid")
            name = relative.removeprefix("schemas/")
            if "/" in name or not name.endswith(".schema.json") or name in expected_names:
                raise LCHError("SCHEMA_CATALOG_INVALID", "Schema catalog path is unsafe or duplicated")
            expected_names.add(name)
            path = self.directory / name
            try:
                raw = path.read_bytes()
                if len(raw) != entry.get("byte_length") or sha256_digest(raw) != entry.get("sha256_raw"):
                    raise LCHError("SCHEMA_INTEGRITY_FAIL", f"Schema integrity mismatch: {path.name}")
                document = loads_strict(raw)
            except Exception as exc:
                if isinstance(exc, LCHError):
                    raise
                raise LCHError("SCHEMA_INVALID", f"cannot load Schema: {path.name}") from exc
            if not isinstance(document, dict) or document.get("$id") != entry.get("id"):
                raise LCHError("SCHEMA_ID_MISMATCH", f"Schema $id mismatch: {path.name}")
            self.documents[path.resolve()] = document
            identifier = document.get("$id") if isinstance(document, dict) else None
            if isinstance(identifier, str):
                if identifier in self.ids:
                    raise LCHError("SCHEMA_DUPLICATE_ID", "duplicate bundled Schema $id")
                self.ids[identifier] = path.resolve()
        actual_names = {path.name for path in self.directory.glob("*.schema.json")}
        if actual_names != expected_names:
            raise LCHError("SCHEMA_CATALOG_CLOSURE_FAIL", "bundled Schema set differs from the offline catalog")

        bootstrap = Validator(self)
        asset_checks = (
            (catalog, "schema-catalog.schema.json", "Schema catalog"),
            (profile_feature_registry(), "profile-feature-registry.schema.json", "profile and feature registry"),
            (registry_lock(), "registry-lock.schema.json", "language registry lock"),
            (vector_catalog(), "vector-catalog.schema.json", "golden vector catalog"),
            (language_unicode_vector(), "language-unicode-vector.schema.json", "language and Unicode vector"),
        )
        for value, schema_name, label in asset_checks:
            problems = bootstrap.validate(value, schema_name)
            if problems:
                raise LCHError(
                    "PROTOCOL_ASSET_SCHEMA_FAIL",
                    f"{label} fails its bundled Schema",
                    details=[problem.as_dict() for problem in problems],
                )

    def document(self, name: str) -> tuple[Path, Any]:
        path = (self.directory / name).resolve()
        if path not in self.documents:
            raise LCHError("SCHEMA_NOT_FOUND", f"unknown bundled Schema: {name}")
        return path, self.documents[path]

    def resolve(self, reference: str, current: Path) -> tuple[Path, Any]:
        base, marker, fragment = reference.partition("#")
        if base:
            if urlparse(base).scheme:
                target_path = self.ids.get(base)
                if target_path is None:
                    raise LCHError("SCHEMA_REF_UNRESOLVED", "external Schema reference is not bundled")
            else:
                target_path = (current.parent / base).resolve()
        else:
            target_path = current
        document = self.documents.get(target_path)
        if document is None:
            raise LCHError("SCHEMA_REF_UNRESOLVED", f"Schema reference is not bundled: {reference}")
        node = document
        if marker and fragment:
            if not fragment.startswith("/"):
                raise LCHError("SCHEMA_REF_UNRESOLVED", "only JSON Pointer fragments are supported")
            for raw in fragment[1:].split("/"):
                token = raw.replace("~1", "/").replace("~0", "~")
                try:
                    if isinstance(node, list):
                        node = node[int(token)]
                    else:
                        node = node[token]
                except (KeyError, IndexError, TypeError, ValueError) as exc:
                    raise LCHError("SCHEMA_REF_UNRESOLVED", f"unresolved Schema reference: {reference}") from exc
        return target_path, node


def _type_matches(value: Any, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    return False


_URI_UNRESERVED = r"[A-Za-z0-9._~-]"
_URI_PCT_ENCODED = r"%[0-9A-Fa-f]{2}"
_URI_SUB_DELIM = r"[!$&'()*+,;=]"
_URI_PCHAR = rf"(?:{_URI_UNRESERVED}|{_URI_PCT_ENCODED}|{_URI_SUB_DELIM}|[:@])"
_URI_AUTHORITY_CHAR = rf"(?:{_URI_UNRESERVED}|{_URI_PCT_ENCODED}|{_URI_SUB_DELIM}|[:@\[\]])"
_URI_QUERY_CHAR = rf"(?:{_URI_PCHAR}|[/?])"
_ABSOLUTE_URI_RE = re.compile(
    rf"[A-Za-z][A-Za-z0-9+.-]*:"
    rf"(?:"
    rf"//{_URI_AUTHORITY_CHAR}*(?:/{_URI_PCHAR}*)*"
    rf"|/(?:{_URI_PCHAR}+(?:/{_URI_PCHAR}*)*)?"
    rf"|{_URI_PCHAR}+(?:/{_URI_PCHAR}*)*"
    rf"|"
    rf")"
    rf"(?:\?{_URI_QUERY_CHAR}*)?"
    rf"(?:#{_URI_QUERY_CHAR}*)?"
)


def format_matches(value: str, name: str) -> bool:
    if name == "date-time":
        match = re.fullmatch(
            r"([0-9]{4})-([0-9]{2})-([0-9]{2})[Tt]"
            r"([0-9]{2}):([0-9]{2}):([0-9]{2})"
            r"(?:\.[0-9]+)?([Zz]|[+-][0-9]{2}:[0-9]{2})",
            value,
        )
        if match is None:
            return False
        year, month, day, hour, minute, second = map(int, match.groups()[:6])
        if hour > 23 or minute > 59 or second > 60:
            return False
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        month_lengths = (31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
        if month < 1 or month > 12 or day < 1 or day > month_lengths[month - 1]:
            return False
        offset = match.group(7)
        if offset.casefold() != "z":
            offset_hour, offset_minute = map(int, offset[1:].split(":"))
            if offset_hour > 23 or offset_minute > 59:
                return False
        return True
    if name == "uri":
        if not value or any(ord(character) < 0x21 or ord(character) > 0x7E for character in value):
            return False
        if _ABSOLUTE_URI_RE.fullmatch(value) is None:
            return False
        try:
            parsed = urlparse(value)
            if not parsed.scheme:
                return False
            if parsed.netloc.count("@") > 1:
                return False
            # Accessing hostname makes urllib reject malformed bracketed hosts.
            # Validate the generic RFC 3986 port grammar ourselves: ``*DIGIT`` has
            # no 0..65535 network-semantics range restriction.
            _ = parsed.hostname
            host_port = parsed.netloc.rsplit("@", 1)[-1]
            if host_port.startswith("["):
                close = host_port.find("]")
                if close < 0:
                    return False
                suffix = host_port[close + 1 :]
                if suffix and (
                    not suffix.startswith(":")
                    or re.fullmatch(r"[0-9]*", suffix[1:]) is None
                ):
                    return False
            else:
                if "[" in host_port or "]" in host_port or host_port.count(":") > 1:
                    return False
                if ":" in host_port:
                    port = host_port.rsplit(":", 1)[1]
                    if re.fullmatch(r"[0-9]*", port) is None:
                        return False
        except ValueError:
            return False
        return True
    if name == "bcp47":
        # Syntax prefilter only.  The pinned registry-aware validator performs
        # qualification; this intentionally admits grandfathered/private-use tags.
        return bool(re.fullmatch(r"[A-Za-z0-9]{1,8}(?:-[A-Za-z0-9]{1,8})*", value))
    return True


def _value_key(value: Any) -> str:
    try:
        return canonicalize_text(value)
    except Exception:
        return repr(value)


class Validator:
    def __init__(self, store: SchemaStore, *, max_problems: int = 100):
        self.store = store
        self.max_problems = max_problems

    def validate(self, value: Any, schema_name: str) -> list[SchemaProblem]:
        path, schema = self.store.document(schema_name)
        problems: list[SchemaProblem] = []
        self._check(value, schema, path, "$", problems)
        return problems[: self.max_problems]

    def _trial(self, value: Any, schema: Any, document: Path, path: str) -> bool:
        trial: list[SchemaProblem] = []
        self._check(value, schema, document, path, trial)
        return not trial

    def _add(self, problems: list[SchemaProblem], path: str, message: str) -> None:
        if len(problems) < self.max_problems:
            problems.append(SchemaProblem(path, message))

    def _evaluated_properties(
        self,
        value: Any,
        schema: Any,
        document: Path,
        seen: set[tuple[Path, int]],
    ) -> set[str]:
        if not isinstance(value, dict) or not isinstance(schema, dict):
            return set()
        marker = (document, id(schema))
        if marker in seen:
            return set()
        seen.add(marker)
        properties = schema.get("properties")
        result = value.keys() & properties.keys() if isinstance(properties, dict) else set()
        if "$ref" in schema:
            target_document, target = self.store.resolve(schema["$ref"], document)
            result.update(self._evaluated_properties(value, target, target_document, seen))
        branches = schema.get("allOf", [])
        if isinstance(branches, list):
            for branch in branches:
                if self._trial(value, branch, document, "$"):
                    result.update(self._evaluated_properties(value, branch, document, seen))
        for keyword in ("anyOf", "oneOf"):
            branches = schema.get(keyword, [])
            if isinstance(branches, list):
                for branch in branches:
                    if self._trial(value, branch, document, "$"):
                        result.update(self._evaluated_properties(value, branch, document, seen))
        if_schema = schema.get("if")
        if isinstance(if_schema, dict):
            chosen = schema.get("then") if self._trial(value, if_schema, document, "$") else schema.get("else")
            if chosen is not None and self._trial(value, chosen, document, "$"):
                result.update(self._evaluated_properties(value, chosen, document, seen))
        return result

    def _check(
        self,
        value: Any,
        schema: Any,
        document: Path,
        path: str,
        problems: list[SchemaProblem],
    ) -> None:
        if len(problems) >= self.max_problems:
            return
        if schema is True:
            return
        if schema is False:
            self._add(problems, path, "value is forbidden by Schema")
            return
        if not isinstance(schema, dict):
            self._add(problems, path, "invalid bundled Schema node")
            return

        if "$ref" in schema:
            target_document, target = self.store.resolve(schema["$ref"], document)
            self._check(value, target, target_document, path, problems)

        for branch in schema.get("allOf", []):
            self._check(value, branch, document, path, problems)

        one_of = schema.get("oneOf")
        if isinstance(one_of, list):
            matches = sum(self._trial(value, branch, document, path) for branch in one_of)
            if matches != 1:
                self._add(problems, path, f"must match exactly one oneOf branch; matched {matches}")

        any_of = schema.get("anyOf")
        if isinstance(any_of, list) and not any(self._trial(value, branch, document, path) for branch in any_of):
            self._add(problems, path, "must match at least one anyOf branch")

        if_schema = schema.get("if")
        if isinstance(if_schema, dict):
            chosen = schema.get("then") if self._trial(value, if_schema, document, path) else schema.get("else")
            if chosen is not None:
                self._check(value, chosen, document, path, problems)

        if "not" in schema and self._trial(value, schema["not"], document, path):
            self._add(problems, path, "matches forbidden not branch")

        expected_type = schema.get("type")
        if isinstance(expected_type, str):
            if not _type_matches(value, expected_type):
                self._add(problems, path, f"expected {expected_type}")
                return
        elif isinstance(expected_type, list):
            if not any(isinstance(item, str) and _type_matches(value, item) for item in expected_type):
                self._add(problems, path, "value has no allowed type")
                return

        if "const" in schema and value != schema["const"]:
            self._add(problems, path, "value does not equal const")
        enum = schema.get("enum")
        if isinstance(enum, list) and value not in enum:
            self._add(problems, path, "value is not in enum")

        if isinstance(value, str):
            minimum = schema.get("minLength")
            maximum = schema.get("maxLength")
            if isinstance(minimum, int) and len(value) < minimum:
                self._add(problems, path, f"string is shorter than {minimum}")
            if isinstance(maximum, int) and len(value) > maximum:
                self._add(problems, path, f"string is longer than {maximum}")
            pattern = schema.get("pattern")
            if isinstance(pattern, str):
                try:
                    if re.search(pattern, value) is None:
                        self._add(problems, path, "string does not match pattern")
                except re.error:
                    self._add(problems, path, "bundled Schema pattern is unsupported")
            format_name = schema.get("format")
            if isinstance(format_name, str) and not format_matches(value, format_name):
                self._add(problems, path, f"string does not match format {format_name}")

        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                self._add(problems, path, "number is below minimum")
            if "maximum" in schema and value > schema["maximum"]:
                self._add(problems, path, "number is above maximum")

        if isinstance(value, list):
            if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
                self._add(problems, path, "array has too few items")
            if isinstance(schema.get("maxItems"), int) and len(value) > schema["maxItems"]:
                self._add(problems, path, "array has too many items")
            if schema.get("uniqueItems") is True:
                keys = [_value_key(item) for item in value]
                if len(keys) != len(set(keys)):
                    self._add(problems, path, "array items are not unique")
            prefix_items = schema.get("prefixItems")
            prefix_length = 0
            if isinstance(prefix_items, list):
                prefix_length = len(prefix_items)
                for index, child_schema in enumerate(prefix_items):
                    if index < len(value):
                        self._check(
                            value[index],
                            child_schema,
                            document,
                            f"{path}[{index}]",
                            problems,
                        )
            if "items" in schema:
                for index in range(prefix_length, len(value)):
                    self._check(
                        value[index],
                        schema["items"],
                        document,
                        f"{path}[{index}]",
                        problems,
                    )
            contains = schema.get("contains")
            if contains is not None:
                matches = sum(self._trial(item, contains, document, f"{path}[*]") for item in value)
                minimum = schema.get("minContains", 1)
                maximum = schema.get("maxContains")
                if matches < minimum:
                    self._add(problems, path, f"contains matched {matches}, below {minimum}")
                if isinstance(maximum, int) and matches > maximum:
                    self._add(problems, path, f"contains matched {matches}, above {maximum}")

        if isinstance(value, dict):
            required = schema.get("required", [])
            if isinstance(required, list):
                for key in required:
                    if key not in value:
                        self._add(problems, path, f"missing required property {key}")
            properties = schema.get("properties", {})
            if isinstance(properties, dict):
                for key, child_schema in properties.items():
                    if key in value:
                        self._check(value[key], child_schema, document, f"{path}.{key}", problems)
            if isinstance(schema.get("minProperties"), int) and len(value) < schema["minProperties"]:
                self._add(problems, path, "object has too few properties")
            if schema.get("additionalProperties") is False and isinstance(properties, dict):
                for key in value.keys() - properties.keys():
                    self._add(problems, f"{path}.{key}", "additional property is forbidden")
            if schema.get("unevaluatedProperties") is False:
                evaluated = self._evaluated_properties(value, schema, document, set())
                for key in value.keys() - evaluated:
                    self._add(problems, f"{path}.{key}", "unevaluated property is forbidden")
