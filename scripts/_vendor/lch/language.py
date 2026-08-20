"""Release-pinned RFC 5646 and Unicode vector qualification."""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

from .canonicalize import sha256_digest
from .registry import language_unicode_vector, registry_lock
from .util import LCHError, read_bytes


HANDOFF_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_DIRECTORY = HANDOFF_ROOT / "assets" / "registry"
MAX_REGISTRY_BYTES = 2 * 1024 * 1024
_BIDI_CONTROLS = frozenset(
    {
        0x061C,
        0x200E,
        0x200F,
        0x202A,
        0x202B,
        0x202C,
        0x202D,
        0x202E,
        0x2066,
        0x2067,
        0x2068,
        0x2069,
    }
)
_LOCALIZED_TEXT_KEYS = frozenset(
    {
        "text_id",
        "value",
        "lang",
        "dir",
        "kind",
        "authority",
        "fidelity",
        "translation_of",
        "translation_method",
        "review_status",
    }
)
_LANGUAGE_PROFILE_KEYS = frozenset(
    {
        "source_languages",
        "content_languages",
        "continuation_language_ranges",
        "selected_continuation_language",
        "translation_policy",
        "generated_text_normalization",
    }
)
_RECEIPT_SIGNATURE_KEYS = frozenset(
    {
        "receipt_version",
        "package_id",
        "package_integrity_ref",
        "challenge_nonce",
        "receipt_issuer",
        "verification_result_refs",
        "selected_continuation_language",
        "continuation_status",
    }
)


def is_receipt_payload(value: Any) -> bool:
    """Recognize the direct Receipt object, which intentionally has no ``type``."""

    if not isinstance(value, dict) or not _RECEIPT_SIGNATURE_KEYS.issubset(value):
        return False
    issuer = value.get("receipt_issuer")
    return (
        value.get("receipt_version") == "0.1.0"
        and isinstance(value.get("package_integrity_ref"), dict)
        and isinstance(issuer, dict)
        and issuer.get("authority") == "receive_and_verify"
        and isinstance(value.get("selected_continuation_language"), str)
    )


def _parse_records(text: str) -> tuple[str, dict[str, dict[str, dict[str, Any]]]]:
    sections = text.split("%%")
    header = sections[0].strip().splitlines()
    if len(header) != 1 or not header[0].startswith("File-Date: "):
        raise LCHError("LANGUAGE_REGISTRY_HEADER_FAIL", "IANA registry File-Date header is invalid")
    file_date = header[0].split(": ", 1)[1]
    by_type: dict[str, dict[str, dict[str, Any]]] = {}
    for raw_record in sections[1:]:
        fields: dict[str, list[str]] = {}
        current: str | None = None
        for line in raw_record.strip().splitlines():
            if line.startswith("  ") and current is not None:
                fields[current][-1] += line[1:]
                continue
            if ": " not in line:
                if line:
                    raise LCHError("LANGUAGE_REGISTRY_PARSE_FAIL", "IANA registry record is malformed")
                continue
            key, value = line.split(": ", 1)
            fields.setdefault(key, []).append(value)
            current = key
        if not fields:
            continue
        record_type = fields.get("Type", [None])[0]
        identifier = fields.get("Subtag", fields.get("Tag", [None]))[0]
        if not isinstance(record_type, str) or not isinstance(identifier, str):
            raise LCHError("LANGUAGE_REGISTRY_PARSE_FAIL", "IANA registry record lacks Type or identifier")
        normalized = identifier.casefold()
        bucket = by_type.setdefault(record_type.casefold(), {})
        if normalized in bucket:
            raise LCHError("LANGUAGE_REGISTRY_DUPLICATE", "IANA registry contains a duplicate identifier")
        bucket[normalized] = {key: tuple(values) for key, values in fields.items()}
    return file_date, by_type


def _parse_extensions(text: str) -> tuple[str, dict[str, dict[str, Any]]]:
    sections = text.split("%%")
    header = sections[0].strip().splitlines()
    if len(header) != 1 or not header[0].startswith("File-Date: "):
        raise LCHError("EXTENSION_REGISTRY_HEADER_FAIL", "IANA extension registry File-Date header is invalid")
    file_date = header[0].split(": ", 1)[1]
    records: dict[str, dict[str, Any]] = {}
    for raw_record in sections[1:]:
        fields: dict[str, list[str]] = {}
        current: str | None = None
        for line in raw_record.strip().splitlines():
            if line.startswith("  ") and current is not None:
                fields[current][-1] += line[1:]
                continue
            if ": " not in line:
                if line:
                    raise LCHError("EXTENSION_REGISTRY_PARSE_FAIL", "IANA extension registry record is malformed")
                continue
            key, value = line.split(": ", 1)
            fields.setdefault(key, []).append(value)
            current = key
        if not fields:
            continue
        identifier = fields.get("Identifier", [None])[0]
        if not isinstance(identifier, str) or re.fullmatch(r"[0-9A-WY-Za-wy-z]", identifier) is None:
            raise LCHError("EXTENSION_REGISTRY_PARSE_FAIL", "IANA extension registry identifier is invalid")
        normalized = identifier.casefold()
        if normalized in records:
            raise LCHError("EXTENSION_REGISTRY_DUPLICATE", "IANA extension singleton is duplicated")
        records[normalized] = {key: tuple(values) for key, values in fields.items()}
    return file_date, records


@lru_cache(maxsize=1)
def pinned_registry() -> tuple[dict[str, dict[str, dict[str, Any]]], dict[str, Any]]:
    lock = registry_lock()
    iana = lock.get("iana_language_subtag_registry")
    extensions_lock = lock.get("iana_language_tag_extensions_registry")
    unicode_lock = lock.get("unicode")
    if (
        not isinstance(iana, dict)
        or not isinstance(extensions_lock, dict)
        or not isinstance(unicode_lock, dict)
    ):
        raise LCHError("REGISTRY_LOCK_INVALID", "registry lock sections are missing")
    path_name = iana.get("path")
    if not isinstance(path_name, str) or Path(path_name).name != path_name:
        raise LCHError("REGISTRY_LOCK_INVALID", "registry lock path must be one local filename")
    snapshot = read_bytes(REGISTRY_DIRECTORY / path_name, max_bytes=MAX_REGISTRY_BYTES)
    if len(snapshot) != iana.get("byte_length"):
        raise LCHError("LANGUAGE_REGISTRY_LENGTH_FAIL", "pinned IANA registry byte length mismatch")
    if sha256_digest(snapshot) != iana.get("sha256_raw"):
        raise LCHError("LANGUAGE_REGISTRY_HASH_FAIL", "pinned IANA registry SHA-256 mismatch")
    try:
        snapshot_text = snapshot.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise LCHError("LANGUAGE_REGISTRY_ENCODING_FAIL", "pinned IANA registry is not UTF-8") from exc
    file_date, parsed = _parse_records(snapshot_text)
    if file_date != iana.get("file_date"):
        raise LCHError("LANGUAGE_REGISTRY_DATE_FAIL", "pinned IANA registry File-Date mismatch")
    extension_name = extensions_lock.get("path")
    if not isinstance(extension_name, str) or Path(extension_name).name != extension_name:
        raise LCHError("REGISTRY_LOCK_INVALID", "extension registry path must be one local filename")
    extension_snapshot = read_bytes(
        REGISTRY_DIRECTORY / extension_name,
        max_bytes=MAX_REGISTRY_BYTES,
    )
    if len(extension_snapshot) != extensions_lock.get("byte_length"):
        raise LCHError("EXTENSION_REGISTRY_LENGTH_FAIL", "pinned extension registry byte length mismatch")
    if sha256_digest(extension_snapshot) != extensions_lock.get("sha256_raw"):
        raise LCHError("EXTENSION_REGISTRY_HASH_FAIL", "pinned extension registry SHA-256 mismatch")
    try:
        extension_text = extension_snapshot.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise LCHError("EXTENSION_REGISTRY_ENCODING_FAIL", "pinned extension registry is not UTF-8") from exc
    extension_date, extensions = _parse_extensions(extension_text)
    if extension_date != extensions_lock.get("file_date"):
        raise LCHError("EXTENSION_REGISTRY_DATE_FAIL", "pinned extension registry File-Date mismatch")
    parsed["extension"] = extensions
    locked_unicode = unicode_lock.get("version")
    if locked_unicode != "15.1.0" or unicodedata.unidata_version != locked_unicode:
        raise LCHError("UNICODE_VERSION_MISMATCH", "runtime Unicode data does not match locked 15.1.0")
    metadata: dict[str, Any] = {
        "registry_path": "assets/registry/" + path_name,
        "registry_file_date": file_date,
        "registry_sha256_raw": iana["sha256_raw"],
        "registry_byte_length": iana["byte_length"],
        "extension_registry_path": "assets/registry/" + extension_name,
        "extension_registry_file_date": extension_date,
        "extension_registry_sha256_raw": extensions_lock["sha256_raw"],
        "extension_registry_byte_length": extensions_lock["byte_length"],
        "unicode_version": unicodedata.unidata_version,
    }
    return parsed, metadata


def _record_for(
    registry: dict[str, dict[str, dict[str, Any]]],
    record_type: str,
    subtag: str,
) -> dict[str, Any] | None:
    bucket = registry.get(record_type, {})
    normalized = subtag.casefold()
    direct = bucket.get(normalized)
    if direct is not None:
        return direct
    for key, record in bucket.items():
        if ".." not in key:
            continue
        first, last = key.split("..", 1)
        if len(first) == len(normalized) == len(last) and first <= normalized <= last:
            return record
    return None


def _result(
    *,
    valid: bool,
    classification: str,
    canonical: str | None,
    deprecated: bool = False,
    preferred_value: str | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    return {
        "valid": valid,
        "classification": classification,
        "canonical": canonical,
        "deprecated": deprecated,
        "preferred_value": preferred_value,
        "error_code": error_code,
    }


def _invalid(code: str) -> dict[str, Any]:
    return _result(
        valid=False,
        classification="INVALID",
        canonical=None,
        error_code=code,
    )


def qualify_tag(
    tag: str,
    registry: dict[str, dict[str, dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    """Return deterministic RFC 5646 qualification for one language tag."""

    if registry is None:
        registry, _ = pinned_registry()
    if not isinstance(tag, str) or not tag or not tag.isascii():
        return _invalid("SYNTAX")
    lowered = tag.casefold()
    exact = registry.get("grandfathered", {}).get(lowered)
    exact_kind = "grandfathered"
    if exact is None:
        exact = registry.get("redundant", {}).get(lowered)
        exact_kind = "redundant"
    if exact is not None and (
        exact_kind == "grandfathered"
        or "Preferred-Value" in exact
        or "Deprecated" in exact
    ):
        preferred = exact.get("Preferred-Value", (None,))[0]
        deprecated = "Deprecated" in exact
        canonical = preferred if isinstance(preferred, str) else lowered
        classification = (
            "GRANDFATHERED_DEPRECATED" if deprecated else "GRANDFATHERED"
        ) if exact_kind == "grandfathered" else (
            "DEPRECATED" if deprecated else "REGISTERED"
        )
        return _result(
            valid=True,
            classification=classification,
            canonical=canonical,
            deprecated=deprecated,
            preferred_value=canonical if isinstance(preferred, str) else None,
        )

    parts = tag.split("-")
    if any(
        not part or len(part) > 8 or re.fullmatch(r"[A-Za-z0-9]+", part) is None
        for part in parts
    ):
        return _invalid("SYNTAX")
    if parts[0].casefold() == "x":
        if len(parts) == 1:
            return _invalid("SYNTAX")
        return _result(
            valid=True,
            classification="PRIVATE_USE",
            canonical="-".join(part.casefold() for part in parts),
        )

    language = parts[0]
    if not language.isalpha() or not 2 <= len(language) <= 8:
        return _invalid("SYNTAX")
    language_record = _record_for(registry, "language", language)
    if language_record is None:
        return _invalid("UNREGISTERED_SUBTAG")
    canonical_parts = [language.casefold()]
    validation_prefix = [language.casefold()]
    preferred_applied = False
    deprecated = "Deprecated" in language_record
    primary_preferred = language_record.get("Preferred-Value", (None,))[0]
    if isinstance(primary_preferred, str):
        canonical_parts[0] = primary_preferred.casefold()
        preferred_applied = True

    index = 1
    extlang_count = 0
    while index < len(parts) and len(parts[index]) == 3 and parts[index].isalpha() and extlang_count < 3:
        extlang = parts[index]
        record = _record_for(registry, "extlang", extlang)
        if record is None:
            break
        prefixes = {item.casefold() for item in record.get("Prefix", ())}
        if prefixes and "-".join(validation_prefix) not in prefixes:
            return _invalid("EXTLANG_PREFIX")
        validation_prefix.append(extlang.casefold())
        preferred = record.get("Preferred-Value", (None,))[0]
        deprecated = deprecated or "Deprecated" in record
        if isinstance(preferred, str) and extlang_count == 0:
            canonical_parts = [preferred.casefold()]
            preferred_applied = True
        else:
            canonical_parts.append(extlang.casefold())
        extlang_count += 1
        index += 1

    if index < len(parts) and len(parts[index]) == 4 and parts[index].isalpha():
        script = parts[index]
        record = _record_for(registry, "script", script)
        if record is None:
            return _invalid("UNREGISTERED_SUBTAG")
        preferred = record.get("Preferred-Value", (None,))[0]
        replacement = preferred if isinstance(preferred, str) else script
        canonical_parts.append(replacement.title())
        validation_prefix.append(script.casefold())
        preferred_applied = preferred_applied or isinstance(preferred, str)
        deprecated = deprecated or "Deprecated" in record
        index += 1

    if index < len(parts) and (
        (len(parts[index]) == 2 and parts[index].isalpha())
        or (len(parts[index]) == 3 and parts[index].isdigit())
    ):
        region = parts[index]
        record = _record_for(registry, "region", region)
        if record is None:
            return _invalid("UNREGISTERED_SUBTAG")
        preferred = record.get("Preferred-Value", (None,))[0]
        replacement = preferred if isinstance(preferred, str) else region
        canonical_parts.append(replacement.upper())
        validation_prefix.append(region.casefold())
        preferred_applied = preferred_applied or isinstance(preferred, str)
        deprecated = deprecated or "Deprecated" in record
        index += 1

    seen_variants: set[str] = set()
    while index < len(parts):
        variant = parts[index]
        variant_shape = 5 <= len(variant) <= 8 or (len(variant) == 4 and variant[0].isdigit())
        if not variant_shape:
            break
        record = _record_for(registry, "variant", variant)
        if record is None:
            return _invalid("UNREGISTERED_SUBTAG")
        normalized = variant.casefold()
        if normalized in seen_variants:
            return _invalid("DUPLICATE_VARIANT")
        preferred = record.get("Preferred-Value", (None,))[0]
        replacement = preferred if isinstance(preferred, str) else variant
        canonical_parts.append(replacement.casefold())
        validation_prefix.append(normalized)
        preferred_applied = preferred_applied or isinstance(preferred, str)
        deprecated = deprecated or "Deprecated" in record
        seen_variants.add(normalized)
        index += 1

    seen_singletons: set[str] = set()
    extension_present = False
    extensions: list[tuple[str, list[str]]] = []
    while index < len(parts) and len(parts[index]) == 1 and parts[index].casefold() != "x":
        singleton = parts[index].casefold()
        if re.fullmatch(r"[0-9a-wy-z]", singleton) is None:
            return _invalid("SYNTAX")
        if singleton in seen_singletons:
            return _invalid("DUPLICATE_SINGLETON")
        if singleton not in registry.get("extension", {}):
            return _invalid("UNREGISTERED_SINGLETON")
        seen_singletons.add(singleton)
        extension_present = True
        index += 1
        start = index
        extension_parts: list[str] = []
        while index < len(parts) and 2 <= len(parts[index]) <= 8:
            extension_parts.append(parts[index].casefold())
            index += 1
        if index == start:
            return _invalid("SYNTAX")
        extensions.append((singleton, extension_parts))

    for singleton, extension_parts in sorted(extensions):
        canonical_parts.append(singleton)
        canonical_parts.extend(extension_parts)

    if index < len(parts) and parts[index].casefold() == "x":
        canonical_parts.append("x")
        index += 1
        if index == len(parts):
            return _invalid("SYNTAX")
        while index < len(parts) and 1 <= len(parts[index]) <= 8:
            canonical_parts.append(parts[index].casefold())
            index += 1

    if index != len(parts):
        part = parts[index]
        if len(part) == 4 and part.isalpha() and any(
            len(candidate) in {2, 3} for candidate in parts[1:index]
        ):
            return _invalid("ORDER")
        return _invalid("UNREGISTERED_SUBTAG")

    canonical = "-".join(canonical_parts)
    if deprecated:
        classification = "DEPRECATED"
    elif preferred_applied:
        classification = "PREFERRED_REPLACEMENT"
    elif extension_present:
        classification = "EXTENSION"
    else:
        classification = "REGISTERED"
    return _result(
        valid=True,
        classification=classification,
        canonical=canonical,
        deprecated=deprecated,
        preferred_value=canonical if preferred_applied else None,
    )


@lru_cache(maxsize=1)
def run_registered_vector() -> dict[str, Any]:
    registry, metadata = pinned_registry()
    vector = language_unicode_vector()
    lock = vector.get("registry_lock")
    subtag_lock = lock.get("language_subtag_registry") if isinstance(lock, dict) else None
    extension_lock = lock.get("language_tag_extensions_registry") if isinstance(lock, dict) else None
    if not isinstance(subtag_lock, dict) or not isinstance(extension_lock, dict) or (
        subtag_lock.get("path") != metadata["registry_path"]
        or subtag_lock.get("file_date") != metadata["registry_file_date"]
        or subtag_lock.get("byte_length") != metadata["registry_byte_length"]
        or subtag_lock.get("sha256_raw") != metadata["registry_sha256_raw"]
        or extension_lock.get("path") != metadata["extension_registry_path"]
        or extension_lock.get("file_date") != metadata["extension_registry_file_date"]
        or extension_lock.get("byte_length") != metadata["extension_registry_byte_length"]
        or extension_lock.get("sha256_raw") != metadata["extension_registry_sha256_raw"]
    ):
        raise LCHError("LANGUAGE_VECTOR_LOCK_FAIL", "language vector registry lock differs from the pinned registry")
    unicode_runtime = vector.get("unicode_runtime")
    if not isinstance(unicode_runtime, dict) or unicode_runtime.get("version") != metadata["unicode_version"]:
        raise LCHError("LANGUAGE_VECTOR_UNICODE_FAIL", "language vector Unicode version is unavailable")
    for case in vector.get("bcp47_cases", []):
        if not isinstance(case, dict) or qualify_tag(case.get("input"), registry) != case.get("expected"):
            case_id = case.get("case_id") if isinstance(case, dict) else "unknown"
            raise LCHError("LANGUAGE_VECTOR_BCP47_FAIL", f"registered BCP 47 vector failed: {case_id}")
    unicode_cases = vector.get("unicode_cases")
    if not isinstance(unicode_cases, dict):
        raise LCHError("LANGUAGE_VECTOR_INVALID", "registered Unicode vector cases are missing")
    for case in unicode_cases.get("normalization", []):
        if (
            unicodedata.normalize(str(case.get("operation")), str(case.get("input"))) != case.get("expected")
            or unicodedata.normalize("NFKC", str(case.get("input"))) != case.get("nfkc_expected")
        ):
            raise LCHError("LANGUAGE_VECTOR_NORMALIZATION_FAIL", "registered Unicode normalization vector failed")
    for case in unicode_cases.get("source_byte_preservation", []):
        try:
            source = bytes.fromhex(str(case.get("source_utf8_hex")))
            derived = unicodedata.normalize("NFC", source.decode("utf-8")).encode("utf-8")
        except (ValueError, UnicodeError) as exc:
            raise LCHError("LANGUAGE_VECTOR_BYTES_FAIL", "registered source-byte vector is invalid") from exc
        if source.hex() != case.get("expected_source_utf8_hex") or derived.hex() != case.get("derived_nfc_utf8_hex"):
            raise LCHError("LANGUAGE_VECTOR_BYTES_FAIL", "registered source-byte vector failed")
    for case in unicode_cases.get("protected_spans", []):
        if case.get("input") != case.get("expected"):
            raise LCHError("LANGUAGE_VECTOR_PROTECTED_FAIL", "registered protected-span vector failed")
    for case in unicode_cases.get("bidi_control_detection", []):
        value = str(case.get("input"))
        found = [f"U+{ord(character):04X}" for character in value if ord(character) in _BIDI_CONTROLS]
        if (
            bool(found) is not case.get("detected")
            or found != case.get("control_codepoints")
            or value != case.get("expected_unchanged")
        ):
            raise LCHError("LANGUAGE_VECTOR_BIDI_FAIL", "registered bidi-control vector failed")
    return {
        **metadata,
        "vector_id": vector.get("vector_id"),
        "qualification_scope": "REGISTERED_VECTOR_SCOPE_ONLY",
        "not_claimed": vector.get("not_claimed"),
    }


def _collect_language_material(
    values: tuple[Any, ...],
) -> tuple[list[str], list[dict[str, Any]]]:
    tags: list[str] = []
    profiles: list[dict[str, Any]] = []
    stack = list(values)
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            if _LOCALIZED_TEXT_KEYS.issubset(value) and isinstance(value.get("lang"), str):
                tags.append(value["lang"])
            if _LANGUAGE_PROFILE_KEYS.issubset(value):
                profiles.append(value)
                source_languages = value.get("source_languages")
                if isinstance(source_languages, list):
                    for item in source_languages:
                        if isinstance(item, dict) and isinstance(item.get("tag"), str):
                            tags.append(item["tag"])
                for key in ("content_languages", "continuation_language_ranges"):
                    child = value.get(key)
                    if isinstance(child, list):
                        tags.extend(item for item in child if isinstance(item, str))
                selected = value.get("selected_continuation_language")
                if isinstance(selected, str):
                    tags.append(selected)
            if is_receipt_payload(value):
                tags.append(value["selected_continuation_language"])
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return tags, profiles


def qualify_languages(*values: Any) -> dict[str, Any]:
    tags, profiles = _collect_language_material(values)
    unique_tags = sorted(set(tags))
    try:
        qualification = run_registered_vector()
        registry, _ = pinned_registry()
    except LCHError as exc:
        return {
            "performed": False,
            "result": "NOT_RUN",
            "issues": [{"code": exc.code, "message": exc.message}],
            "registry_file_date": None,
            "registry_path": None,
            "registry_sha256_raw": None,
            "registry_byte_length": None,
            "extension_registry_file_date": None,
            "extension_registry_path": None,
            "extension_registry_sha256_raw": None,
            "extension_registry_byte_length": None,
            "unicode_version": unicodedata.unidata_version,
            "vector_id": "language-unicode-v1-001",
            "qualification_scope": None,
            "language_tags_present": bool(tags),
            "tag_count": len(unique_tags),
            "canonical_mappings": [],
            "not_claimed": [
                {"algorithm": "UAX9", "result": "NOT_RUN"},
                {"algorithm": "UAX29", "result": "NOT_RUN"},
                {"algorithm": "UTS39", "result": "NOT_RUN"},
                {"algorithm": "PACKAGE_CONTENT_NORMALIZATION", "result": "NOT_RUN"},
                {"algorithm": "PACKAGE_PROTECTED_SPAN_PRESERVATION", "result": "NOT_RUN"},
                {"algorithm": "PACKAGE_BIDI_CONTROL_SCAN", "result": "NOT_RUN"},
            ],
        }
    tag_results = {tag: qualify_tag(tag, registry) for tag in unique_tags}
    issues: list[dict[str, Any]] = []
    issue_keys: set[tuple[str, str]] = set()

    def add_issue(code: str, message: str, object_id: str) -> None:
        key = (code, object_id)
        if key not in issue_keys:
            issue_keys.add(key)
            issues.append({"code": code, "message": message, "object_id": object_id})

    for tag in unique_tags:
        if tag_results[tag].get("valid") is not True:
            add_issue(
                "BCP47_QUALIFICATION_FAIL",
                "language tag is not qualified by the pinned IANA snapshot",
                tag,
            )

    def canonical_key(tag: Any) -> str | None:
        if not isinstance(tag, str):
            return None
        result = tag_results.get(tag)
        canonical = result.get("canonical") if isinstance(result, dict) else None
        return canonical.casefold() if isinstance(canonical, str) else None

    for profile in profiles:
        for field, code, label in (
            (
                "content_languages",
                "CONTENT_LANGUAGE_CANONICAL_DUPLICATE",
                "content_languages contains a canonical case-insensitive duplicate",
            ),
            (
                "continuation_language_ranges",
                "CONTINUATION_LANGUAGE_CANONICAL_DUPLICATE",
                "continuation_language_ranges contains a canonical case-insensitive duplicate",
            ),
        ):
            items = profile.get(field)
            if not isinstance(items, list):
                continue
            seen: set[str] = set()
            for item in items:
                key = canonical_key(item)
                if key is None:
                    continue
                if key in seen:
                    add_issue(code, label, key)
                seen.add(key)

        selected = profile.get("selected_continuation_language")
        ranges = profile.get("continuation_language_ranges")
        selected_key = canonical_key(selected)
        if isinstance(ranges, list) and selected_key is not None:
            range_keys = [canonical_key(item) for item in ranges]
            if all(key is not None for key in range_keys) and selected_key not in range_keys:
                add_issue(
                    "SELECTED_CONTINUATION_LANGUAGE_MISMATCH",
                    "selected continuation language does not canonically equal a declared continuation language range",
                    selected_key,
                )

    canonical_mappings = sorted(
        (
            {"source": tag, "canonical": result["canonical"]}
            for tag, result in tag_results.items()
            if result.get("valid") is True and isinstance(result.get("canonical"), str)
        ),
        key=lambda item: (item["source"], item["canonical"]),
    )
    return {
        "performed": True,
        "result": "FAIL" if issues else "PASS",
        "issues": issues,
        "language_tags_present": bool(tags),
        "tag_count": len(unique_tags),
        "canonical_mappings": canonical_mappings,
        **qualification,
    }
