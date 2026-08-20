"""Load and integrity-check the release-pinned offline protocol registries."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Any

from .canonicalize import canonicalize, loads_strict, sha256_digest
from .util import LCHError, read_bytes


HANDOFF_ROOT = Path(__file__).resolve().parents[3]
ASSETS_ROOT = HANDOFF_ROOT / "assets"
PROTOCOL_VERSION_PATH = ASSETS_ROOT / "protocol-version.json"
MAX_PROTOCOL_ASSET_BYTES = 4 * 1024 * 1024
VECTOR_DIRECTORY = ASSETS_ROOT / "vectors"


def _strict_object(raw: bytes, *, code: str, label: str) -> dict[str, Any]:
    try:
        value = loads_strict(raw)
    except Exception as exc:
        raise LCHError(code, f"{label} is not strict JSON") from exc
    if not isinstance(value, dict):
        raise LCHError(code, f"{label} must be a JSON object")
    return value


def _asset_path(relative: Any, *, label: str) -> Path:
    if not isinstance(relative, str):
        raise LCHError("PROTOCOL_ASSET_PATH_FAIL", f"{label} path is missing")
    parsed = PurePosixPath(relative)
    if (
        parsed.is_absolute()
        or not parsed.parts
        or any(part in {"", ".", ".."} for part in parsed.parts)
        or "\\" in relative
        or ":" in relative
    ):
        raise LCHError("PROTOCOL_ASSET_PATH_FAIL", f"{label} path is unsafe")
    return ASSETS_ROOT.joinpath(*parsed.parts)


def _load_declared_asset(
    descriptor: dict[str, Any],
    *,
    label: str,
) -> tuple[dict[str, Any], bytes]:
    path = _asset_path(descriptor.get("path"), label=label)
    raw = read_bytes(path, max_bytes=MAX_PROTOCOL_ASSET_BYTES)
    expected_raw_length = descriptor.get("byte_length_raw")
    if isinstance(expected_raw_length, int) and len(raw) != expected_raw_length:
        raise LCHError("PROTOCOL_ASSET_LENGTH_FAIL", f"{label} raw byte length mismatch")
    expected_raw_digest = descriptor.get("sha256_raw")
    if not isinstance(expected_raw_digest, str) or sha256_digest(raw) != expected_raw_digest:
        raise LCHError("PROTOCOL_ASSET_HASH_FAIL", f"{label} raw SHA-256 mismatch")
    value = _strict_object(raw, code="PROTOCOL_ASSET_INVALID", label=label)
    canonical = canonicalize(value)
    expected_canonical_length = descriptor.get("byte_length_canonical")
    if isinstance(expected_canonical_length, int) and len(canonical) != expected_canonical_length:
        raise LCHError(
            "PROTOCOL_ASSET_CANONICAL_LENGTH_FAIL",
            f"{label} canonical byte length mismatch",
        )
    expected_canonical_digest = descriptor.get("sha256_canonical")
    if isinstance(expected_canonical_digest, str) and sha256_digest(canonical) != expected_canonical_digest:
        raise LCHError(
            "PROTOCOL_ASSET_CANONICAL_HASH_FAIL",
            f"{label} canonical SHA-256 mismatch",
        )
    return value, raw


@lru_cache(maxsize=1)
def protocol_assets() -> dict[str, dict[str, Any]]:
    raw = read_bytes(PROTOCOL_VERSION_PATH, max_bytes=256 * 1024)
    protocol = _strict_object(raw, code="PROTOCOL_VERSION_INVALID", label="protocol version")
    if protocol.get("protocol_version") != "0.1.0" or protocol.get("status") != "IMPLEMENTED":
        raise LCHError("PROTOCOL_VERSION_UNSUPPORTED", "bundled protocol version is unsupported")
    result: dict[str, dict[str, Any]] = {"protocol_version": protocol}
    for key, label in (
        ("profile_feature_registry", "profile and feature registry"),
        ("schema_catalog", "Schema catalog"),
        ("registry_lock", "language registry lock"),
        ("vector_catalog", "golden vector catalog"),
    ):
        descriptor = protocol.get(key)
        if not isinstance(descriptor, dict):
            raise LCHError("PROTOCOL_VERSION_INVALID", f"{label} descriptor is missing")
        result[key], _ = _load_declared_asset(descriptor, label=label)
    return result


def profile_feature_registry() -> dict[str, Any]:
    return protocol_assets()["profile_feature_registry"]


def schema_catalog() -> dict[str, Any]:
    return protocol_assets()["schema_catalog"]


def vector_catalog() -> dict[str, Any]:
    return protocol_assets()["vector_catalog"]


@lru_cache(maxsize=1)
def verified_vectors() -> dict[str, dict[str, Any]]:
    catalog = vector_catalog()
    entries = catalog.get("vectors")
    if not isinstance(entries, list):
        raise LCHError("VECTOR_CATALOG_INVALID", "vector catalog entries are missing")
    values: dict[str, dict[str, Any]] = {}
    expected_names: set[str] = set()
    entry_by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise LCHError("VECTOR_CATALOG_INVALID", "vector catalog entry is not an object")
        vector_id = entry.get("vector_id")
        name = entry.get("path")
        if (
            not isinstance(vector_id, str)
            or not isinstance(name, str)
            or PurePosixPath(name).name != name
            or not name.endswith(".json")
            or name == "index.json"
            or name in expected_names
            or vector_id in entry_by_id
        ):
            raise LCHError("VECTOR_CATALOG_INVALID", "vector ID or path is unsafe or duplicated")
        expected_names.add(name)
        entry_by_id[vector_id] = entry
        raw = read_bytes(VECTOR_DIRECTORY / name, max_bytes=MAX_PROTOCOL_ASSET_BYTES)
        if len(raw) != entry.get("byte_length_raw") or sha256_digest(raw) != entry.get("sha256_raw"):
            raise LCHError("VECTOR_INTEGRITY_FAIL", f"golden vector raw integrity mismatch: {name}")
        value = _strict_object(raw, code="VECTOR_INVALID", label=f"golden vector {name}")
        canonical = canonicalize(value)
        if (
            len(canonical) != entry.get("byte_length_canonical")
            or sha256_digest(canonical) != entry.get("sha256_canonical")
        ):
            raise LCHError("VECTOR_CANONICAL_INTEGRITY_FAIL", f"golden vector JCS integrity mismatch: {name}")
        if value.get("vector_id") != vector_id or value.get("kind") != entry.get("kind"):
            raise LCHError("VECTOR_ID_MISMATCH", f"golden vector ID or kind mismatch: {name}")
        values[vector_id] = value
    actual_names = {
        path.name for path in VECTOR_DIRECTORY.glob("*.json") if path.name != "index.json"
    }
    if actual_names != expected_names:
        raise LCHError("VECTOR_CATALOG_CLOSURE_FAIL", "golden vector directory differs from its catalog")

    profile_registry = profile_feature_registry()
    for profile in profile_registry.get("profiles", []):
        qualification = profile.get("qualification") if isinstance(profile, dict) else None
        vector_ids = qualification.get("vector_ids", []) if isinstance(qualification, dict) else []
        if not isinstance(vector_ids, list) or any(vector_id not in values for vector_id in vector_ids):
            raise LCHError(
                "PROFILE_VECTOR_UNRESOLVED",
                "Profile qualification references an absent golden vector",
            )

    direct = protocol_assets()["protocol_version"].get("language_unicode_vector")
    language_entry = entry_by_id.get("language-unicode-v1-001")
    if not isinstance(direct, dict) or not isinstance(language_entry, dict):
        raise LCHError("PROTOCOL_VERSION_INVALID", "language vector compatibility lock is missing")
    comparable = {
        "path": "vectors/" + str(language_entry.get("path")),
        "byte_length_raw": language_entry.get("byte_length_raw"),
        "sha256_raw": language_entry.get("sha256_raw"),
        "byte_length_canonical": language_entry.get("byte_length_canonical"),
        "sha256_canonical": language_entry.get("sha256_canonical"),
    }
    if any(direct.get(key) != value for key, value in comparable.items()):
        raise LCHError("VECTOR_LOCK_CONFLICT", "direct language vector lock differs from vector catalog")
    return values


def language_unicode_vector() -> dict[str, Any]:
    return verified_vectors()["language-unicode-v1-001"]


def registry_lock() -> dict[str, Any]:
    return protocol_assets()["registry_lock"]
