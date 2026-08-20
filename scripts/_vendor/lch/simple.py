"""Human-first handoff formats and their bounded deterministic helpers.

The ordinary product path intentionally stays separate from the LCH 0.1 audit
wire protocol.  Markdown is the authority for ordinary handoffs.  A small ZIP
only carries required files, while an audit ZIP adds a machine projection and a
byte manifest.  None of these formats transfers current action authority.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import stat
import tempfile
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping, Sequence

from .canonicalize import loads_strict
from .security import scan_bytes
from .util import (
    LCHError,
    atomic_commit_no_replace,
    atomic_write,
    json_bytes,
    lexical_absolute,
    read_bytes,
    secure_output_path,
)


SIMPLE_VERSION = "1.0"
MARKDOWN_FORMAT = "handoff.md"
ATTACHMENT_FORMAT = "handoff.zip"
AUDIT_FORMAT = "handoff-audit.zip"
MAX_MARKDOWN_BYTES = 2 * 1024 * 1024
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 256 * 1024 * 1024
MAX_MEMBERS = 512
MAX_COMPRESSION_RATIO = 100

FRONT_MATTER_KEYS = ("handoff", "version", "language", "coverage")
FRONT_MATTER_VALUES = {
    "handoff": "task-context",
    "version": SIMPLE_VERSION,
}
COVERAGE_VALUES = frozenset({"FULL", "PARTIAL", "UNKNOWN"})
LANGUAGE_RE = re.compile(r"^(?:[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*|und|zxx)$")

SECTION_SPECS: tuple[tuple[str, str], ...] = (
    ("current_goal", "当前目标 / Current goal"),
    ("stopped_at", "停止位置 / Stopped at"),
    ("recommended_next_action", "建议下一步 / Recommended next action"),
    ("completion_criteria", "完成标准 / Completion criteria"),
    ("active_decisions", "有效决定 / Active decisions"),
    ("constraints_and_authority", "约束与权限 / Constraints and authority"),
    ("do_not_revive", "不要复活 / Do not revive"),
    ("failed_attempts", "失败尝试 / Failed attempts"),
    ("answered_questions", "已回答问题 / Answered questions"),
    ("workspace_and_files", "工作区与关键文件 / Workspace and important files"),
    ("included_attachments", "随包附件 / Included attachments"),
    ("open_questions", "未决问题 / Open questions"),
    ("known_omissions", "已知缺失 / Known omissions"),
    ("revalidate", "需要重新验证 / Revalidate"),
)
SECTION_BY_HEADING = {heading: key for key, heading in SECTION_SPECS}
REQUIRED_GROUP_HEADINGS = (
    "## 继续位置 / Resume",
    "## 不可丢失 / Keep",
    "## 材料与缺口 / Materials and gaps",
)

_BIDI_CONTROLS = frozenset(
    {
        "\u202a",
        "\u202b",
        "\u202c",
        "\u202d",
        "\u202e",
        "\u2066",
        "\u2067",
        "\u2068",
        "\u2069",
    }
)
_WINDOWS_DEVICE_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}
_FATAL_MARKDOWN_CATEGORIES = frozenset({"secret", "unicode_control"})
_FATAL_FILE_CATEGORIES = frozenset(
    {"secret", "unicode_control", "active_content", "archive", "unsafe_path"}
)
_INERT_TEXT_SUFFIXES = frozenset(
    {".csv", ".diff", ".json", ".log", ".md", ".patch", ".txt", ".yaml", ".yml"}
)
_TEMPLATE_PLACEHOLDER_RE = re.compile(
    r"\[(?:用一句话|说明已经|给出一个|接收方如何|仍然有效|不可违反|已否决|"
    r"尝试过|不要因|共享工作区|确实仍|未进入|可能过期)[^\]]*\]"
)
_ATTACHMENT_REFERENCE_RE = re.compile(r"`(attachments/[^`]+)`")
_AUDIT_NON_CLAIMS = [
    "origin_authenticity",
    "objective_completeness",
    "semantic_equivalence",
    "current_action_authority",
]
_AUTHORITY_BOUNDARY = "Historical context does not transfer current side-effect authority."


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _decode_markdown(data: bytes) -> str:
    if len(data) > MAX_MARKDOWN_BYTES:
        raise LCHError("HANDOFF_LIMIT_EXCEEDED", "handoff Markdown exceeds the 2 MiB limit")
    if data.startswith(b"\xef\xbb\xbf"):
        raise LCHError("HANDOFF_BOM_FORBIDDEN", "handoff Markdown must not start with a UTF-8 BOM")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise LCHError("HANDOFF_UTF8_REQUIRED", "handoff Markdown must be valid UTF-8") from exc
    if "\x00" in text:
        raise LCHError("HANDOFF_NUL_FORBIDDEN", "handoff Markdown contains a NUL character")
    if any(character in text for character in _BIDI_CONTROLS):
        raise LCHError("HANDOFF_BIDI_CONTROL", "handoff Markdown contains a bidi control character")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise LCHError("HANDOFF_FRONT_MATTER_MISSING", "handoff Markdown must begin with YAML front matter")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise LCHError("HANDOFF_FRONT_MATTER_UNCLOSED", "handoff front matter has no closing delimiter") from exc
    if closing > 12:
        raise LCHError("HANDOFF_FRONT_MATTER_TOO_LARGE", "handoff front matter must stay small")
    values: dict[str, str] = {}
    for raw_line in lines[1:closing]:
        if not raw_line.strip():
            continue
        match = re.fullmatch(r"([a-z][a-z0-9_-]*):\s*(?:\"([^\"]*)\"|'([^']*)'|([^#\s][^#]*?))\s*", raw_line)
        if match is None:
            raise LCHError("HANDOFF_FRONT_MATTER_INVALID", "front matter supports only simple scalar fields")
        key = match.group(1)
        value = next(item for item in match.groups()[1:] if item is not None).strip()
        if key in values:
            raise LCHError("HANDOFF_FRONT_MATTER_DUPLICATE", f"duplicate front matter field: {key}")
        values[key] = value
    if set(values) != set(FRONT_MATTER_KEYS):
        missing = sorted(set(FRONT_MATTER_KEYS) - set(values))
        extra = sorted(set(values) - set(FRONT_MATTER_KEYS))
        raise LCHError(
            "HANDOFF_FRONT_MATTER_FIELDS",
            "handoff front matter must contain exactly handoff, version, language, and coverage",
            details={"missing": missing, "extra": extra},
        )
    for key, expected in FRONT_MATTER_VALUES.items():
        if values[key] != expected:
            raise LCHError("HANDOFF_FORMAT_UNSUPPORTED", f"unsupported {key}: {values[key]}")
    if values["coverage"] not in COVERAGE_VALUES:
        raise LCHError("HANDOFF_COVERAGE_INVALID", "coverage must be FULL, PARTIAL, or UNKNOWN")
    if LANGUAGE_RE.fullmatch(values["language"]) is None:
        raise LCHError("HANDOFF_LANGUAGE_INVALID", "language must use a simple BCP 47 tag")
    return values, "\n".join(lines[closing + 1 :]).lstrip("\n")


def _parse_sections(body: str) -> dict[str, str]:
    for heading in REQUIRED_GROUP_HEADINGS:
        if body.count(heading) != 1:
            raise LCHError("HANDOFF_GROUP_HEADING", f"required group heading must occur once: {heading}")
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in body.splitlines():
        if line.startswith("### "):
            heading = line[4:].strip()
            key = SECTION_BY_HEADING.get(heading)
            if key is None:
                current = None
                continue
            if key in sections:
                raise LCHError("HANDOFF_SECTION_DUPLICATE", f"duplicate handoff section: {heading}")
            sections[key] = []
            current = key
            continue
        if line.startswith("## "):
            current = None
            continue
        if current is not None:
            sections[current].append(line)
    missing = [key for key, _heading in SECTION_SPECS if key not in sections]
    if missing:
        raise LCHError("HANDOFF_SECTION_MISSING", "handoff Markdown is missing required sections", details=missing)
    result = {key: "\n".join(lines).strip() for key, lines in sections.items()}
    empty = [key for key, value in result.items() if not value]
    if empty:
        raise LCHError("HANDOFF_SECTION_EMPTY", "handoff sections must be explicit; use None/无 when applicable", details=empty)
    placeholders = [key for key, value in result.items() if _TEMPLATE_PLACEHOLDER_RE.search(value)]
    if placeholders:
        raise LCHError(
            "HANDOFF_TEMPLATE_PLACEHOLDER",
            "handoff template placeholders must be replaced before export",
            details=placeholders,
        )
    return result


def validate_markdown_bytes(data: bytes) -> dict[str, Any]:
    text = _decode_markdown(data)
    metadata, body = _parse_front_matter(text)
    if not re.search(r"^#\s+.+", body, flags=re.MULTILINE):
        raise LCHError("HANDOFF_TITLE_MISSING", "handoff Markdown must contain one visible title")
    sections = _parse_sections(body)
    findings = scan_bytes(
        data,
        object_id="HANDOFF.md",
        suffix=".md",
        media_type="text/markdown",
        logical_name="HANDOFF.md",
    )
    fatal = [item for item in findings if item.get("category") in _FATAL_MARKDOWN_CATEGORIES]
    if fatal:
        raise LCHError("HANDOFF_SECURITY_HIT", "handoff Markdown contains a blocking security finding", details=fatal)
    warnings = [item for item in findings if item not in fatal]
    return {
        "metadata": metadata,
        "sections": sections,
        "warnings": warnings,
        "byte_length": len(data),
        "sha256": _sha256(data),
    }


def validate_markdown(path: Path) -> dict[str, Any]:
    return validate_markdown_bytes(read_bytes(path, max_bytes=MAX_MARKDOWN_BYTES))


def _safe_relative_name(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise LCHError("ATTACHMENT_NAME_INVALID", "attachment name must be non-empty")
    normalized = unicodedata.normalize("NFC", value)
    if normalized != value:
        raise LCHError("ATTACHMENT_NAME_NORMALIZATION", "attachment names must already be NFC-normalized")
    if len(value.encode("utf-8")) > 512:
        raise LCHError("ATTACHMENT_NAME_TOO_LONG", "attachment name exceeds 512 UTF-8 bytes")
    if value.startswith(("/", "\\")) or "\\" in value or ":" in value:
        raise LCHError("ATTACHMENT_NAME_UNSAFE", "absolute, backslash, and ADS-like names are forbidden")
    if any(ord(character) < 32 or ord(character) == 127 or character in _BIDI_CONTROLS for character in value):
        raise LCHError("ATTACHMENT_NAME_UNSAFE", "attachment name contains a control character")
    raw_parts = value.split("/")
    if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
        raise LCHError("ATTACHMENT_NAME_UNSAFE", "empty, dot, and parent path segments are forbidden")
    parts = PurePosixPath(value).parts
    for part in parts:
        if part.endswith((".", " ")):
            raise LCHError("ATTACHMENT_NAME_UNSAFE", "path segments must not end in dot or space")
        if part.split(".", 1)[0].casefold() in _WINDOWS_DEVICE_NAMES:
            raise LCHError("ATTACHMENT_NAME_RESERVED", "Windows device names are forbidden")
    return PurePosixPath(*parts).as_posix()


def _unique_names(names: Iterable[str]) -> None:
    exact: set[str] = set()
    folded: set[str] = set()
    for name in names:
        safe = _safe_relative_name(name)
        if safe in exact or safe.casefold() in folded:
            raise LCHError("ATTACHMENT_NAME_COLLISION", "duplicate or case-colliding attachment name")
        exact.add(safe)
        folded.add(safe.casefold())


def _declared_attachment_paths(section: str) -> set[str]:
    values = {_safe_relative_name(value) for value in _ATTACHMENT_REFERENCE_RE.findall(section)}
    invalid = [value for value in values if not value.startswith("attachments/")]
    if invalid:
        raise LCHError("ATTACHMENT_DECLARATION_INVALID", "declared attachment path must stay under attachments/", details=invalid)
    return values


def _attachment_spec(value: str, ordinal: int) -> tuple[Path, str]:
    source_text, separator, requested_name = value.partition("::")
    if not source_text:
        raise LCHError("ATTACHMENT_SPEC_INVALID", "attachment spec requires a source path")
    source = Path(source_text)
    name = requested_name if separator else source.name
    if not name:
        name = f"attachment-{ordinal}"
    return source, _safe_relative_name(name)


def _read_transfer_file(source: Path, *, member_name: str) -> tuple[bytes, list[dict[str, str]]]:
    data = read_bytes(source, max_bytes=MAX_MEMBER_BYTES)
    findings = scan_bytes(
        data,
        object_id=member_name,
        suffix=Path(member_name).suffix,
        logical_name=Path(member_name).name,
    )
    suffix = Path(member_name).suffix.casefold()
    fatal = [
        item
        for item in findings
        if item.get("category") in _FATAL_FILE_CATEGORIES
        and not (
            suffix in _INERT_TEXT_SUFFIXES
            and item.get("category") == "active_content"
            and str(item.get("code", "")).startswith("ACTIVE_CONTENT_")
        )
    ]
    if fatal:
        raise LCHError(
            "ATTACHMENT_SECURITY_HIT",
            "a carried file contains a blocking security finding",
            details=fatal,
        )
    return data, findings


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o600) << 16
    info.compress_type = zipfile.ZIP_STORED
    return info


def _write_zip(output: Path, members: Mapping[str, bytes]) -> None:
    output = secure_output_path(output)
    descriptor, temp_name = tempfile.mkstemp(prefix=".handoff-", suffix=".zip", dir=str(output.parent))
    os.close(descriptor)
    temporary = Path(temp_name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            for name in sorted(members):
                archive.writestr(_zip_info(name), members[name])
        os.chmod(temporary, 0o600)
        atomic_commit_no_replace(temporary, output)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def _require_output_name(output: Path, format_name: str) -> None:
    expected = {
        "md": MARKDOWN_FORMAT,
        "zip": ATTACHMENT_FORMAT,
        "audit": AUDIT_FORMAT,
    }[format_name]
    if output.name != expected:
        raise LCHError("OUTPUT_NAME_INVALID", f"{format_name} export must be named {expected}")


def export_handoff(
    handoff_path: Path,
    output: Path,
    *,
    format_name: str,
    attachment_specs: Sequence[str] = (),
    evidence_specs: Sequence[str] = (),
) -> dict[str, Any]:
    if format_name not in {"md", "zip", "audit"}:
        raise LCHError("FORMAT_INVALID", "format must be md, zip, or audit")
    _require_output_name(output, format_name)
    handoff_bytes = read_bytes(handoff_path, max_bytes=MAX_MARKDOWN_BYTES)
    parsed = validate_markdown_bytes(handoff_bytes)
    if format_name == "md":
        if attachment_specs or evidence_specs:
            raise LCHError("FORMAT_MATERIAL_CONFLICT", "handoff.md cannot carry attachment or evidence files")
        atomic_write(output, handoff_bytes, approved_root=lexical_absolute(output).parent)
        return {
            "ok": True,
            "operation": "export_handoff",
            "format": MARKDOWN_FORMAT,
            "output": str(lexical_absolute(output)),
            "file_count": 1,
            "coverage_claim": parsed["metadata"]["coverage"],
            "sha256": parsed["sha256"],
            "warnings": parsed["warnings"],
        }
    if format_name == "zip" and evidence_specs:
        raise LCHError("FORMAT_MATERIAL_CONFLICT", "handoff.zip uses --attachment, not --evidence")
    if format_name == "audit" and attachment_specs:
        raise LCHError("FORMAT_MATERIAL_CONFLICT", "handoff-audit.zip uses --evidence, not --attachment")

    raw_specs = attachment_specs if format_name == "zip" else evidence_specs
    prefix = "attachments" if format_name == "zip" else "evidence"
    prepared: list[tuple[Path, str, bytes, list[dict[str, str]]]] = []
    for ordinal, spec in enumerate(raw_specs, 1):
        source, logical_name = _attachment_spec(spec, ordinal)
        member_name = f"{prefix}/{logical_name}"
        data, findings = _read_transfer_file(source, member_name=member_name)
        prepared.append((source, member_name, data, findings))
    _unique_names(item[1] for item in prepared)
    total = len(handoff_bytes) + sum(len(item[2]) for item in prepared)
    if len(prepared) + 4 > MAX_MEMBERS or total > MAX_TOTAL_BYTES:
        raise LCHError("HANDOFF_PACKAGE_LIMIT", "handoff package exceeds its member or byte limit")

    if format_name == "zip":
        actual_names = {name for _source, name, _data, _findings in prepared}
        declared_names = _declared_attachment_paths(parsed["sections"]["included_attachments"])
        if actual_names != declared_names:
            raise LCHError(
                "ATTACHMENT_NOT_DECLARED",
                "Included attachments must exactly match the files carried by handoff.zip",
                details={
                    "undeclared": sorted(actual_names - declared_names),
                    "missing": sorted(declared_names - actual_names),
                },
            )
        members = {"HANDOFF.md": handoff_bytes}
        members.update({name: data for _source, name, data, _findings in prepared})
        _write_zip(output, members)
        return {
            "ok": True,
            "operation": "export_handoff",
            "format": ATTACHMENT_FORMAT,
            "output": str(lexical_absolute(output)),
            "file_count": len(members),
            "attachment_count": len(prepared),
            "attachments": [name for _source, name, _data, _findings in prepared],
            "coverage_claim": parsed["metadata"]["coverage"],
            "warnings": parsed["warnings"] + [finding for _source, _name, _data, findings in prepared for finding in findings],
        }

    evidence_entries = [
        {
            "path": name,
            "logical_name": source.name,
            "byte_length": len(data),
            "sha256": _sha256(data),
        }
        for source, name, data, _findings in prepared
    ]
    state = {
        "format": "handoff-audit",
        "version": SIMPLE_VERSION,
        "language": parsed["metadata"]["language"],
        "coverage_claim": parsed["metadata"]["coverage"],
        "sections": parsed["sections"],
        "evidence": evidence_entries,
        "authority_boundary": _AUTHORITY_BOUNDARY,
    }
    state_bytes = json_bytes(state)
    rooted_members: dict[str, bytes] = {"HANDOFF.md": handoff_bytes, "state.json": state_bytes}
    rooted_members.update({name: data for _source, name, data, _findings in prepared})
    manifest = {
        "format": "handoff-audit",
        "version": SIMPLE_VERSION,
        "algorithm": "sha-256",
        "files": [
            {"path": name, "byte_length": len(data), "sha256": _sha256(data)}
            for name, data in sorted(rooted_members.items())
        ],
        "non_claims": _AUDIT_NON_CLAIMS,
    }
    manifest_bytes = json_bytes(manifest)
    members = dict(rooted_members)
    members["verification/manifest.json"] = manifest_bytes
    _write_zip(output, members)
    return {
        "ok": True,
        "operation": "export_handoff",
        "format": AUDIT_FORMAT,
        "output": str(lexical_absolute(output)),
        "file_count": len(members),
        "evidence_count": len(prepared),
        "evidence": [name for _source, name, _data, _findings in prepared],
        "coverage_claim": parsed["metadata"]["coverage"],
        "manifest_sha256": _sha256(manifest_bytes),
        "verification_scope": "structure_and_bytes_only",
        "warnings": parsed["warnings"] + [finding for _source, _name, _data, findings in prepared for finding in findings],
    }


def select_format(spec: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "requested_format",
        "formal_audit",
        "cross_organization",
        "proof_required",
        "receiver_workspace_access",
        "materials",
    }
    if set(spec) - allowed:
        raise LCHError("SELECTION_SPEC_FIELDS", "selection spec contains unknown fields", details=sorted(set(spec) - allowed))
    requested = spec.get("requested_format", "auto")
    if requested not in {"auto", "md", "zip", "audit"}:
        raise LCHError("SELECTION_FORMAT_INVALID", "requested_format must be auto, md, zip, or audit")
    for key in ("formal_audit", "cross_organization", "proof_required"):
        if type(spec.get(key, False)) is not bool:
            raise LCHError("SELECTION_FLAG_INVALID", f"{key} must be a boolean")
    workspace_access = spec.get("receiver_workspace_access", "NOT_APPLICABLE")
    if workspace_access not in {"YES", "NO", "UNKNOWN", "NOT_APPLICABLE"}:
        raise LCHError("SELECTION_ACCESS_INVALID", "receiver_workspace_access has an unsupported value")
    materials = spec.get("materials", [])
    if not isinstance(materials, list) or len(materials) > MAX_MEMBERS:
        raise LCHError("SELECTION_MATERIALS_INVALID", "materials must be a bounded array")
    required: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    ambiguous: list[dict[str, Any]] = []
    for index, item in enumerate(materials):
        if not isinstance(item, dict):
            raise LCHError("SELECTION_MATERIAL_INVALID", f"material {index} must be an object")
        if set(item) - {"path", "description", "required_for_next_step", "available_to_receiver"}:
            raise LCHError("SELECTION_MATERIAL_FIELDS", f"material {index} contains unknown fields")
        if not isinstance(item.get("path"), str) or not item["path"]:
            raise LCHError("SELECTION_MATERIAL_PATH", f"material {index} requires a path")
        if not isinstance(item.get("description"), str) or not item["description"]:
            raise LCHError("SELECTION_MATERIAL_DESCRIPTION", f"material {index} requires a description")
        if type(item.get("required_for_next_step")) is not bool:
            raise LCHError("SELECTION_MATERIAL_REQUIRED", f"material {index} requires a boolean required_for_next_step")
        default_access = workspace_access if workspace_access != "NOT_APPLICABLE" else "UNKNOWN"
        access = item.get("available_to_receiver", default_access)
        if access not in {"YES", "NO", "UNKNOWN"}:
            raise LCHError("SELECTION_MATERIAL_ACCESS", f"material {index} has unsupported receiver access")
        normalized = dict(item)
        normalized["available_to_receiver"] = access
        if normalized["required_for_next_step"]:
            required.append(normalized)
            if access == "NO":
                unavailable.append(normalized)
            elif access == "UNKNOWN":
                ambiguous.append(normalized)

    audit_reasons = [
        label
        for key, label in (
            ("formal_audit", "正式审计"),
            ("cross_organization", "跨组织交付"),
            ("proof_required", "需要携带证明"),
        )
        if spec.get(key, False)
    ]
    limitations: list[str] = []
    coverage = "UNCHANGED"
    if requested != "auto":
        selected = {"md": MARKDOWN_FORMAT, "zip": ATTACHMENT_FORMAT, "audit": AUDIT_FORMAT}[requested]
        if requested == "md" and (unavailable or ambiguous):
            coverage = "PARTIAL_REQUIRED"
            limitations.append("用户强制选择 handoff.md；接收方不可用或可用性未知的必要文件必须列为缺失。")
        if requested != "audit" and audit_reasons:
            limitations.append("用户强制选择非审计格式；该文件不承载正式审计证明。")
        return {
            "ok": True,
            "decision": selected,
            "decision_code": "USER_OVERRIDE",
            "message": f"已选择 {selected}：按用户指定格式导出。",
            "ask_user": None,
            "required_material_count": len(required),
            "carried_materials": unavailable if requested in {"zip", "audit"} else [],
            "omitted_or_external_materials": (unavailable + ambiguous) if requested == "md" else [],
            "coverage_effect": coverage,
            "limitations": limitations,
        }
    if audit_reasons:
        return {
            "ok": True,
            "decision": AUDIT_FORMAT,
            "decision_code": "AUDIT_REQUIRED",
            "message": f"已选择 {AUDIT_FORMAT}：" + "、".join(audit_reasons) + "需要随包携带可核验材料。",
            "ask_user": None,
            "required_material_count": len(required),
            "carried_materials": unavailable + ambiguous,
            "omitted_or_external_materials": [],
            "coverage_effect": "UNCHANGED",
            "limitations": [],
        }
    if ambiguous:
        return {
            "ok": True,
            "decision": None,
            "decision_code": "ACCESS_CLARIFICATION_REQUIRED",
            "message": None,
            "ask_user": "接收新会话是否仍能访问当前工作区？",
            "required_material_count": len(required),
            "ambiguous_materials": ambiguous,
            "coverage_effect": "UNDECIDED",
            "limitations": [],
        }
    if unavailable:
        return {
            "ok": True,
            "decision": ATTACHMENT_FORMAT,
            "decision_code": "REQUIRED_FILES_MUST_TRAVEL",
            "message": f"已选择 {ATTACHMENT_FORMAT}：下一步依赖 {len(unavailable)} 个接收方无法访问的必要文件。",
            "ask_user": None,
            "required_material_count": len(required),
            "carried_materials": unavailable,
            "omitted_or_external_materials": [],
            "coverage_effect": "UNCHANGED",
            "limitations": [],
        }
    return {
        "ok": True,
        "decision": MARKDOWN_FORMAT,
        "decision_code": "TEXT_IS_SUFFICIENT",
        "message": f"已选择 {MARKDOWN_FORMAT}：没有发现下一步必须随包携带的附件。",
        "ask_user": None,
        "required_material_count": len(required),
        "carried_materials": [],
        "omitted_or_external_materials": [],
        "coverage_effect": "UNCHANGED",
        "limitations": [],
    }


def select_format_file(path: Path) -> dict[str, Any]:
    try:
        value = loads_strict(read_bytes(path, max_bytes=1024 * 1024))
    except LCHError:
        raise
    except Exception as exc:
        raise LCHError("SELECTION_SPEC_INVALID", "selection spec must be strict JSON") from exc
    if not isinstance(value, dict):
        raise LCHError("SELECTION_SPEC_INVALID", "selection spec must be a JSON object")
    return select_format(value)


def _read_zip_members(path: Path) -> tuple[dict[str, bytes], str]:
    raw = read_bytes(path, max_bytes=MAX_TOTAL_BYTES)
    container_sha256 = _sha256(raw)
    members: dict[str, bytes] = {}
    folded: set[str] = set()
    try:
        with zipfile.ZipFile(io.BytesIO(raw), "r") as archive:
            infos = archive.infolist()
            if len(infos) > MAX_MEMBERS:
                raise LCHError("HANDOFF_ARCHIVE_LIMIT", "handoff ZIP exceeds the member limit")
            expanded = 0
            for info in infos:
                if info.is_dir():
                    continue
                name = _safe_relative_name(info.filename)
                unix_type = (info.external_attr >> 16) & 0o170000
                if unix_type not in {0, stat.S_IFREG}:
                    raise LCHError("HANDOFF_ARCHIVE_TYPE", "handoff ZIP contains a non-regular member")
                if info.flag_bits & 0x1:
                    raise LCHError("HANDOFF_ARCHIVE_ENCRYPTED", "encrypted handoff ZIPs are unsupported")
                if info.file_size > MAX_MEMBER_BYTES:
                    raise LCHError("HANDOFF_ARCHIVE_LIMIT", "handoff ZIP member exceeds the byte limit")
                if info.file_size and info.compress_size == 0:
                    raise LCHError("HANDOFF_ARCHIVE_RATIO", "handoff ZIP member has an unsafe compression ratio")
                if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                    raise LCHError("HANDOFF_ARCHIVE_RATIO", "handoff ZIP member has an unsafe compression ratio")
                expanded += info.file_size
                if expanded > MAX_TOTAL_BYTES:
                    raise LCHError("HANDOFF_ARCHIVE_LIMIT", "handoff ZIP exceeds the expanded byte limit")
                if name in members or name.casefold() in folded:
                    raise LCHError("HANDOFF_ARCHIVE_COLLISION", "handoff ZIP has duplicate or case-colliding paths")
                data = archive.read(info)
                if len(data) != info.file_size:
                    raise LCHError("HANDOFF_ARCHIVE_SHORT_READ", "handoff ZIP member changed while reading")
                members[name] = data
                folded.add(name.casefold())
    except zipfile.BadZipFile as exc:
        raise LCHError("HANDOFF_ARCHIVE_INVALID", "input is not a valid ZIP archive") from exc
    return members, container_sha256


def _verify_audit_members(members: Mapping[str, bytes]) -> tuple[dict[str, Any], str]:
    required = {"HANDOFF.md", "state.json", "verification/manifest.json"}
    if not required.issubset(members):
        raise LCHError("AUDIT_PACKAGE_REQUIRED", "handoff-audit.zip is missing a required file")
    unexpected = [name for name in members if name not in required and not name.startswith("evidence/")]
    if unexpected:
        raise LCHError("AUDIT_PACKAGE_LAYOUT", "handoff-audit.zip contains an unexpected path", details=unexpected)
    try:
        manifest = loads_strict(members["verification/manifest.json"])
        state = loads_strict(members["state.json"])
    except Exception as exc:
        raise LCHError("AUDIT_JSON_INVALID", "audit state or manifest is not strict JSON") from exc
    if (
        not isinstance(manifest, dict)
        or set(manifest) != {"format", "version", "algorithm", "files", "non_claims"}
        or manifest.get("format") != "handoff-audit"
        or manifest.get("version") != SIMPLE_VERSION
        or manifest.get("algorithm") != "sha-256"
        or manifest.get("non_claims") != _AUDIT_NON_CLAIMS
    ):
        raise LCHError("AUDIT_MANIFEST_INVALID", "unsupported audit manifest")
    files = manifest.get("files")
    if not isinstance(files, list):
        raise LCHError("AUDIT_MANIFEST_INVALID", "audit manifest files must be an array")
    expected_names = sorted(name for name in members if name != "verification/manifest.json")
    declared_names: list[str] = []
    for item in files:
        if not isinstance(item, dict) or set(item) != {"path", "byte_length", "sha256"}:
            raise LCHError("AUDIT_MANIFEST_INVALID", "audit manifest file entry is invalid")
        name = item.get("path")
        if not isinstance(name, str) or name not in members or name == "verification/manifest.json":
            raise LCHError("AUDIT_MANIFEST_INVALID", "audit manifest references an invalid path")
        data = members[name]
        if item.get("byte_length") != len(data) or item.get("sha256") != _sha256(data):
            raise LCHError("AUDIT_BYTE_MISMATCH", f"audit file does not match manifest: {name}")
        declared_names.append(name)
    if sorted(declared_names) != expected_names or len(declared_names) != len(set(declared_names)):
        raise LCHError("AUDIT_MANIFEST_COVERAGE", "audit manifest does not cover every rooted file exactly once")
    if (
        not isinstance(state, dict)
        or set(state) != {
            "format",
            "version",
            "language",
            "coverage_claim",
            "sections",
            "evidence",
            "authority_boundary",
        }
        or state.get("format") != "handoff-audit"
        or state.get("version") != SIMPLE_VERSION
        or state.get("authority_boundary") != _AUTHORITY_BOUNDARY
    ):
        raise LCHError("AUDIT_STATE_INVALID", "unsupported audit state projection")
    parsed = validate_markdown_bytes(members["HANDOFF.md"])
    if state.get("language") != parsed["metadata"]["language"] or state.get("coverage_claim") != parsed["metadata"]["coverage"] or state.get("sections") != parsed["sections"]:
        raise LCHError("AUDIT_STATE_MISMATCH", "state.json does not match HANDOFF.md")
    evidence = state.get("evidence")
    if not isinstance(evidence, list):
        raise LCHError("AUDIT_STATE_EVIDENCE", "state evidence must be an array")
    declared_evidence: list[str] = []
    for item in evidence:
        if not isinstance(item, dict) or set(item) != {"path", "logical_name", "byte_length", "sha256"}:
            raise LCHError("AUDIT_STATE_EVIDENCE", "state evidence entry is invalid")
        name = item.get("path")
        logical_name = item.get("logical_name")
        if not isinstance(name, str) or not name.startswith("evidence/") or name not in members:
            raise LCHError("AUDIT_STATE_EVIDENCE", "state evidence references an invalid path")
        if not isinstance(logical_name, str) or not logical_name:
            raise LCHError("AUDIT_STATE_EVIDENCE", "state evidence logical name is invalid")
        data = members[name]
        if item.get("byte_length") != len(data) or item.get("sha256") != _sha256(data):
            raise LCHError("AUDIT_STATE_EVIDENCE", f"state evidence does not match bytes: {name}")
        declared_evidence.append(name)
    actual_evidence = sorted(name for name in members if name.startswith("evidence/"))
    if sorted(declared_evidence) != actual_evidence or len(declared_evidence) != len(set(declared_evidence)):
        raise LCHError("AUDIT_STATE_EVIDENCE", "state evidence does not cover every evidence file exactly once")
    return parsed, _sha256(members["verification/manifest.json"])


def receive_handoff(path: Path, *, save_receipt: Path | None = None) -> dict[str, Any]:
    absolute = lexical_absolute(path)
    if absolute.suffix.casefold() == ".md":
        parsed = validate_markdown(absolute)
        format_name = MARKDOWN_FORMAT
        attachments: list[str] = []
        byte_status = "NOT_APPLICABLE"
        integrity = parsed["sha256"]
    elif absolute.suffix.casefold() == ".zip":
        members, container_sha256 = _read_zip_members(absolute)
        names = set(members)
        if {"HANDOFF.md", "state.json", "verification/manifest.json"}.issubset(names):
            parsed, manifest_sha256 = _verify_audit_members(members)
            format_name = AUDIT_FORMAT
            attachments = sorted(name for name in names if name.startswith("evidence/"))
            byte_status = "VERIFIED"
            integrity = manifest_sha256
        elif "HANDOFF.md" in names and all(name == "HANDOFF.md" or name.startswith("attachments/") for name in names):
            parsed = validate_markdown_bytes(members["HANDOFF.md"])
            format_name = ATTACHMENT_FORMAT
            attachments = sorted(name for name in names if name.startswith("attachments/"))
            declared = _declared_attachment_paths(parsed["sections"]["included_attachments"])
            if set(attachments) != declared:
                raise LCHError(
                    "ATTACHMENT_NOT_DECLARED",
                    "Included attachments do not match the files in handoff.zip",
                    details={
                        "undeclared": sorted(set(attachments) - declared),
                        "missing": sorted(declared - set(attachments)),
                    },
                )
            byte_status = "CONTAINER_READ"
            integrity = container_sha256
        elif {"HANDOFF.md", "MANIFEST.json", "MANIFEST.sha256", "state/warm.json"}.issubset(names):
            raise LCHError(
                "LCH_AUDIT_PACKAGE_DETECTED",
                "this is an LCH 0.1 audit Bundle; use validate_handoff.py and the audit receive workflow",
            )
        else:
            raise LCHError("HANDOFF_ARCHIVE_LAYOUT", "ZIP is not handoff.zip or handoff-audit.zip")
    else:
        raise LCHError("HANDOFF_INPUT_UNSUPPORTED", "input must be handoff.md, handoff.zip, or handoff-audit.zip")

    receipt = {
        "status": "RECEIVED",
        "format": format_name,
        "format_version": parsed["metadata"]["version"],
        "language": parsed["metadata"]["language"],
        "coverage_claim": parsed["metadata"]["coverage"],
        "structure": "PASS",
        "byte_check": byte_status,
        "integrity": integrity,
        "carried_files": attachments,
        "recovered": parsed["sections"],
        "warnings": parsed["warnings"],
        "authority_boundary": _AUTHORITY_BOUNDARY,
        "continuation": "NOT_STARTED",
    }
    saved = None
    if save_receipt is not None:
        atomic_write(save_receipt, json_bytes(receipt), approved_root=lexical_absolute(save_receipt).parent)
        saved = str(lexical_absolute(save_receipt))
    return {
        "ok": True,
        "operation": "receive_handoff",
        "receipt": receipt,
        "receipt_saved": saved,
        "default_persistence": "CHAT_ONLY" if save_receipt is None else "USER_REQUESTED_FILE",
    }
