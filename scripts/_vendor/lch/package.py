"""Native Bundle and T0 draft packing plus length-safe transport readers."""

from __future__ import annotations

import base64
import json
import math
import os
import re
import shutil
import stat
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator

from .canonicalize import canonicalize, loads_strict, sha256_digest, sha256_hex
from .language import qualify_languages
from .projection import canonical_state_digest, review_projection_v1
from .registry import profile_feature_registry

from .schema import SchemaStore, Validator
from .security import scan_bytes
from .util import (
    LCHError,
    atomic_commit_no_replace,
    atomic_write,
    check_json_depth,
    ensure_unique_paths,
    lexical_absolute,
    read_bytes,
    reject_symlink_ancestry,
    safe_relative_path,
    secure_output_path,
)


HANDOFF_ROOT = Path(__file__).resolve().parents[3]
SCHEMA_DIRECTORY = HANDOFF_ROOT / "assets" / "schemas"
MATERIALITY_PROFILE_PATH = HANDOFF_ROOT / "assets" / "profiles" / "materiality-v1.json"
CHUNK_SIZE = 4096
MAX_JSON_BYTES = 32 * 1024 * 1024
MAX_OBJECT_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_OBJECTS = 4096
MAX_COMPRESSION_RATIO = 100
MAX_JSON_DEPTH = 128

STATE_COLLECTION_PATHS: tuple[tuple[str, ...], ...] = (
    ("records",),
    ("transition_events",),
    ("action_graph", "actions"),
    ("action_graph", "action_edges"),
    ("action_graph", "action_groups"),
    ("source_inventory", "entries"),
    ("source_inventory", "gaps"),
    ("content_coverage", "omissions"),
)

FORBIDDEN_ROOT_RESULT_KEYS = frozenset(
    {
        "approvalgate",
        "approvalstatement",
        "approvalverification",
        "authorizationresult",
        "authorizationsummary",
        "benchmarkresult",
        "byteconsistency",
        "byteconsistencyresult",
        "continuationstatus",
        "coverageverification",
        "inventoryauthenticity",
        "inventoryscopecoverage",
        "losslessconformance",
        "losslesspass",
        "originverification",
        "packagevsinventorycoverage",
        "receiverreceipt",
        "receiverrunresult",
        "receipt",
        "receiptattestation",
        "securityrunresult",
        "semanticcontinuityresult",
        "structureconformance",
        "structureresult",
        "reviewprojectionconformance",
        "reviewprojectionresult",
    }
)

ROOT_WARM_EQUALITY: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("protocol_version", ("protocol_version",)),
    ("source_boundary", ("boundaries", "source_boundary")),
    ("scope", ("boundaries", "scope")),
    ("policy_boundary", ("boundaries", "policy_boundary")),
    (
        "external_state_dependencies",
        ("boundaries", "external_state_dependencies"),
    ),
    ("content_coverage", ("content_coverage",)),
    ("consistency_claim", ("consistency_claim",)),
    ("semantic_actionability_claim", ("semantic_actionability_claim",)),
    ("language_profile", ("language_profile",)),
    ("materiality_profile_ref", ("materiality_profile_ref",)),
)

T0_HEADER_RE = re.compile(rb"LCH-T0 ([0-9]+\.[0-9]+)\n")
T0_LENGTH_RE = re.compile(rb"control-byte-length: (0|[1-9][0-9]*)\n")
T0_HASH_RE = re.compile(rb"control-sha256: ([0-9a-f]{64})\n")
T0_CHUNK_RE = re.compile(
    rb"LCH-T0-EMBEDDED ([1-9][0-9]*) ([A-Za-z][A-Za-z0-9._:-]*) "
    rb"([1-9][0-9]*)/([1-9][0-9]*) ([1-9][0-9]*)\n"
)
T0_DETACHED_RE = re.compile(
    rb"LCH-T0-DETACHED ([A-Za-z][A-Za-z0-9._:-]*) "
    rb"([A-Za-z][A-Za-z0-9._:-]*) (0|[1-9][0-9]*) ((?:sha256:)?[0-9a-f]{64})\n"
)


def _schema_validator() -> Validator:
    return Validator(SchemaStore(SCHEMA_DIRECTORY))


def bundled_materiality_ref() -> dict[str, str]:
    raw = read_bytes(MATERIALITY_PROFILE_PATH, max_bytes=MAX_JSON_BYTES)
    try:
        value = loads_strict(raw)
    except Exception as exc:
        raise LCHError("MATERIALITY_PROFILE_INVALID", "bundled materiality Profile is not strict JSON") from exc
    if not isinstance(value, dict):
        raise LCHError("MATERIALITY_PROFILE_INVALID", "bundled materiality Profile must be an object")
    problems = _schema_validator().validate(value, "materiality-profile.schema.json")
    if problems:
        raise LCHError(
            "MATERIALITY_PROFILE_SCHEMA_FAIL",
            "bundled materiality Profile fails its Schema",
            details=[item.as_dict() for item in problems],
        )
    return {
        "id": value["profile_id"],
        "version": value["profile_version"],
        "sha256": sha256_digest(canonicalize(value)),
    }


def root_result_key_hits(root: dict[str, Any]) -> list[str]:
    """Find post-seal or foreign-role result keys hidden in a Producer root."""

    hits: set[str] = set()
    stack: list[Any] = [root]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            for key, child in value.items():
                if isinstance(key, str):
                    token = re.sub(r"[^a-z0-9]", "", key.casefold())
                    if token in FORBIDDEN_ROOT_RESULT_KEYS:
                        hits.add(key)
                stack.append(child)
        elif isinstance(value, list):
            stack.extend(value)
    return sorted(hits)


def root_capability_issues(root: dict[str, Any]) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    registry = profile_feature_registry()
    registered_profiles = {
        (item.get("id"), item.get("version")): item
        for item in registry.get("profiles", [])
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and isinstance(item.get("version"), str)
    }
    supported_features = {
        item.get("id")
        for item in registry.get("features", [])
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and item.get("status") == "SUPPORTED"
    }
    registered_profile_ids = {
        item.get("id")
        for item in registry.get("profiles", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    registered_feature_ids = {
        item.get("id")
        for item in registry.get("features", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    profiles = root.get("profiles")
    profiles = profiles if isinstance(profiles, list) else []
    seen_versions: dict[str, str] = {}
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        profile_id = profile.get("id")
        version = profile.get("version")
        if profile_id in registered_feature_ids:
            issues.append(("FEATURE_IN_PROFILE_LIST", str(profile_id)))
        if isinstance(profile_id, str):
            if profile_id in seen_versions:
                issues.append(("PROFILE_ID_DUPLICATE", profile_id))
                if seen_versions[profile_id] != version:
                    issues.append(("PROFILE_VERSION_CONFLICT", profile_id))
            elif isinstance(version, str):
                seen_versions[profile_id] = version
        definition = registered_profiles.get((profile_id, version))
        if definition is not None and definition.get("selectable") is not True:
            issues.append(("PROFILE_NOT_SELECTABLE", str(profile_id)))
        if definition is not None and definition.get("status") not in {
            "SUPPORTED",
            "QUALIFIED_SUBSET",
        }:
            issues.append(("PROFILE_STATUS_UNSUPPORTED", str(profile_id)))
        if profile.get("required") is True:
            if (
                definition is None
                or definition.get("selectable") is not True
                or definition.get("status") not in {"SUPPORTED", "QUALIFIED_SUBSET"}
            ):
                issues.append(("REQUIRED_PROFILE_UNSUPPORTED", str(profile_id)))
    required_extensions = root.get("must_understand")
    required_extensions = (
        required_extensions if isinstance(required_extensions, list) else []
    )
    for extension in required_extensions:
        if extension in registered_profile_ids:
            issues.append(("PROFILE_IN_MUST_UNDERSTAND", str(extension)))
        if extension not in supported_features:
            issues.append(("MUST_UNDERSTAND_UNSUPPORTED", str(extension)))
    return issues


def root_capability_warnings(root: dict[str, Any]) -> list[tuple[str, str]]:
    """Report optional Profiles preserved inert because this release cannot resolve them."""

    registry = profile_feature_registry()
    registered_profiles = {
        (item.get("id"), item.get("version"))
        for item in registry.get("profiles", [])
        if isinstance(item, dict)
        and isinstance(item.get("id"), str)
        and isinstance(item.get("version"), str)
    }
    registered_feature_ids = {
        item.get("id")
        for item in registry.get("features", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    warnings: list[tuple[str, str]] = []
    profiles = root.get("profiles")
    profile_items = profiles if isinstance(profiles, list) else []
    id_counts: dict[str, int] = {}
    for profile in profile_items:
        profile_id = profile.get("id") if isinstance(profile, dict) else None
        if isinstance(profile_id, str):
            id_counts[profile_id] = id_counts.get(profile_id, 0) + 1
    for profile in profile_items:
        if not isinstance(profile, dict) or profile.get("required") is not False:
            continue
        profile_id = profile.get("id")
        version = profile.get("version")
        if (
            not isinstance(profile_id, str)
            or not isinstance(version, str)
            or id_counts.get(profile_id) != 1
            or profile_id in registered_feature_ids
        ):
            continue
        if (profile_id, version) in registered_profiles:
            continue
        subject = f"{profile_id}:{version}"
        warnings.append(("OPTIONAL_PROFILE_INERT", subject))
    return warnings


def manifest_reference_issues(
    objects: list[Any],
    warm: dict[str, Any],
) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    object_ids = {
        item.get("object_id")
        for item in objects
        if isinstance(item, dict) and isinstance(item.get("object_id"), str)
    }
    inventory = warm.get("source_inventory")
    entries = inventory.get("entries", []) if isinstance(inventory, dict) else []
    source_ids = {
        item.get("source_id")
        for item in entries
        if isinstance(item, dict) and isinstance(item.get("source_id"), str)
    }
    graph: dict[str, set[str]] = {object_id: set() for object_id in object_ids}
    for item in objects:
        if not isinstance(item, dict) or not isinstance(item.get("object_id"), str):
            continue
        object_id = item["object_id"]
        source_refs = item.get("source_refs")
        source_refs = source_refs if isinstance(source_refs, list) else []
        for source_ref in source_refs:
            if source_ref not in source_ids:
                issues.append(("MANIFEST_SOURCE_REF_DANGLING", object_id))
        derived_from = item.get("derived_from")
        derived_from = derived_from if isinstance(derived_from, list) else []
        for parent in derived_from:
            if parent not in object_ids:
                issues.append(("MANIFEST_DERIVATION_DANGLING", object_id))
            elif parent == object_id:
                issues.append(("MANIFEST_DERIVATION_SELF", object_id))
            else:
                graph[object_id].add(parent)

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return False
        if node in visited:
            return True
        visiting.add(node)
        if any(not visit(parent) for parent in graph.get(node, set())):
            return False
        visiting.remove(node)
        visited.add(node)
        return True

    if any(not visit(object_id) for object_id in sorted(object_ids)):
        issues.append(("MANIFEST_DERIVATION_CYCLE", "manifest"))
    return issues


def state_resource_issues(warm: dict[str, Any]) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    for path in STATE_COLLECTION_PATHS:
        value: Any = warm
        for member in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(member)
        if isinstance(value, list) and len(value) > MAX_OBJECTS:
            issues.append(("STATE_COLLECTION_LIMIT", ".".join(path)))
    return issues


def root_warm_mismatches(root: dict[str, Any], warm: dict[str, Any]) -> list[str]:
    """Return every root claim whose canonical WARM projection is not identical."""

    mismatches: list[str] = []
    for root_key, warm_path in ROOT_WARM_EQUALITY:
        value: Any = warm
        for member in warm_path:
            if not isinstance(value, dict) or member not in value:
                value = object()
                break
            value = value[member]
        if root.get(root_key) != value:
            mismatches.append(root_key)
    warm_boundaries = warm.get("boundaries") if isinstance(warm.get("boundaries"), dict) else {}
    warm_coverage = warm.get("content_coverage") if isinstance(warm.get("content_coverage"), dict) else {}
    root_coverage = root.get("content_coverage") if isinstance(root.get("content_coverage"), dict) else {}
    if (
        root_coverage.get("scope") != root.get("scope")
        or warm_coverage.get("scope") != warm_boundaries.get("scope")
    ):
        mismatches.append("content_coverage.scope")
    return mismatches


def _localized_name(object_id: str) -> dict[str, Any]:
    return {
        "text_id": object_id + ".logical_name",
        "value": object_id,
        "lang": "zxx",
        "dir": "ltr",
        "kind": "canonical_assertion",
        "authority": "canonical_assertion",
        "fidelity": "derived_restatement",
        "translation_of": None,
        "translation_method": None,
        "review_status": "not_applicable",
    }


def _validate_pack_boundary(root: dict[str, Any]) -> None:
    approval = root.get("approval_claim")
    if not isinstance(approval, dict) or approval.get("state") != "PROPOSED":
        raise LCHError("DRAFT_APPROVAL_REQUIRED", "pack accepts only approval_claim.state PROPOSED")
    if root.get("structure_self_check") != "NOT_RUN":
        raise LCHError("DRAFT_SELF_CHECK_REQUIRED", "pack requires structure_self_check NOT_RUN")

    capability_issues = root_capability_issues(root)
    if capability_issues:
        raise LCHError(
            capability_issues[0][0],
            "draft root declares an unsupported required protocol capability",
            details=[{"code": code, "subject": subject} for code, subject in capability_issues],
        )

    forbidden_hits = root_result_key_hits(root)
    if forbidden_hits:
        raise LCHError(
            "ROLE_BOUNDARY_VIOLATION",
            "draft root contains a post-seal or foreign-role result key",
            details=forbidden_hits,
        )

    slots = root.get("detached_envelope_slots")
    if not isinstance(slots, list):
        raise LCHError("SLOT_POLICY_MISSING", "detached_envelope_slots must be an array")
    required_slots = [
        item for item in slots if isinstance(item, dict) and item.get("required") is True
    ]
    required_types = {item.get("expected_type") for item in required_slots}
    missing_types = {
        "review_projection_conformance",
        "approval_statement",
        "approval_verification",
    } - required_types
    if missing_types:
        raise LCHError(
            "REQUIRED_SLOT_MISSING",
            "draft root is missing required detached result slots",
            details=sorted(missing_types),
        )
    slot_ids = [item.get("opaque_id") for item in slots if isinstance(item, dict)]
    if any(not isinstance(item, str) for item in slot_ids):
        raise LCHError("SLOT_ID_INVALID", "detached slot opaque IDs must be stable strings")
    if len(slot_ids) != len(set(slot_ids)):
        raise LCHError("DUPLICATE_SLOT_ID", "detached slot opaque IDs must be unique")
    for expected_type in (
        "review_projection_conformance",
        "approval_statement",
        "approval_verification",
    ):
        if sum(item.get("expected_type") == expected_type for item in required_slots) != 1:
            raise LCHError(
                "REQUIRED_SLOT_CARDINALITY",
                "each required review and approval slot type must occur exactly once",
            )
    scoped = root.get("scope", {}).get("approval_statement_slot") if isinstance(root.get("scope"), dict) else None
    claimed = approval.get("approval_statement_slot")
    statement_ids = {
        item.get("opaque_id")
        for item in slots
        if isinstance(item, dict) and item.get("expected_type") == "approval_statement"
    }
    if scoped != claimed or scoped not in statement_ids:
        raise LCHError("APPROVAL_SLOT_MISMATCH", "scope, approval claim, and statement slot must agree")
    coverage = root.get("content_coverage")
    if not isinstance(coverage, dict) or coverage.get("scope") != root.get("scope"):
        raise LCHError(
            "COVERAGE_SCOPE_MISMATCH",
            "root content_coverage.scope must equal root scope",
        )
    coverage_slot_ids = coverage.get("coverage_envelope_slot_ids")
    declared_slot_ids = set(slot_ids)
    if not isinstance(coverage_slot_ids, list) or any(
        not isinstance(opaque_id, str) or opaque_id not in declared_slot_ids
        for opaque_id in coverage_slot_ids
    ):
        raise LCHError(
            "COVERAGE_SLOT_DANGLING",
            "coverage envelope slot IDs must resolve to declared detached slots",
        )


def _security_gate(
    objects: list[tuple[str, bytes, list[str], str]],
) -> None:
    findings: list[dict[str, str]] = []
    for object_id, data, logical_names, media_type in objects:
        for logical_name in sorted(set(logical_names)) or [""]:
            findings.extend(
                scan_bytes(
                    data,
                    object_id=object_id,
                    suffix=Path(logical_name).suffix,
                    media_type=media_type,
                    logical_name=logical_name,
                )
            )
    findings = list(
        {
            (item["code"], item["object_id"]): item
            for item in findings
        }.values()
    )
    if findings:
        raise LCHError(
            "SECURITY_SCAN_BLOCKED",
            "packing refused after a conservative security scan hit",
            details=sorted(findings, key=lambda item: (item["object_id"], item["code"])),
        )


def _load_object_specs(path: Path, *, maximum: int) -> list[dict[str, Any]]:
    raw = read_bytes(path, max_bytes=MAX_JSON_BYTES)
    try:
        value = loads_strict(raw)
    except Exception as exc:
        raise LCHError("OBJECT_MAP_INVALID", "object map is not strict JSON") from exc
    check_json_depth(value, maximum=MAX_JSON_DEPTH)
    if isinstance(value, dict) and set(value) == {"objects"}:
        value = value["objects"]
    if not isinstance(value, list):
        raise LCHError("OBJECT_MAP_INVALID", "object map must be an array or {objects: [...]}")
    if len(value) > maximum:
        raise LCHError("OBJECT_LIMIT_EXCEEDED", f"object map exceeds the transport budget of {maximum} objects")
    specs: list[dict[str, Any]] = []
    ids: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise LCHError("OBJECT_MAP_INVALID", f"object map item {index} is not an object")
        allowed = {
            "object_id", "source_path", "bundle_path", "logical_name", "role",
            "media_type", "charset", "source_refs", "authority", "derived_from",
        }
        if set(item) - allowed:
            raise LCHError("OBJECT_MAP_INVALID", f"object map item {index} has unknown staging keys")
        required = {"object_id", "source_path", "bundle_path", "role", "media_type"}
        if required - set(item):
            raise LCHError("OBJECT_MAP_INVALID", f"object map item {index} is missing staging keys")
        object_id = item["object_id"]
        if not isinstance(object_id, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9._:-]*", object_id):
            raise LCHError("OBJECT_ID_INVALID", f"object map item {index} has an invalid object_id")
        if object_id in ids:
            raise LCHError("DUPLICATE_OBJECT_ID", "object IDs must be unique")
        ids.add(object_id)
        safe_relative_path(item["bundle_path"])
        if item["role"] not in {"transcript", "evidence", "artifact", "imported_source"}:
            raise LCHError("OBJECT_ROLE_INVALID", "extra objects must use a COLD or artifact role")
        source_path = reject_symlink_ancestry(
            Path(item["source_path"]), code="OBJECT_SOURCE_SYMLINK"
        )
        data = read_bytes(source_path, max_bytes=MAX_OBJECT_BYTES)
        spec = dict(item)
        spec["_source_path"] = source_path
        spec["_data"] = data
        specs.append(spec)
    ensure_unique_paths([item["bundle_path"] for item in specs])
    if not any(item["bundle_path"].startswith("cold/") for item in specs):
        raise LCHError("COLD_OBJECT_REQUIRED", "at least one extra object must use a cold/ path")
    if sum(len(item["_data"]) for item in specs) > MAX_TOTAL_BYTES:
        raise LCHError("TOTAL_SIZE_EXCEEDED", "staged object bytes exceed the total limit")
    return specs


def _review_context(root: dict[str, Any], integrity_kind: str, state_digest: str) -> dict[str, Any]:
    origin = root.get("origin_claim") if isinstance(root.get("origin_claim"), dict) else {}
    recipient = origin.get("recipient_binding")
    return {
        "protocol_id": root.get("protocol_id", "lossless-context-handoff"),
        "package_id": root["package_id"],
        "profiles": root["profiles"],
        "integrity_kind": integrity_kind,
        "integrity_algorithm": "sha-256",
        "canonical_state_digest": state_digest,
        "recipient_and_sharing_scope": recipient,
        "detached_envelope_policy": root["detached_envelope_slots"],
    }


def _prepare(
    root_path: Path,
    warm_path: Path,
    object_map_path: Path,
    *,
    integrity_kind: str,
) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes, list[dict[str, Any]]]:
    for staged_path in (root_path, warm_path, object_map_path):
        reject_symlink_ancestry(staged_path, code="PACK_INPUT_SYMLINK")
    try:
        root_value = loads_strict(read_bytes(root_path, max_bytes=MAX_JSON_BYTES))
        warm = loads_strict(read_bytes(warm_path, max_bytes=MAX_JSON_BYTES))
    except LCHError:
        raise
    except Exception as exc:
        raise LCHError("PACK_INPUT_INVALID", "root or WARM is not strict JSON") from exc
    if not isinstance(root_value, dict) or not isinstance(warm, dict):
        raise LCHError("PACK_INPUT_INVALID", "root and WARM must be JSON objects")
    check_json_depth(root_value, maximum=MAX_JSON_DEPTH)
    check_json_depth(warm, maximum=MAX_JSON_DEPTH)
    resource_issues = state_resource_issues(warm)
    if resource_issues:
        raise LCHError(
            "STATE_RESOURCE_LIMIT",
            "staged WARM state exceeds a frozen collection limit",
            details=[{"code": code, "path": path} for code, path in resource_issues],
        )
    warm_problems = _schema_validator().validate(warm, "state.schema.json")
    if warm_problems:
        raise LCHError(
            "WARM_SCHEMA_FAIL",
            "staged WARM state fails bundled Schema",
            details=[item.as_dict() for item in warm_problems],
        )
    root = deepcopy(root_value)
    for generated in ("objects", "embedded_objects", "integrity"):
        if generated in root:
            raise LCHError("PRESEALED_INPUT_FORBIDDEN", f"pack input must not contain generated {generated}")
    _validate_pack_boundary(root)
    mismatches = root_warm_mismatches(root, warm)
    if mismatches:
        raise LCHError(
            "ROOT_WARM_PROJECTION_MISMATCH",
            "staged root and WARM shared protocol fields must be identical",
            details=mismatches,
        )
    language_qualification = qualify_languages(root, warm)
    multilingual_required = any(
        isinstance(profile, dict)
        and profile.get("id") == "urn:lch:profile:multilingual"
        and profile.get("required") is True
        for profile in root.get("profiles", [])
    )
    if language_qualification.get("performed") is not True and (
        language_qualification.get("language_tags_present") is True
        or multilingual_required
    ):
        raise LCHError(
            "LANGUAGE_QUALIFICATION_NOT_RUN",
            "pinned RFC 5646 qualification could not run for staged language tags",
            details=language_qualification.get("issues", []),
        )
    if (
        language_qualification.get("performed") is True
        and language_qualification.get("result") != "PASS"
    ):
        raise LCHError(
            "LANGUAGE_QUALIFICATION_FAIL",
            "staged language tags are not qualified by the pinned registry",
            details=language_qualification.get("issues", []),
        )
    if root.get("materiality_profile_ref") != bundled_materiality_ref():
        raise LCHError(
            "MATERIALITY_PROFILE_REF_FAIL",
            "staged materiality_profile_ref does not match the bundled frozen Profile",
        )
    maximum_specs = MAX_OBJECTS - (4 if integrity_kind == "bundle_manifest" else 1)
    specs = _load_object_specs(object_map_path, maximum=maximum_specs)
    state_digest = canonical_state_digest(warm)
    declared_state_digest = root.get("canonical_state_digest")
    if declared_state_digest is not None and declared_state_digest != state_digest:
        raise LCHError("STATE_DIGEST_MISMATCH", "staged canonical_state_digest is stale")
    root["canonical_state_digest"] = state_digest
    context = _review_context(root, integrity_kind, state_digest)
    review = review_projection_v1(warm, context)
    review_ref = {
        "kind": "bundle_handoff" if integrity_kind == "bundle_manifest" else "t0_human_view",
        "projection_version": "review-v1",
        "sha256_raw": sha256_digest(review),
        "byte_length": len(review),
    }
    declared_review = root.get("review_projection_ref")
    if declared_review is not None and declared_review != review_ref:
        raise LCHError("REVIEW_REF_MISMATCH", "staged review_projection_ref is stale")
    root["review_projection_ref"] = review_ref
    root["byte_digests_present"] = "YES"
    warm_bytes = canonicalize(warm)
    security_objects = [
        ("package_root_staging", canonicalize(root), ["root.json"], "application/json"),
        ("warm_state", warm_bytes, ["warm.json"], "application/json"),
        ("review_projection", review, ["HANDOFF.md"], "text/markdown"),
    ] + [
        (
            item["object_id"],
            item["_data"],
            [
                Path(item["source_path"]).name,
                item["bundle_path"],
            ],
            item["media_type"],
        )
        for item in specs
    ]
    _security_gate(security_objects)
    return root, warm, warm_bytes, review, specs


def _manifest_object(
    *,
    object_id: str,
    path: str,
    role: str,
    media_type: str,
    charset: str | None,
    data: bytes,
    logical_name: Any = None,
    source_refs: Any = None,
    authority: str,
    derived_from: Any = None,
) -> dict[str, Any]:
    return {
        "object_id": object_id,
        "location": {"kind": "path", "path": path, "section_id": None, "encoding": "identity"},
        "logical_name": logical_name if logical_name is not None else _localized_name(object_id),
        "role": role,
        "media_type": media_type,
        "charset": charset,
        "byte_length": len(data),
        "sha256_raw": sha256_digest(data),
        "source_refs": source_refs if isinstance(source_refs, list) else [],
        "authority": authority,
        "derived_from": derived_from if isinstance(derived_from, list) else [],
    }


def _write_bundle_tree(output: Path, files: dict[str, bytes]) -> None:
    output = secure_output_path(output)
    stage = Path(tempfile.mkdtemp(prefix=".lch-bundle-", dir=str(output.parent)))
    try:
        os.chmod(stage, 0o700)
        for relative, data in sorted(files.items()):
            if relative not in {"MANIFEST.json", "MANIFEST.sha256"}:
                safe_relative_path(relative, allow_envelopes=False)
            target = stage / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(target.parent, 0o700)
            target.write_bytes(data)
            os.chmod(target, 0o600)
        atomic_commit_no_replace(stage, output)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def _write_bundle_zip(output: Path, files: dict[str, bytes]) -> None:
    output = secure_output_path(output)
    descriptor, temp_name = tempfile.mkstemp(prefix=".lch-bundle-", suffix=".zip", dir=str(output.parent))
    os.close(descriptor)
    temp = Path(temp_name)
    try:
        with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            for relative, data in sorted(files.items()):
                if relative not in {"MANIFEST.json", "MANIFEST.sha256"}:
                    safe_relative_path(relative, allow_envelopes=False)
                info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
                info.create_system = 3
                info.external_attr = (stat.S_IFREG | 0o600) << 16
                info.compress_type = zipfile.ZIP_STORED
                archive.writestr(info, data)
        os.chmod(temp, 0o600)
        atomic_commit_no_replace(temp, output)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def pack_bundle(
    root_path: Path,
    warm_path: Path,
    object_map_path: Path,
    output: Path,
    *,
    archive: bool,
) -> dict[str, Any]:
    root, warm, warm_bytes, review, specs = _prepare(
        root_path, warm_path, object_map_path, integrity_kind="bundle_manifest"
    )
    handoff_id = "handoff_review"
    warm_id = "warm_state"
    used_ids = {item["object_id"] for item in specs}
    if handoff_id in used_ids or warm_id in used_ids:
        raise LCHError("RESERVED_OBJECT_ID", "object map uses a generated object ID")
    objects = [
        _manifest_object(
            object_id=handoff_id,
            path="HANDOFF.md",
            role="handoff_view",
            media_type="text/markdown",
            charset="utf-8",
            data=review,
            authority="derived_view",
            derived_from=[warm_id],
        ),
        _manifest_object(
            object_id=warm_id,
            path="state/warm.json",
            role="state",
            media_type="application/json",
            charset="utf-8",
            data=warm_bytes,
            authority="normative",
            derived_from=[item["object_id"] for item in specs],
        ),
    ]
    files: dict[str, bytes] = {"HANDOFF.md": review, "state/warm.json": warm_bytes}
    for item in specs:
        bundle_path = item["bundle_path"]
        data = item["_data"]
        objects.append(
            _manifest_object(
                object_id=item["object_id"],
                path=bundle_path,
                role=item["role"],
                media_type=item["media_type"],
                charset=item.get("charset"),
                data=data,
                logical_name=item.get("logical_name"),
                source_refs=item.get("source_refs"),
                authority=item.get("authority", "source_evidence"),
                derived_from=item.get("derived_from"),
            )
        )
        files[bundle_path] = data
    ensure_unique_paths(files)
    root["integrity"] = {
        "algorithm": "sha-256",
        "manifest_canonicalization": "RFC8785-JCS",
        "canonicalization_profile": "state-projection-v1",
    }
    root["objects"] = objects
    reference_issues = manifest_reference_issues(objects, warm)
    if reference_issues:
        raise LCHError(
            reference_issues[0][0],
            "generated Manifest contains a dangling or cyclic reference",
            details=[{"code": code, "object_id": object_id} for code, object_id in reference_issues],
        )
    problems = _schema_validator().validate(root, "manifest.schema.json")
    if problems:
        raise LCHError("MANIFEST_SCHEMA_FAIL", "generated Manifest fails bundled Schema", details=[item.as_dict() for item in problems])
    manifest = canonicalize(root)
    files["MANIFEST.json"] = manifest
    files["MANIFEST.sha256"] = (sha256_hex(manifest) + "\n").encode("ascii")
    if len(files) > MAX_OBJECTS:
        raise LCHError("OBJECT_LIMIT_EXCEEDED", "generated Bundle exceeds file count limit")
    if any(len(data) > MAX_OBJECT_BYTES for data in files.values()):
        raise LCHError("OBJECT_LIMIT_EXCEEDED", "generated Bundle member exceeds size limit")
    if sum(len(data) for data in files.values()) > MAX_TOTAL_BYTES:
        raise LCHError("TOTAL_SIZE_EXCEEDED", "generated Bundle exceeds total byte limit")
    if archive:
        _write_bundle_zip(output, files)
    else:
        _write_bundle_tree(output, files)
    integrity_ref = {
        "kind": "bundle_manifest",
        "sha256": sha256_digest(manifest),
        "byte_length": len(manifest),
    }
    return {
        "ok": True,
        "operation": "pack_handoff",
        "transport": "bundle_zip" if archive else "bundle_directory",
        "draft": True,
        "output": str(lexical_absolute(output)),
        "package_id": root["package_id"],
        "package_integrity_ref": integrity_ref,
        "canonical_state_digest": root["canonical_state_digest"],
        "review_projection_ref": root["review_projection_ref"],
        "rooted_object_count": len(objects),
        "issued_results": [],
        "approval_claim": "PROPOSED",
        "capability_processing": {
            "result": "WARN" if root_capability_warnings(root) else "NO_ISSUES",
            "issues": [
                {"code": "LCH-" + code.replace("_", "-"), "subject": subject}
                for code, subject in root_capability_warnings(root)
            ],
        },
    }


def _encoded_object(object_id: str, ordinal: int, media_type: str, data: bytes) -> tuple[dict[str, Any], str]:
    encoded = base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")
    count = math.ceil(len(encoded) / CHUNK_SIZE) if encoded else 0
    metadata = {
        "object_id": object_id,
        "ordinal": ordinal,
        "media_type": media_type,
        "encoding": "base64url",
        "encoded_byte_length": len(encoded),
        "decoded_byte_length": len(data),
        "chunk_size": CHUNK_SIZE,
        "chunk_count": count,
        "sha256_raw": sha256_digest(data),
    }
    return metadata, encoded


def _t0_bytes(control: bytes, encoded: list[tuple[dict[str, Any], str]], review: bytes, version: str) -> bytes:
    major_minor = ".".join(version.split(".")[:2])
    parts = [
        f"LCH-T0 {major_minor}\n".encode("ascii"),
        f"control-byte-length: {len(control)}\n".encode("ascii"),
        f"control-sha256: {sha256_hex(control)}\n".encode("ascii"),
        control,
        b"\n",
    ]
    for metadata, text in encoded:
        count = metadata["chunk_count"]
        for index in range(count):
            chunk = text[index * CHUNK_SIZE : (index + 1) * CHUNK_SIZE]
            parts.append(
                (
                    f"LCH-T0-EMBEDDED {metadata['ordinal']} {metadata['object_id']} "
                    f"{index + 1}/{count} {len(chunk)}\n"
                ).encode("ascii")
            )
            parts.append(chunk.encode("ascii"))
            parts.append(b"\n")
    parts.append(b"LCH-T0-HUMAN-VIEW\n")
    parts.append(review)
    return b"".join(parts)


def pack_t0(
    root_path: Path,
    warm_path: Path,
    object_map_path: Path,
    output: Path,
) -> dict[str, Any]:
    root, warm, warm_bytes, review, specs = _prepare(
        root_path, warm_path, object_map_path, integrity_kind="t0_control"
    )
    used_ids = {item["object_id"] for item in specs}
    if "warm_state" in used_ids:
        raise LCHError("RESERVED_OBJECT_ID", "object map uses generated object ID warm_state")
    sources = [("warm_state", "application/json", warm_bytes)] + [
        (item["object_id"], item["media_type"], item["_data"]) for item in specs
    ]
    encoded: list[tuple[dict[str, Any], str]] = []
    for ordinal, (object_id, media_type, data) in enumerate(sources, 1):
        encoded.append(_encoded_object(object_id, ordinal, media_type, data))
    root["embedded_objects"] = [metadata for metadata, _ in encoded]
    problems = _schema_validator().validate(root, "t0-control.schema.json")
    if problems:
        raise LCHError("T0_CONTROL_SCHEMA_FAIL", "generated T0 control fails bundled Schema", details=[item.as_dict() for item in problems])
    control = canonicalize(root)
    artifact = _t0_bytes(control, encoded, review, root["protocol_version"])
    if len(encoded) > MAX_OBJECTS:
        raise LCHError("OBJECT_LIMIT_EXCEEDED", "generated T0 exceeds embedded object count limit")
    if any(metadata["decoded_byte_length"] > MAX_OBJECT_BYTES for metadata, _ in encoded):
        raise LCHError("OBJECT_LIMIT_EXCEEDED", "generated T0 object exceeds size limit")
    if sum(metadata["decoded_byte_length"] for metadata, _ in encoded) > MAX_TOTAL_BYTES:
        raise LCHError("TOTAL_SIZE_EXCEEDED", "generated T0 decoded objects exceed total limit")
    if len(artifact) > MAX_TOTAL_BYTES:
        raise LCHError("TOTAL_SIZE_EXCEEDED", "generated T0 artifact exceeds total byte limit")
    atomic_write(output, artifact, approved_root=lexical_absolute(output).parent)
    integrity_ref = {
        "kind": "t0_control",
        "sha256": sha256_digest(control),
        "byte_length": len(control),
    }
    return {
        "ok": True,
        "operation": "pack_handoff",
        "transport": "t0",
        "draft": True,
        "output": str(lexical_absolute(output)),
        "package_id": root["package_id"],
        "package_integrity_ref": integrity_ref,
        "canonical_state_digest": root["canonical_state_digest"],
        "review_projection_ref": root["review_projection_ref"],
        "rooted_object_count": len(encoded),
        "issued_results": [],
        "approval_claim": "PROPOSED",
        "capability_processing": {
            "result": "WARN" if root_capability_warnings(root) else "NO_ISSUES",
            "issues": [
                {"code": "LCH-" + code.replace("_", "-"), "subject": subject}
                for code, subject in root_capability_warnings(root)
            ],
        },
    }


class BundleSource:
    """Read a Bundle directory or ZIP without following links or extracting."""

    def __init__(self, path: Path):
        self.path = lexical_absolute(path)
        if self.path.is_symlink():
            raise LCHError("BUNDLE_SYMLINK_INPUT", "Bundle input must not be a symlink")
        reject_symlink_ancestry(self.path.parent, code="BUNDLE_PARENT_SYMLINK")
        self._zip: zipfile.ZipFile | None = None
        self._members: dict[str, zipfile.ZipInfo] = {}
        if self.path.is_dir():
            self.kind = "bundle_directory"
        elif self.path.is_file() and zipfile.is_zipfile(self.path):
            self.kind = "bundle_zip"
            self._zip = zipfile.ZipFile(self.path, "r")
            total = 0
            paths: list[str] = []
            entries = self._zip.infolist()
            if len(entries) > MAX_OBJECTS:
                raise LCHError("ARCHIVE_LIMIT_EXCEEDED", "ZIP exceeds entry count limit")
            entry_paths: list[str] = []
            for info in entries:
                is_directory = info.is_dir()
                lexical_name = (
                    info.filename[:-1]
                    if is_directory and info.filename.endswith("/")
                    else info.filename
                )
                name = safe_relative_path(
                    lexical_name, allow_envelopes=True, allow_root_files=True
                )
                entry_paths.append(name)
                if info.flag_bits & 0x1:
                    raise LCHError("ENCRYPTED_ARCHIVE", "encrypted ZIP members are unsupported")
                mode = (info.external_attr >> 16) & 0o170000
                if is_directory:
                    if mode not in {0, stat.S_IFDIR}:
                        raise LCHError("ARCHIVE_SPECIAL_FILE", "ZIP directory entry has an unsafe type")
                    continue
                if mode not in {0, stat.S_IFREG}:
                    raise LCHError("ARCHIVE_SPECIAL_FILE", "ZIP contains a non-regular file member")
                paths.append(name)
                if info.file_size > MAX_OBJECT_BYTES:
                    raise LCHError("OBJECT_LIMIT_EXCEEDED", "ZIP member exceeds object size limit")
                if info.compress_size == 0 and info.file_size > 0:
                    raise LCHError("ARCHIVE_RATIO_EXCEEDED", "ZIP member has unsafe compression ratio")
                if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                    raise LCHError("ARCHIVE_RATIO_EXCEEDED", "ZIP member has unsafe compression ratio")
                total += info.file_size
                self._members[name] = info
            if len(entry_paths) != len(set(entry_paths)) or len({item.casefold() for item in entry_paths}) != len(entry_paths):
                raise LCHError("PATH_COLLISION", "duplicate or case-colliding ZIP entry path")
            if len(paths) != len(set(paths)) or len({item.casefold() for item in paths}) != len(paths):
                raise LCHError("PATH_COLLISION", "duplicate or case-colliding ZIP member path")
            if len(paths) > MAX_OBJECTS or total > MAX_TOTAL_BYTES:
                raise LCHError("ARCHIVE_LIMIT_EXCEEDED", "ZIP exceeds object or expanded-byte limit")
        else:
            raise LCHError("TRANSPORT_UNKNOWN", "input is neither a Bundle directory nor ZIP")

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()

    def names(self) -> list[str]:
        if self._zip is not None:
            return sorted(self._members)
        names: list[str] = []
        total = 0

        def walk_error(exc: OSError) -> None:
            raise LCHError("BUNDLE_UNREADABLE", "cannot enumerate Bundle directory") from exc

        for directory, directory_names, file_names in os.walk(
            self.path,
            topdown=True,
            followlinks=False,
            onerror=walk_error,
        ):
            base = Path(directory)
            directory_names[:] = sorted(directory_names)
            for name in directory_names:
                candidate = base / name
                try:
                    mode = candidate.lstat().st_mode
                except OSError as exc:
                    raise LCHError("BUNDLE_UNREADABLE", "cannot inspect Bundle directory member") from exc
                if stat.S_ISLNK(mode):
                    raise LCHError("BUNDLE_LINK", "Bundle links are forbidden")
                if not stat.S_ISDIR(mode):
                    raise LCHError("BUNDLE_SPECIAL_FILE", "Bundle contains a non-directory container member")
            for name in sorted(file_names):
                candidate = base / name
                try:
                    metadata = candidate.lstat()
                except OSError as exc:
                    raise LCHError("BUNDLE_UNREADABLE", "cannot inspect Bundle file member") from exc
                if stat.S_ISLNK(metadata.st_mode):
                    raise LCHError("BUNDLE_LINK", "Bundle links are forbidden")
                if not stat.S_ISREG(metadata.st_mode):
                    raise LCHError("BUNDLE_SPECIAL_FILE", "Bundle contains a non-regular file")
                if metadata.st_nlink != 1:
                    raise LCHError("BUNDLE_HARDLINK", "Bundle hard-linked files are forbidden")
                if metadata.st_size > MAX_OBJECT_BYTES:
                    raise LCHError("OBJECT_LIMIT_EXCEEDED", "Bundle member exceeds object size limit")
                total += metadata.st_size
                if total > MAX_TOTAL_BYTES:
                    raise LCHError("BUNDLE_LIMIT_EXCEEDED", "Bundle exceeds total byte limit")
                names.append(
                    safe_relative_path(
                        candidate.relative_to(self.path).as_posix(),
                        allow_envelopes=True,
                        allow_root_files=True,
                    )
                )
                if len(names) > MAX_OBJECTS:
                    raise LCHError("OBJECT_LIMIT_EXCEEDED", "Bundle exceeds object count limit")
        if len(names) != len(set(names)) or len({item.casefold() for item in names}) != len(names):
            raise LCHError("PATH_COLLISION", "duplicate or case-colliding Bundle path")
        return names

    def read(self, name: str, *, max_bytes: int = MAX_OBJECT_BYTES) -> bytes:
        safe_relative_path(name, allow_envelopes=True, allow_root_files=True)
        if self._zip is not None:
            info = self._members.get(name)
            if info is None:
                raise LCHError("OBJECT_MISSING", f"Bundle object is missing: {name}")
            if info.file_size > max_bytes:
                raise LCHError("OBJECT_LIMIT_EXCEEDED", f"Bundle object exceeds limit: {name}")
            try:
                data = self._zip.read(info)
            except (zipfile.BadZipFile, RuntimeError, OSError, EOFError) as exc:
                raise LCHError(
                    "ARCHIVE_MEMBER_READ_FAIL",
                    f"cannot safely read ZIP member: {name}",
                ) from exc
            if len(data) != info.file_size:
                raise LCHError("ARCHIVE_SHORT_READ", f"ZIP member short read: {name}")
            return data
        target = self.path / name
        if target.is_symlink():
            raise LCHError("BUNDLE_LINK", "Bundle links are forbidden")
        current = target.parent
        while current != self.path:
            if current.is_symlink():
                raise LCHError("BUNDLE_LINK", "Bundle parent links are forbidden")
            if current == current.parent:
                raise LCHError("PATH_ESCAPE", "Bundle path escapes root")
            current = current.parent
        return read_bytes(target, max_bytes=max_bytes)


def _read_line(data: bytes, offset: int, *, maximum: int = 1024) -> tuple[bytes, int]:
    end = data.find(b"\n", offset, min(len(data), offset + maximum + 1))
    if end < 0:
        raise LCHError("T0_FRAMING_FAIL", "missing or oversized ASCII frame line")
    return data[offset : end + 1], end + 1


def parse_t0(data: bytes) -> dict[str, Any]:
    offset = 0
    byte_issues: list[dict[str, str]] = []
    line, offset = _read_line(data, offset)
    header = T0_HEADER_RE.fullmatch(line)
    if header is None:
        raise LCHError("T0_HEADER_FAIL", "invalid T0 header")
    line, offset = _read_line(data, offset)
    length_match = T0_LENGTH_RE.fullmatch(line)
    if length_match is None:
        raise LCHError("T0_HEADER_FAIL", "invalid control-byte-length line")
    control_length = int(length_match.group(1))
    if control_length > MAX_JSON_BYTES:
        raise LCHError("T0_CONTROL_LIMIT", "T0 control exceeds size limit")
    line, offset = _read_line(data, offset)
    hash_match = T0_HASH_RE.fullmatch(line)
    if hash_match is None:
        raise LCHError("T0_HEADER_FAIL", "invalid control-sha256 line")
    if offset + control_length > len(data):
        raise LCHError("T0_SHORT_READ", "T0 control is truncated")
    control_bytes = data[offset : offset + control_length]
    offset += control_length
    if offset >= len(data) or data[offset : offset + 1] != b"\n":
        raise LCHError("T0_FRAMING_FAIL", "T0 control delimiter is missing")
    offset += 1
    if sha256_hex(control_bytes) != hash_match.group(1).decode("ascii"):
        byte_issues.append(
            {
                "code": "T0_CONTROL_HASH_FAIL",
                "message": "T0 header control SHA-256 does not match exact control bytes",
                "object_id": "t0_control",
            }
        )
    try:
        control = loads_strict(control_bytes)
    except Exception as exc:
        raise LCHError("T0_CONTROL_JSON_FAIL", "T0 control is not strict JSON") from exc
    check_json_depth(control, maximum=MAX_JSON_DEPTH)
    if canonicalize(control) != control_bytes:
        raise LCHError("T0_CONTROL_JCS_FAIL", "T0 control bytes are not canonical JCS")
    expected_version = ".".join(str(control.get("protocol_version", "")).split(".")[:2])
    if expected_version != header.group(1).decode("ascii"):
        raise LCHError("T0_VERSION_MISMATCH", "T0 header and control versions disagree")
    embedded = control.get("embedded_objects")
    if not isinstance(embedded, list) or len(embedded) > MAX_OBJECTS:
        raise LCHError("T0_OBJECT_MANIFEST_FAIL", "invalid embedded_objects manifest")
    objects: list[dict[str, Any]] = []
    object_ids: set[str] = set()
    decoded_total = 0
    for ordinal, metadata in enumerate(embedded, 1):
        if (
            not isinstance(metadata, dict)
            or type(metadata.get("ordinal")) is not int
            or metadata.get("ordinal") != ordinal
        ):
            raise LCHError("T0_OBJECT_ORDER_FAIL", "embedded object ordinals are not contiguous")
        object_id = metadata.get("object_id")
        if not isinstance(object_id, str) or re.fullmatch(r"[A-Za-z][A-Za-z0-9._:-]*", object_id) is None:
            raise LCHError("T0_OBJECT_ID_FAIL", "T0 embedded object ID is invalid")
        if object_id in object_ids:
            raise LCHError("T0_OBJECT_ID_DUPLICATE", "T0 embedded object IDs must be unique")
        object_ids.add(object_id)
        count = metadata.get("chunk_count")
        if type(count) is not int or count < 0:
            raise LCHError("T0_CHUNK_COUNT_FAIL", "invalid T0 chunk count")
        encoded_length = metadata.get("encoded_byte_length")
        decoded_length = metadata.get("decoded_byte_length")
        if (
            type(encoded_length) is not int
            or encoded_length < 0
            or type(decoded_length) is not int
            or decoded_length < 0
            or decoded_length > MAX_OBJECT_BYTES
            or metadata.get("chunk_size") != CHUNK_SIZE
        ):
            raise LCHError("T0_OBJECT_LENGTH_FAIL", "invalid T0 embedded object lengths")
        expected_encoded_length = (4 * decoded_length + 2) // 3
        expected_chunk_count = (
            math.ceil(encoded_length / CHUNK_SIZE) if encoded_length else 0
        )
        if (
            encoded_length != expected_encoded_length
            or count != expected_chunk_count
        ):
            raise LCHError(
                "T0_OBJECT_LENGTH_FAIL",
                "T0 encoded length and chunk count do not match decoded length",
            )
        decoded_total += decoded_length
        if decoded_total > MAX_TOTAL_BYTES:
            raise LCHError("T0_TOTAL_LIMIT", "T0 decoded objects exceed total byte limit")
        chunks: list[bytes] = []
        for index in range(1, count + 1):
            line, offset = _read_line(data, offset)
            match = T0_CHUNK_RE.fullmatch(line)
            if match is None:
                raise LCHError("T0_CHUNK_HEADER_FAIL", "invalid T0 embedded chunk header")
            values = (
                int(match.group(1)),
                match.group(2).decode("ascii"),
                int(match.group(3)),
                int(match.group(4)),
                int(match.group(5)),
            )
            if values[:4] != (ordinal, object_id, index, count):
                raise LCHError("T0_CHUNK_ORDER_FAIL", "T0 chunk index or object binding mismatch")
            chunk_length = values[4]
            if chunk_length > CHUNK_SIZE or (index < count and chunk_length != CHUNK_SIZE):
                raise LCHError("T0_CHUNK_SIZE_FAIL", "T0 chunk violates fixed chunk size")
            if offset + chunk_length > len(data):
                raise LCHError("T0_SHORT_READ", "T0 embedded chunk is truncated")
            chunk = data[offset : offset + chunk_length]
            offset += chunk_length
            if offset >= len(data) or data[offset : offset + 1] != b"\n":
                raise LCHError("T0_FRAMING_FAIL", "T0 chunk delimiter is missing")
            offset += 1
            if not re.fullmatch(rb"[A-Za-z0-9_-]+", chunk):
                raise LCHError("T0_BASE64URL_FAIL", "T0 chunk is not unpadded base64url")
            chunks.append(chunk)
        encoded = b"".join(chunks)
        if len(encoded) != encoded_length:
            raise LCHError("T0_ENCODED_LENGTH_FAIL", "T0 encoded object length mismatch")
        try:
            padding = b"=" * ((4 - len(encoded) % 4) % 4)
            decoded = base64.b64decode(encoded + padding, altchars=b"-_", validate=True)
        except Exception as exc:
            raise LCHError("T0_BASE64URL_FAIL", "invalid T0 base64url object") from exc
        if len(decoded) != decoded_length:
            byte_issues.append(
                {
                    "code": "T0_DECODED_LENGTH_FAIL",
                    "message": "T0 decoded object length does not match its control commitment",
                    "object_id": object_id,
                }
            )
        if sha256_digest(decoded) != metadata.get("sha256_raw"):
            byte_issues.append(
                {
                    "code": "T0_OBJECT_HASH_FAIL",
                    "message": "T0 embedded object SHA-256 does not match its control commitment",
                    "object_id": object_id,
                }
            )
        objects.append({"metadata": metadata, "bytes": decoded})
    marker, offset = _read_line(data, offset)
    if marker != b"LCH-T0-HUMAN-VIEW\n":
        raise LCHError("T0_REVIEW_MARKER_FAIL", "T0 HUMAN-VIEW marker is missing")
    review_ref = control.get("review_projection_ref")
    review_length = review_ref.get("byte_length") if isinstance(review_ref, dict) else None
    if type(review_length) is not int or review_length < 0 or review_length > MAX_OBJECT_BYTES:
        raise LCHError("T0_REVIEW_REF_FAIL", "T0 review projection ref is invalid")
    if offset + review_length > len(data):
        raise LCHError("T0_SHORT_READ", "T0 HUMAN-VIEW is truncated")
    review = data[offset : offset + review_length]
    offset += review_length
    if not review.endswith(b"\n") or review.endswith(b"\n\n"):
        raise LCHError("T0_REVIEW_LF_FAIL", "T0 HUMAN-VIEW must end with exactly one LF")
    detached: list[dict[str, Any]] = []
    compatibility_issues: list[dict[str, str]] = []
    while offset < len(data):
        line, offset = _read_line(data, offset)
        match = T0_DETACHED_RE.fullmatch(line)
        if match is None:
            raise LCHError("T0_TRAILING_DATA", "unframed trailing data after HUMAN-VIEW")
        opaque_id = match.group(1).decode("ascii")
        expected_type = match.group(2).decode("ascii")
        length = int(match.group(3))
        declared = match.group(4).decode("ascii")
        if not declared.startswith("sha256:"):
            compatibility_issues.append(
                {
                    "code": "T0_DETACHED_HASH_PREFIX_NONCANONICAL",
                    "object_id": opaque_id,
                }
            )
            declared = "sha256:" + declared
        if length < 0 or length > MAX_OBJECT_BYTES or offset + length > len(data):
            raise LCHError("T0_DETACHED_LENGTH_FAIL", "detached envelope length is invalid")
        payload = data[offset : offset + length]
        offset += length
        actual_digest = sha256_digest(payload)
        if offset < len(data):
            if data[offset : offset + 1] != b"\n":
                raise LCHError("T0_FRAMING_FAIL", "detached envelope delimiter is missing")
            offset += 1
            if offset >= len(data):
                raise LCHError("T0_TRAILING_DATA", "terminal detached payload must not have an extra LF")
        detached.append(
            {
                "opaque_id": opaque_id,
                "type": expected_type,
                "sha256_raw": actual_digest,
                "declared_sha256_raw": declared,
                "bytes": payload if actual_digest == declared else None,
            }
        )
        if len(detached) > MAX_OBJECTS or len(detached) + len(objects) > MAX_OBJECTS:
            raise LCHError("T0_DETACHED_LIMIT", "T0 detached candidate count exceeds limit")
    return {
        "transport": "t0",
        "control": control,
        "control_bytes": control_bytes,
        "package_integrity_ref": {
            "kind": "t0_control",
            "sha256": sha256_digest(control_bytes),
            "byte_length": len(control_bytes),
        },
        "objects": objects,
        "review_bytes": review,
        "detached": detached,
        "compatibility_issues": compatibility_issues,
        "byte_issues": byte_issues,
    }


def identify_transport(path: Path) -> str:
    path = lexical_absolute(path)
    if path.is_symlink():
        raise LCHError("TRANSPORT_SYMLINK", "native transport input must not be a symlink")
    reject_symlink_ancestry(path.parent, code="TRANSPORT_PARENT_SYMLINK")
    if path.is_dir():
        return "bundle"
    if path.is_file():
        prefix = read_bytes(path, max_bytes=MAX_TOTAL_BYTES)[:32]
        if T0_HEADER_RE.match(prefix):
            return "t0"
        if zipfile.is_zipfile(path):
            return "bundle"
    raise LCHError("TRANSPORT_UNKNOWN", "input is not a native Bundle or T0 artifact")
