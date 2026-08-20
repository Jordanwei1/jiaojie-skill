"""Conservative first-version legacy detection and conversion reports."""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .canonicalize import canonicalize, canonicalize_text, loads_strict, sha256_digest
from .package import (
    MAX_OBJECT_BYTES,
    MAX_JSON_DEPTH,
    SCHEMA_DIRECTORY,
    bundled_materiality_ref,
)
from .projection import derived_digest_v1
from .schema import SchemaStore, Validator, format_matches
from .security import scan_bytes
from .util import (
    LCHError,
    atomic_commit_no_replace,
    check_json_depth,
    lexical_absolute,
    read_bytes,
    reject_symlink_ancestry,
    secure_output_path,
)


PARSER_VERSION = "legacy-converter-0.1.0"
FORMAT_RULES: dict[str, dict[str, Any]] = {
    "handoff_markdown": {
        "source_version": "handoff-md-v1",
        "marker": "# HANDOFF.md v1",
        "sections": {
            "Current Intent": "current_intent",
            "Decisions": "decisions",
            "Constraints": "constraints",
            "Rejected": "rejected",
            "Next Action": "next_action",
        },
        "detection_rule": "handoff_md_v1_exact_marker",
    },
    "och_snapshot": {
        "source_version": "och-snapshot-v1",
        "headings": [
            ("WHAT WE ARE DOING", "what_we_are_doing"),
            ("CURRENT STATE", "current_state"),
            ("COMPLETED", "completed"),
            ("DECISIONS", "decisions"),
            ("CONSTRAINTS", "constraints"),
            ("NEXT ACTION", "next_action"),
        ],
        "detection_rule": "och_snapshot_v1_exact_six_fields",
    },
    "ltm_packet": {
        "versions": {
            "0.1": {
                "source_version": "ltm-cmp-v0.1",
                "detection_rule": "ltm_cmp_v0_1_exact_version",
            },
            "0.2": {
                "source_version": "ltm-cmp-v0.2",
                "detection_rule": "ltm_cmp_v0_2_exact_version",
            },
        },
    },
}


def _headings(text: str) -> list[tuple[int, str]]:
    result: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), 1):
        match = re.fullmatch(r"## ([^\r\n]+)", line)
        if match:
            result.append((number, match.group(1)))
    return result


def _markdown_mapping(
    data: bytes,
    format_name: str,
    *,
    override: bool,
    evidence_ref: str,
) -> tuple[
    list[dict[str, Any]],
    list[str],
    list[str],
    list[str],
    int,
    str,
    str,
    list[dict[str, Any]],
]:
    rules = FORMAT_RULES[format_name]
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise LCHError("LEGACY_UTF8_REQUIRED", "first-version Markdown converter requires UTF-8") from exc
    if text.startswith("\ufeff") or "\r" in text:
        raise LCHError("LEGACY_TEXT_ENCODING_FAIL", "legacy Markdown must use UTF-8 without BOM and LF")
    lines = text.splitlines()
    if format_name == "och_snapshot":
        heading_level = "###"
        ordered_headings = rules["headings"]
        known = dict(ordered_headings)
        observed = [
            match.group(1)
            for line in lines
            if (match := re.fullmatch(r"### ([^\r\n]+)", line)) is not None
        ]
        if observed != [item[0] for item in ordered_headings]:
            message = "OCH Snapshot v1 must contain the exact six canonical ### fields in order"
            if override:
                message += "; --format-override cannot authorize a noncanonical OCH version"
            raise LCHError("LEGACY_FORMAT_UNKNOWN", message)
        first_field_index = next(
            (index for index, line in enumerate(lines) if line.startswith("### ")),
            len(lines),
        )
        preamble = [line for line in lines[:first_field_index] if line.strip()]
        if len(preamble) > 1 or (preamble and re.fullmatch(r"# [^\r\n]+", preamble[0]) is None):
            raise LCHError(
                "LEGACY_FORMAT_UNKNOWN",
                "OCH Snapshot v1 permits only one optional document title before its six fields",
            )
        confidence = 1
        warnings: list[str] = []
        source_version = rules["source_version"]
        detection_rule = rules["detection_rule"]
    else:
        heading_level = "##"
        known = rules["sections"]
        detected = bool(lines and lines[0] == rules["marker"])
        if not detected and not override:
            raise LCHError("LEGACY_FORMAT_UNKNOWN", "legacy input does not match the frozen exact marker")
        confidence = 1 if detected else 0
        warnings = [] if detected else ["GENERIC_HANDOFF_OVERRIDE_NONAUTHORITATIVE"]
        source_version = rules["source_version"] if detected else "handoff-md-generic"
        detection_rule = rules["detection_rule"] if detected else "handoff_md_generic_user_override"
    mapping: list[dict[str, Any]] = []
    extracted: list[dict[str, Any]] = []
    unmapped: list[str] = []
    found: set[str] = set()
    encoded_lines = data.splitlines(keepends=True)
    offsets: list[int] = []
    offset = 0
    for raw_line in encoded_lines:
        offsets.append(offset)
        offset += len(raw_line)
    heading_rows: list[tuple[int, int, str]] = []
    for index, raw_line in enumerate(encoded_lines):
        decoded_line = raw_line.rstrip(b"\n").decode("utf-8")
        match = re.fullmatch(re.escape(heading_level) + r" ([^\r\n]+)", decoded_line)
        if match:
            heading_rows.append((index, index + 1, match.group(1)))
    for heading_index, (line_index, line, heading) in enumerate(heading_rows):
        target = known.get(heading)
        if target is None:
            unmapped.append(f"line:{line}:{heading}")
            continue
        found.add(target)
        mapping.append(
            {
                "rule_id": f"{format_name}.{target}.v1",
                "source_line": line,
                "source_json_pointer": None,
                "extraction_method": "exact_markdown_heading",
                "evidence_refs": [evidence_ref],
            }
        )
        content_start = offsets[line_index] + len(encoded_lines[line_index])
        content_end = (
            offsets[heading_rows[heading_index + 1][0]]
            if heading_index + 1 < len(heading_rows)
            else len(data)
        )
        segment = data[content_start:content_end]
        leading = len(segment) - len(segment.lstrip(b" \t\n"))
        trailing = len(segment) - len(segment.rstrip(b" \t\n"))
        byte_start = content_start + leading
        byte_end = content_end - trailing
        if byte_end > byte_start:
            field_value = data[byte_start:byte_end].decode("utf-8")
            if format_name == "och_snapshot" and any(
                re.match(r"^#{1,6}(?: |$)", line)
                for line in field_value.splitlines()
            ):
                raise LCHError(
                    "LEGACY_FORMAT_UNKNOWN",
                    f"OCH Snapshot v1 field {heading} contains an extra Markdown heading",
                )
            if format_name == "och_snapshot" and heading in {
                "COMPLETED",
                "DECISIONS",
                "CONSTRAINTS",
            }:
                field_lines = [line for line in field_value.splitlines() if line.strip()]
                if not field_lines or any(not line.startswith("- ") for line in field_lines):
                    raise LCHError(
                        "LEGACY_FORMAT_UNKNOWN",
                        f"OCH Snapshot v1 field {heading} must use a Markdown bullet list",
                    )
                list_values = [line[2:] for line in field_lines]
                if "None." in list_values and list_values != ["None."]:
                    raise LCHError(
                        "LEGACY_FORMAT_UNKNOWN",
                        f"OCH Snapshot v1 field {heading} must use exactly '- None.' for an empty list",
                    )
                extracted_value: Any = [] if list_values == ["None."] else list_values
            else:
                if format_name == "och_snapshot":
                    scalar_lines = field_value.splitlines()
                    seen_content = False
                    seen_separator = False
                    for scalar_line in scalar_lines:
                        if scalar_line.strip():
                            if seen_separator:
                                raise LCHError(
                                    "LEGACY_FORMAT_UNKNOWN",
                                    f"OCH Snapshot v1 field {heading} contains trailing prose after its scalar body",
                                )
                            seen_content = True
                        elif seen_content:
                            seen_separator = True
                extracted_value = field_value
            extracted.append(
                {
                    "field": target,
                    "value": extracted_value,
                    "byte_start": byte_start,
                    "byte_end": byte_end,
                    "exact_source_text": not isinstance(extracted_value, list),
                }
            )
        elif format_name == "och_snapshot":
            raise LCHError(
                "LEGACY_FORMAT_UNKNOWN",
                "OCH Snapshot v1 fields must each contain a nonempty value",
            )
    missing = sorted(set(known.values()) - found)
    missing.append("verified_state_evolution")
    return (
        mapping,
        unmapped,
        missing,
        warnings,
        confidence,
        source_version,
        detection_rule,
        extracted,
    )


def _escape_pointer(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def _ltm_mapping(
    data: bytes,
    *,
    override: bool,
    evidence_ref: str,
) -> tuple[
    list[dict[str, Any]],
    list[str],
    list[str],
    list[str],
    int,
    str,
    str,
    list[dict[str, Any]],
]:
    try:
        value = loads_strict(data)
    except Exception as exc:
        raise LCHError("LEGACY_JSON_FAIL", "LTM packet must be strict JSON") from exc
    if not isinstance(value, dict):
        raise LCHError("LEGACY_JSON_FAIL", "LTM packet root must be an object")
    check_json_depth(value, maximum=MAX_JSON_DEPTH)
    if len(data) > 32 * 1024:
        raise LCHError("LEGACY_LTM_SIZE_FAIL", "LTM CMP exceeds the upstream 32 KiB limit")
    rules = FORMAT_RULES["ltm_packet"]
    version = value.get("ltm_version")
    version_rule = rules["versions"].get(version) if isinstance(version, str) else None
    if version_rule is None:
        message = "LTM input does not declare supported Core Memory Packet version 0.1 or 0.2"
        if override:
            message += "; --format-override cannot authorize an unsupported version"
        raise LCHError("LEGACY_FORMAT_UNKNOWN", message)

    def fail(path: str, message: str) -> None:
        raise LCHError("LEGACY_LTM_SCHEMA_FAIL", f"{path}: {message}")

    def text_field(candidate: Any, path: str, *, minimum: int = 0, maximum: int = 1024) -> None:
        if not isinstance(candidate, str) or len(candidate) < minimum or len(candidate) > maximum:
            fail(path, f"must be a string of length {minimum}..{maximum}")

    def string_array(candidate: Any, path: str, *, maximum_items: int, maximum_length: int = 1024) -> None:
        if not isinstance(candidate, list) or len(candidate) > maximum_items:
            fail(path, f"must be an array with at most {maximum_items} items")
        for index, item in enumerate(candidate):
            text_field(item, f"{path}/{index}", maximum=maximum_length)

    common_keys = {
        "ltm_version", "id", "created_at", "project", "goal", "constraints",
        "decisions", "attempts", "open_questions", "next_step", "tags", "provenance",
    }
    v02_keys = {"parent_id", "success_criteria", "methods"}
    allowed = common_keys | (v02_keys if version == "0.2" else set())
    unknown = sorted(set(value) - allowed)
    if unknown:
        fail("/", "contains unsupported fields: " + ", ".join(unknown))
    for required in ("ltm_version", "id", "created_at", "goal", "next_step"):
        if required not in value:
            fail("/", "missing required field " + required)
    text_field(value["id"], "/id", minimum=10, maximum=64)
    text_field(value["created_at"], "/created_at", minimum=1, maximum=64)
    if not format_matches(value["created_at"], "date-time") or not value["created_at"].lower().endswith("z"):
        fail("/created_at", "must be an RFC 3339 UTC timestamp")
    text_field(value["goal"], "/goal", minimum=1)
    text_field(value["next_step"], "/next_step", minimum=1)
    if "parent_id" in value:
        text_field(value["parent_id"], "/parent_id", minimum=10, maximum=64)
    project = value.get("project")
    if project is not None:
        if not isinstance(project, dict) or set(project) - {"name", "ref"}:
            fail("/project", "must be a closed name/ref object")
        if "name" in project:
            text_field(project["name"], "/project/name", maximum=128)
        if "ref" in project:
            text_field(project["ref"], "/project/ref", maximum=256)
    for key, maximum_items in (("constraints", 32), ("open_questions", 32), ("success_criteria", 16)):
        if key in value:
            string_array(value[key], "/" + key, maximum_items=maximum_items)
    decisions = value.get("decisions", [])
    if not isinstance(decisions, list) or len(decisions) > 64:
        fail("/decisions", "must be an array with at most 64 items")
    decision_keys = {"what", "why", "locked"} | ({"consequences"} if version == "0.2" else set())
    for index, decision in enumerate(decisions):
        if not isinstance(decision, dict) or set(decision) - decision_keys or not {"what", "why"}.issubset(decision):
            fail(f"/decisions/{index}", "must match the frozen decision object")
        text_field(decision["what"], f"/decisions/{index}/what")
        text_field(decision["why"], f"/decisions/{index}/why")
        if "consequences" in decision:
            text_field(decision["consequences"], f"/decisions/{index}/consequences")
        if "locked" in decision and type(decision["locked"]) is not bool:
            fail(f"/decisions/{index}/locked", "must be boolean")
    attempts = value.get("attempts", [])
    if not isinstance(attempts, list) or len(attempts) > 64:
        fail("/attempts", "must be an array with at most 64 items")
    attempt_keys = {"tried", "outcome", "learned"} | ({"confidence"} if version == "0.2" else set())
    for index, attempt in enumerate(attempts):
        if not isinstance(attempt, dict) or set(attempt) - attempt_keys or not {"tried", "outcome"}.issubset(attempt):
            fail(f"/attempts/{index}", "must match the frozen attempt object")
        text_field(attempt["tried"], f"/attempts/{index}/tried")
        if attempt["outcome"] not in {"succeeded", "failed", "partial"}:
            fail(f"/attempts/{index}/outcome", "must be succeeded, failed, or partial")
        if "learned" in attempt:
            text_field(attempt["learned"], f"/attempts/{index}/learned")
        if "confidence" in attempt and attempt["confidence"] not in {"low", "medium", "high"}:
            fail(f"/attempts/{index}/confidence", "must be low, medium, or high")
    methods = value.get("methods", [])
    if not isinstance(methods, list) or len(methods) > 32:
        fail("/methods", "must be an array with at most 32 items")
    for index, method in enumerate(methods):
        if not isinstance(method, dict) or set(method) != {"name", "when_applicable", "how"}:
            fail(f"/methods/{index}", "must match the frozen method object")
        text_field(method["name"], f"/methods/{index}/name", minimum=1, maximum=128)
        if re.fullmatch(r"[a-z0-9][a-z0-9-]{0,127}", method["name"]) is None:
            fail(f"/methods/{index}/name", "must be a lowercase stable method name")
        text_field(method["when_applicable"], f"/methods/{index}/when_applicable")
        text_field(method["how"], f"/methods/{index}/how", maximum=2048)
    tags = value.get("tags")
    if tags is not None:
        string_array(tags, "/tags", maximum_items=16, maximum_length=32)
        if any(re.fullmatch(r"[a-z0-9][a-z0-9-]{0,31}", item) is None for item in tags):
            fail("/tags", "items must be lowercase stable tags")
    provenance = value.get("provenance")
    if provenance is not None:
        allowed_provenance = {"author_model", "author_human", "source_hash", "confidence"}
        if not isinstance(provenance, dict) or set(provenance) - allowed_provenance:
            fail("/provenance", "must match the frozen provenance object")
        for key in ("author_model", "author_human"):
            if key in provenance:
                text_field(provenance[key], "/provenance/" + key, maximum=128)
        if "source_hash" in provenance and (
            not isinstance(provenance["source_hash"], str)
            or re.fullmatch(r"sha256:[a-f0-9]{64}", provenance["source_hash"]) is None
        ):
            fail("/provenance/source_hash", "must be a lowercase SHA-256 digest")
        if "confidence" in provenance and (
            not isinstance(provenance["confidence"], str)
            or provenance["confidence"] not in {"low", "medium", "high"}
        ):
            fail("/provenance/confidence", "must be low, medium, or high")

    mapping: list[dict[str, Any]] = []
    extracted: list[dict[str, Any]] = []
    found: set[str] = set()
    key_targets = {
        "goal": "goal",
        "constraints": "constraints",
        "decisions": "decisions",
        "attempts": "attempts",
        "open_questions": "open_questions",
        "next_step": "next_step",
        "success_criteria": "success_criteria",
        "methods": "methods",
    }
    for key, target in key_targets.items():
        if key in value:
            found.add(target)
            mapping.append(
                {
                    "rule_id": f"ltm_packet.{target}.v1",
                    "source_line": None,
                    "source_json_pointer": "/" + _escape_pointer(key),
                    "extraction_method": "exact_json_pointer",
                    "evidence_refs": [evidence_ref],
                }
            )
            extracted.append(
                {
                    "field": target,
                    "value": value[key],
                    "byte_start": 0,
                    "byte_end": len(data),
                    "exact_source_text": False,
                }
            )
    preserved_metadata = {"ltm_version", "id", "created_at", "parent_id", "project", "tags", "provenance"}
    unmapped = ["/" + _escape_pointer(key) for key in sorted(set(value) & preserved_metadata)]
    expected_targets = {"goal", "constraints", "decisions", "attempts", "open_questions", "next_step"}
    if version == "0.2":
        expected_targets.update({"success_criteria", "methods"})
    missing = sorted(expected_targets - found)
    missing.append("verified_state_evolution")
    warnings: list[str] = []
    if isinstance(provenance, dict) and "source_hash" in provenance:
        warnings.append("SOURCE_HASH_PRESERVED_AS_SOURCE_DECLARED_ONLY")
    return (
        mapping,
        unmapped,
        missing,
        warnings,
        1,
        version_rule["source_version"],
        version_rule["detection_rule"],
        extracted,
    )


def _atomic_directory(output: Path, files: dict[str, bytes]) -> list[str]:
    output = secure_output_path(output)
    stage = Path(tempfile.mkdtemp(prefix=".lch-convert-", dir=str(output.parent)))
    try:
        os.chmod(stage, 0o700)
        for name, data in sorted(files.items()):
            target = stage / name
            target.parent.mkdir(parents=True, exist_ok=True)
            os.chmod(target.parent, 0o700)
            target.write_bytes(data)
            os.chmod(target, 0o600)
        atomic_commit_no_replace(stage, output)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return sorted(files)


def _localized(
    text_id: str,
    value: str,
    *,
    lang: str = "en",
    fidelity: str = "derived_restatement",
) -> dict[str, Any]:
    return {
        "text_id": text_id,
        "value": value,
        "lang": lang,
        "dir": "ltr",
        "kind": "canonical_assertion",
        "authority": "canonical_assertion",
        "fidelity": fidelity,
        "translation_of": None,
        "translation_method": None,
        "review_status": "not_applicable",
    }


def _native_staging(
    *,
    report: dict[str, Any],
    report_bytes: bytes,
    source: bytes,
    source_suffix: str,
    output: Path,
    created_at: str,
    tenant_id: str,
    include_original: bool,
    extracted: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, bytes]]:
    if not format_matches(created_at, "date-time"):
        raise LCHError("CREATED_AT_INVALID", "--created-at must be an RFC 3339 timestamp")
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9._:-]*", tenant_id) is None:
        raise LCHError("TENANT_ID_INVALID", "--tenant-id must be a stable ASCII ID")
    source_hex = report["source_sha256"].split(":", 1)[1]
    package_id = "legacy." + source_hex[:24]
    scope_id = "scope." + source_hex[:24]
    approval_slot = "slot.approval_statement." + source_hex[:16]
    review_slot = "slot.review_projection." + source_hex[:16]
    approval_verify_slot = "slot.approval_verification." + source_hex[:16]
    graph_record_id = "graph." + source_hex[:16]
    graph_event_id = "event.graph." + source_hex[:16]
    inventory_id = "inventory." + source_hex[:16]
    evidence_object_id = "legacy_source" if include_original else "legacy_conversion_report"
    evidence_bytes = source if include_original else report_bytes
    evidence_sha = sha256_digest(evidence_bytes)
    evidence_source_id = "legacy_source_entry"

    scope = {
        "scope_id": scope_id,
        "statement": _localized(
            "text.scope." + source_hex[:12],
            "Conservative legacy conversion scope; the original task request is not yet established.",
        ),
        "user_request_refs": [evidence_source_id],
        "selection_basis": "PRODUCER_PROPOSED",
        "material_exclusion_ids": [] if include_original else ["omission.original_transfer"],
        "approval_statement_slot": approval_slot,
    }
    state_omission = {
        "omission_id": "omission.legacy_state_evolution",
        "category": "evidence",
        "description": _localized(
            "text.omission." + source_hex[:12],
            "Legacy state evolution remains unconfirmed.",
        ),
        "reason": _localized(
            "text.omission_reason." + source_hex[:12],
            "Deterministic conversion cannot establish historical transitions or source authority.",
        ),
        "materiality": "MATERIAL",
        "recoverable": True,
    }
    omissions = [state_omission]
    if not include_original:
        omissions.append(
            {
                "omission_id": "omission.original_transfer",
                "category": "policy_exclusion",
                "description": _localized(
                    "text.original_transfer." + source_hex[:12],
                    "Original legacy bytes are excluded from the release object map.",
                ),
                "reason": _localized(
                    "text.original_transfer_reason." + source_hex[:12],
                    "No current transfer approval was declared for the original bytes.",
                ),
                "materiality": "MATERIAL",
                "recoverable": True,
            }
        )
    coverage = {
        "claim": "PARTIAL",
        "claim_issuer": "producer",
        "scope": scope,
        "source_access": "PARTIAL",
        "inventory_object_id": inventory_id,
        "raw_coverage": "PARTIAL",
        "artifact_coverage": "NOT_APPLICABLE",
        "coverage_envelope_slot_ids": [],
        "omissions": omissions,
    }
    inventory_entry = {
        "ordinal": 1,
        "source_id": evidence_source_id,
        "stream_id": "stream.legacy." + source_hex[:12],
        "source_principal_id": "legacy_converter",
        "source_role": "converter",
        "observed_at": created_at,
        "object_id": evidence_object_id,
        "object_sha256": evidence_sha,
        "attachment_object_ids": [],
        "tool_result_object_ids": [],
    }
    source_inventory = {
        "inventory_id": inventory_id,
        "collector_claim": {"principal_id": "legacy_converter", "method": "observed"},
        "tenant_id": tenant_id,
        "source_session_ids": ["session.legacy." + source_hex[:12]],
        "capture_boundary": {
            "started_at": created_at,
            "ended_at": created_at,
            "first_native_id": evidence_source_id,
            "last_native_id": evidence_source_id,
        },
        "entries": [inventory_entry],
        "gaps": omissions,
        "inventory_digest": "",
        "platform_attestation_ref": None,
    }
    inventory_projection = dict(source_inventory)
    del inventory_projection["inventory_digest"]
    source_inventory["inventory_digest"] = derived_digest_v1(
        "inventory_digest",
        inventory_projection,
    )
    field_axes: dict[str, tuple[str, dict[str, str]]] = {
        "current_intent": ("intent", {"lifecycle": "PROPOSED"}),
        "what_we_are_doing": ("intent", {"lifecycle": "PROPOSED"}),
        "goal": ("intent", {"lifecycle": "PROPOSED"}),
        "context": ("intent", {"lifecycle": "PROPOSED"}),
        "current_state": (
            "claim",
            {
                "epistemic_basis": "EXTERNAL_ASSERTED",
                "verification": "UNVERIFIED",
                "temporal_validity": "UNKNOWN",
            },
        ),
        "completed": (
            "claim",
            {
                "epistemic_basis": "EXTERNAL_ASSERTED",
                "verification": "UNVERIFIED",
                "temporal_validity": "UNKNOWN",
            },
        ),
        "decisions": ("decision", {"lifecycle": "CANDIDATE"}),
        "constraints": (
            "constraint",
            {"lifecycle": "PROPOSED", "compliance": "UNKNOWN"},
        ),
        "rejected": ("decision", {"lifecycle": "REJECTED"}),
        "attempts": ("attempt", {"outcome": "INCONCLUSIVE"}),
        "open_questions": ("question", {"lifecycle": "OPEN"}),
        "methods": (
            "claim",
            {
                "epistemic_basis": "EXTERNAL_ASSERTED",
                "verification": "UNVERIFIED",
                "temporal_validity": "UNKNOWN",
            },
        ),
        "next_action": ("next_action", {"eligibility": "BLOCKED"}),
        "next_step": ("next_action", {"eligibility": "BLOCKED"}),
    }
    records: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    record_number = 0
    current_intent_id: str | None = None
    action_completion_criteria = next(
        (
            item.get("value")
            for item in extracted
            if item.get("field") == "success_criteria"
            and isinstance(item.get("value"), list)
        ),
        [],
    )

    def append_record(
        *,
        field: str,
        value: str,
        axes: dict[str, str],
        record_type: str,
        byte_start: int,
        byte_end: int,
        exact_source_text: bool,
    ) -> None:
        nonlocal record_number, current_intent_id
        record_number += 1
        record_id = f"{record_type}.{field}.{record_number}.{source_hex[:12]}"
        event_id = "event." + record_id
        span_bytes = evidence_bytes[byte_start:byte_end]
        record = {
            "id": record_id,
            "type": record_type,
            "assertion": _localized(
                "text." + record_id,
                value,
                lang="und" if exact_source_text else "en",
                fidelity=(
                    "unicode_scalar_exact"
                    if exact_source_text
                    else "derived_restatement"
                ),
            ),
            "evidence_spans": [
                {
                    "object_id": evidence_object_id,
                    "source_id": evidence_source_id,
                    "byte_start": byte_start,
                    "byte_end": byte_end,
                    "sha256_raw": sha256_digest(span_bytes),
                }
            ],
            "source_principal": {
                "principal_id": (
                    "legacy_external_author"
                    if exact_source_text
                    else "legacy_converter"
                ),
                "tenant_id": tenant_id,
                "source_role": "external_author" if exact_source_text else "converter",
                "authority_at_capture": (
                    "external_assertion" if exact_source_text else "no_authority"
                ),
            },
            "ordering": {
                "stream_id": "stream.legacy." + source_hex[:12],
                "sequence": record_number - 1,
                "causal_parent_ids": [],
                "logical_clock": record_number - 1,
            },
            "temporal": {
                "observed_at": created_at,
                "valid_from": None,
                "expires_at": None,
                "revalidate_before": None,
            },
            "related_records": [],
            "transition_event_ids": [event_id],
            "scope_id": scope_id,
            "sensitivity": "private",
            **axes,
        }
        records.append(record)
        events.append(
            {
                "event_id": event_id,
                "event_stream_id": "events." + record_id,
                "event_sequence": 1,
                "record_id": record_id,
                "previous_event_ids": [],
                "from": None,
                "to": dict(axes),
                "reason_kind": "INITIALIZED",
                "principal_id": "legacy_converter",
                "source_refs": [evidence_source_id],
                "scope_id": scope_id,
                "occurred_at": created_at,
                "logical_clock": record_number,
            }
        )
        if record_type == "intent" and current_intent_id is None:
            current_intent_id = record_id
        if record_type == "next_action":
            actions.append(
                {
                    "action_id": "action." + record_id,
                    "next_action_record_id": record_id,
                    "eligibility_projection": "BLOCKED",
                    "event_head_ids": [event_id],
                    "completion_criteria": list(action_completion_criteria),
                    "required_capabilities": [],
                    "required_authorization_specs": [],
                    "external_state_checks": [],
                }
            )

    for item in extracted:
        field = item.get("field")
        mapping = field_axes.get(field) if isinstance(field, str) else None
        if mapping is None:
            continue
        record_type, axes = mapping
        raw_value = item.get("value")
        values = (
            raw_value
            if isinstance(raw_value, list) and record_type != "intent"
            else [raw_value]
        )
        for raw_member in values:
            member_axes = dict(axes)
            if field == "attempts" and isinstance(raw_member, dict):
                member_axes["outcome"] = {
                    "succeeded": "SUCCEEDED",
                    "failed": "FAILED",
                    "partial": "INCONCLUSIVE",
                }.get(raw_member.get("outcome"), "INCONCLUSIVE")
            if isinstance(raw_member, str):
                text_value = raw_member
                exact = item.get("exact_source_text") is True
            else:
                text_value = canonicalize_text(raw_member)
                exact = False
            if not text_value.strip():
                continue
            append_record(
                field=field,
                value=text_value,
                axes=member_axes,
                record_type=record_type,
                byte_start=int(item["byte_start"]),
                byte_end=int(item["byte_end"]),
                exact_source_text=exact,
            )

    if current_intent_id is None:
        append_record(
            field="unknown",
            value="The current task intent is unconfirmed after conservative legacy conversion.",
            axes={"lifecycle": "PROPOSED"},
            record_type="intent",
            byte_start=0,
            byte_end=len(evidence_bytes),
            exact_source_text=False,
        )

    graph_body = {
        "actions": sorted(actions, key=lambda item: item["action_id"]),
        "action_edges": [],
        "action_groups": [],
        "recommended_action_id": None,
        "recommendation_basis_ids": [],
    }
    graph_revision = {
        "record_id": graph_record_id,
        "revision_id": "revision.graph." + source_hex[:12],
        "previous_revision_ids": [],
        "activated_by_event_id": graph_event_id,
        "revision_digest": "",
    }
    action_graph = {"action_graph_revision": graph_revision, **graph_body}
    graph_projection = {
        "action_graph_revision": {
            key: value for key, value in graph_revision.items()
            if key != "revision_digest"
        },
        **graph_body,
    }
    graph_revision["revision_digest"] = derived_digest_v1(
        "revision_digest",
        graph_projection,
    )
    events.append(
        {
            "event_id": graph_event_id,
            "event_stream_id": "events." + graph_record_id,
            "event_sequence": 1,
            "record_id": graph_record_id,
            "previous_event_ids": [],
            "from": None,
            "to": {"lifecycle": "ACTIVE"},
            "reason_kind": "ACTION_GRAPH_ACTIVATED",
            "principal_id": "legacy_converter",
            "source_refs": [evidence_source_id],
            "scope_id": scope_id,
            "occurred_at": created_at,
            "logical_clock": len(events) + 1,
        }
    )
    boundaries = {
        "source_boundary": {
            "conversion_origin": report["conversion_origin"],
            "source_sha256": report["source_sha256"],
        },
        "scope": scope,
        "policy_boundary": {
            "original_transfer": "DECLARED_ALLOWED" if include_original else "NOT_APPROVED"
        },
        "external_state_dependencies": [],
    }
    language_profile = {
        "source_languages": [{"tag": "und", "provenance": "legacy_format_unknown"}],
        "content_languages": ["und"],
        "continuation_language_ranges": ["und"],
        "selected_continuation_language": "und",
        "translation_policy": "original_authoritative",
        "generated_text_normalization": "NFC",
    }
    materiality = bundled_materiality_ref()
    warm = {
        "protocol_version": "0.1.0",
        "state_projection_version": "state-projection-v1",
        "boundaries": boundaries,
        "source_inventory": source_inventory,
        "records": records,
        "transition_events": events,
        "action_graph": action_graph,
        "current_projection": {
            "current_intent_id": current_intent_id,
            "current_phase": "legacy_conversion_review",
            "active_decision_ids": [],
            "rejected_decision_ids": sorted(
                item["id"]
                for item in records
                if item.get("type") == "decision"
                and item.get("lifecycle") == "REJECTED"
            ),
            "failed_attempt_ids": [],
            "active_constraint_ids": [],
            "answered_question_ids": [],
            "ready_action_ids": [],
            "blocked_action_ids": sorted(
                item["action_id"] for item in actions
            ),
            "recommended_action_id": None,
        },
        "content_coverage": coverage,
        "consistency_claim": "UNKNOWN",
        "semantic_actionability_claim": "BLOCKED",
        "language_profile": language_profile,
        "materiality_profile_ref": materiality,
    }
    slots = [
        {
            "opaque_id": review_slot,
            "expected_type": "review_projection_conformance",
            "purpose": _localized("text.slot.review." + source_hex[:12], "Carry the detached review projection result."),
            "required": True,
        },
        {
            "opaque_id": approval_slot,
            "expected_type": "approval_statement",
            "purpose": _localized("text.slot.statement." + source_hex[:12], "Carry an approval statement for the sealed draft."),
            "required": True,
        },
        {
            "opaque_id": approval_verify_slot,
            "expected_type": "approval_verification",
            "purpose": _localized("text.slot.verification." + source_hex[:12], "Carry approval verification for the sealed draft."),
            "required": True,
        },
    ]
    root = {
        "protocol_id": "lossless-context-handoff",
        "protocol_version": "0.1.0",
        "package_id": package_id,
        "created_at": created_at,
        "producer": {
            "runtime": "legacy_converter_python",
            "model": "deterministic_parser",
            "skill_version": "0.1.0",
        },
        "profiles": [
            {"id": "urn:lch:profile:core-markdown", "version": "0.1.0", "required": True}
        ],
        "must_understand": [],
        "source_boundary": boundaries["source_boundary"],
        "scope": scope,
        "policy_boundary": boundaries["policy_boundary"],
        "external_state_dependencies": [],
        "resource_requirements": {},
        "language_profile": language_profile,
        "materiality_profile_ref": materiality,
        "structure_self_check": "NOT_RUN",
        "byte_digests_present": "NO",
        "content_coverage": coverage,
        "consistency_claim": "UNKNOWN",
        "semantic_actionability_claim": "BLOCKED",
        "continuity_eval_eligibility_claim": "INELIGIBLE",
        "approval_claim": {"state": "PROPOSED", "approval_statement_slot": approval_slot},
        "origin_claim": {
            "claimed_principal": "legacy_converter",
            "claimed_method": "deterministic_legacy_conversion",
            "tenant_id": tenant_id,
            "recipient_binding": None,
        },
        "detached_envelope_slots": slots,
    }
    final_output = lexical_absolute(output)
    object_map: list[dict[str, Any]] = [
        {
            "object_id": "legacy_conversion_report",
            "source_path": str(final_output / "conversion-report.json"),
            "bundle_path": "cold/conversion-report.json",
            "role": "evidence",
            "media_type": "application/json",
            "charset": "utf-8",
            "authority": "normative",
            "source_refs": [evidence_source_id],
            "derived_from": ["legacy_source"] if include_original else [],
        }
    ]
    if include_original:
        source_media = "application/json" if source_suffix == ".json" else (
            "text/markdown" if source_suffix in {".md", ".markdown"} else "application/octet-stream"
        )
        object_map.insert(
            0,
            {
                "object_id": "legacy_source",
                "source_path": str(final_output / ("restricted-source/original" + source_suffix)),
                "bundle_path": "cold/legacy-source" + source_suffix,
                "role": "imported_source",
                "media_type": source_media,
                "charset": "utf-8" if source_media.startswith("text/") or source_media == "application/json" else None,
                "authority": "source_evidence",
                "source_refs": [evidence_source_id],
                "derived_from": [],
            },
        )
    files = {
        "root.json": canonicalize(root),
        "warm.json": canonicalize(warm),
        "object-map.json": canonicalize({"objects": object_map}),
        "conversion-report.json": report_bytes,
        "restricted-source/original" + source_suffix: source,
    }
    return root, warm, object_map, files


def _security_stop(
    *,
    output: Path,
    source: bytes,
    source_suffix: str,
    findings: list[dict[str, str]],
    disposition: str,
) -> dict[str, Any]:
    public_findings = [
        {"code": item["code"], "category": item["category"], "severity": item["severity"]}
        for item in findings
    ]
    audit = {
        "disposition": disposition,
        "findings": public_findings,
        "conversion_started": False,
    }
    files: dict[str, bytes] = {}
    if disposition == "QUARANTINE":
        restricted_audit = dict(audit)
        restricted_audit["source_sha256"] = sha256_digest(source)
        files["quarantine/original" + source_suffix] = source
        files["scan-result.json"] = canonicalize(restricted_audit)
    elif disposition == "REDACTED_EXPORT":
        files["redaction-record.json"] = canonicalize(audit)
    elif disposition != "REFUSE":
        raise LCHError("DISPOSITION_INVALID", "security disposition is invalid")
    written = _atomic_directory(output, files) if files else []
    return {
        "ok": False,
        "operation": "convert_legacy",
        "disposition": disposition,
        "output": str(lexical_absolute(output)) if written else None,
        "files": written,
        "findings": public_findings,
        "claims_issued": [],
    }


def convert_legacy(
    input_path: Path,
    output: Path,
    *,
    format_name: str,
    format_override: bool,
    on_security_hit: str,
    created_at: str,
    tenant_id: str,
    approve_original_transfer: bool,
) -> dict[str, Any]:
    if format_name not in FORMAT_RULES:
        raise LCHError("LEGACY_FORMAT_UNSUPPORTED", "unsupported legacy converter format")
    source_path = reject_symlink_ancestry(input_path, code="LEGACY_INPUT_SYMLINK")
    source = read_bytes(source_path, max_bytes=MAX_OBJECT_BYTES)
    findings = scan_bytes(
        source,
        object_id="legacy_source",
        suffix=source_path.suffix,
        logical_name=source_path.name,
    )
    if findings:
        return _security_stop(
            output=output,
            source=source,
            source_suffix=source_path.suffix or ".bin",
            findings=findings,
            disposition=on_security_hit,
        )
    rules = FORMAT_RULES[format_name]
    generic_handoff = (
        format_name == "handoff_markdown"
        and format_override
        and not source.startswith((FORMAT_RULES["handoff_markdown"]["marker"] + "\n").encode("utf-8"))
    )
    if generic_handoff and not approve_original_transfer:
        raise LCHError(
            "GENERIC_SOURCE_TRANSFER_APPROVAL_REQUIRED",
            "generic HANDOFF conversion requires explicit approval to preserve and transfer the exact source bytes",
        )
    include_original = approve_original_transfer
    mapping_evidence_ref = (
        "legacy_source_entry"
        if include_original
        else "omission.original_transfer"
    )
    if format_name == "ltm_packet":
        (
            mapping,
            unmapped,
            missing,
            warnings,
            confidence,
            source_version,
            detection_rule,
            extracted,
        ) = _ltm_mapping(
            source,
            override=format_override,
            evidence_ref=mapping_evidence_ref,
        )
    else:
        (
            mapping,
            unmapped,
            missing,
            warnings,
            confidence,
            source_version,
            detection_rule,
            extracted,
        ) = _markdown_mapping(
            source,
            format_name,
            override=format_override,
            evidence_ref=mapping_evidence_ref,
        )
    report = {
        "conversion_origin": format_name,
        "source_version": source_version,
        "source_sha256": sha256_digest(source),
        "detection_rules": [detection_rule],
        "detection_confidence": confidence,
        "parser_version": PARSER_VERSION,
        "format_override": format_name if format_override else None,
        "mapping_report": mapping,
        "unmapped_sections": unmapped,
        "conflicts": [],
        "warnings": warnings + (
            [] if include_original else ["ORIGINAL_REQUIRES_TRANSFER_APPROVAL"]
        ),
        "CONVERSION_REPORT": "COMPLETED",
        "STRUCTURE_RESULT_REF": None,
        "SOURCE_ORIGIN_CLAIM": "UNKNOWN",
        "CONTINUITY_EVAL_ELIGIBILITY_CLAIM": "INELIGIBLE",
        "CONTENT_COVERAGE_CLAIM": "PARTIAL",
        "COVERAGE_CLAIM_BASIS": "CONVERTER_DERIVED",
        "COVERAGE_RESULT_REFS": [],
        "APPROVAL_CLAIM": "PROPOSED",
        "MISSING": sorted(set(missing)),
    }
    problems = Validator(SchemaStore(SCHEMA_DIRECTORY)).validate(
        report, "legacy-conversion-report.schema.json"
    )
    if problems:
        raise LCHError(
            "CONVERSION_REPORT_SCHEMA_FAIL",
            "generated conversion report fails bundled Schema",
            details=[item.as_dict() for item in problems],
        )
    suffix = source_path.suffix or ".bin"
    report_bytes = canonicalize(report)
    root, warm, object_map, files = _native_staging(
        report=report,
        report_bytes=report_bytes,
        source=source,
        source_suffix=suffix,
        output=output,
        created_at=created_at,
        tenant_id=tenant_id,
        include_original=include_original,
        extracted=extracted if include_original else [],
    )
    warm_problems = Validator(SchemaStore(SCHEMA_DIRECTORY)).validate(
        warm, "state.schema.json"
    )
    if warm_problems:
        raise LCHError(
            "CONVERSION_WARM_SCHEMA_FAIL",
            "generated conservative WARM staging fails bundled Schema",
            details=[item.as_dict() for item in warm_problems],
        )
    written = _atomic_directory(output, files)
    return {
        "ok": True,
        "operation": "convert_legacy",
        "format": format_name,
        "output": str(lexical_absolute(output)),
        "files": written,
        "native_staging": True,
        "ready_for_pack": True,
        "pack_inputs": {
            "root": "root.json",
            "warm": "warm.json",
            "object_map": "object-map.json",
        },
        "source_sha256": report["source_sha256"],
        "claims": {
            "CONTENT_COVERAGE_CLAIM": "PARTIAL",
            "CONTINUITY_EVAL_ELIGIBILITY_CLAIM": "INELIGIBLE",
            "APPROVAL_CLAIM": "PROPOSED",
        },
        "issued_results": [],
        "security_disposition": "NO_HIT_DETECTED",
        "original_transfer": (
            "DECLARED_ALLOWED"
            if approve_original_transfer
            else "NOT_APPROVED_EXCLUDED_FROM_OBJECT_MAP"
        ),
    }
