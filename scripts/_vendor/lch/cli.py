"""Argument parsing and stable JSON responses for all thin entry points."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable, Sequence

from .converters import convert_legacy
from .package import MAX_OBJECT_BYTES, pack_bundle, pack_t0
from .security import scan_path
from .simple import export_handoff, receive_handoff, select_format_file, validate_markdown
from .util import LCHError, emit, stable_error
from .validate import (
    deterministic_results,
    public_report,
    validate_native,
    write_result_set,
)


class JSONArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise LCHError("CLI_USAGE", message)


def _execute(operation: str, function: Callable[[], tuple[dict[str, Any], int]]) -> int:
    try:
        payload, status = function()
    except Exception as exc:
        emit(stable_error(exc, operation=operation))
        return 2
    emit(payload)
    return status


def pack_main(argv: Sequence[str] | None = None) -> int:
    parser = JSONArgumentParser(
        prog="pack_handoff.py",
        description="Create a native PROPOSED Bundle or T0 draft without issuing post-seal results.",
    )
    parser.add_argument("--transport", required=True, choices=("bundle", "t0"))
    parser.add_argument("--root", required=True, type=Path, help="Pre-seal common package-root JSON.")
    parser.add_argument("--warm", required=True, type=Path, help="Canonical WARM JSON input.")
    parser.add_argument("--object-map", required=True, type=Path, help="Staging-only JSON array describing COLD/artifact files.")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--archive", action="store_true", help="For Bundle only, emit a deterministic stored ZIP.")

    def run() -> tuple[dict[str, Any], int]:
        args = parser.parse_args(argv)
        if args.transport == "t0" and args.archive:
            raise LCHError("CLI_USAGE", "--archive applies only to Bundle transport")
        if args.transport == "bundle":
            result = pack_bundle(args.root, args.warm, args.object_map, args.output, archive=args.archive)
        else:
            result = pack_t0(args.root, args.warm, args.object_map, args.output)
        return result, 0

    return _execute("pack_handoff", run)


def validate_main(argv: Sequence[str] | None = None) -> int:
    parser = JSONArgumentParser(
        prog="validate_handoff.py",
        description="Validate native structure, rooted bytes, and deterministic review projection without issuing trust results.",
    )
    parser.add_argument("input", type=Path)

    def run() -> tuple[dict[str, Any], int]:
        args = parser.parse_args(argv)
        report = validate_native(args.input)
        public = public_report(report)
        return public, 0 if public["ok"] else 1

    return _execute("validate_handoff", run)


def verify_main(argv: Sequence[str] | None = None) -> int:
    parser = JSONArgumentParser(
        prog="verify_handoff.py",
        description="Issue only deterministic structure, byte, and review result payloads for one native package.",
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--principal-id", required=True)
    parser.add_argument("--tenant-id")
    parser.add_argument("--runtime", required=True)
    parser.add_argument("--issued-at", required=True, help="Explicit RFC 3339 timestamp; never inferred into canonical state.")

    def run() -> tuple[dict[str, Any], int]:
        args = parser.parse_args(argv)
        report = validate_native(args.input)
        results = deterministic_results(
            report,
            principal_id=args.principal_id,
            tenant_id=args.tenant_id,
            runtime=args.runtime,
            issued_at=args.issued_at,
        )
        files = write_result_set(args.output_dir, results)
        public = public_report(report)
        public["operation"] = "verify_handoff"
        public["issued_result_types"] = [item["type"] for item in results]
        public["issued_result_files"] = files
        public["output_dir"] = str(args.output_dir.absolute())
        public["issuer_boundary"] = "deterministic_verifier_only"
        return public, 0 if public["ok"] else 1

    return _execute("verify_handoff", run)


def scan_main(argv: Sequence[str] | None = None) -> int:
    parser = JSONArgumentParser(
        prog="scan_sensitive.py",
        description="Conservatively scan untrusted bytes for secrets, absolute paths, active content, archives, and symlinks.",
    )
    parser.add_argument("input", type=Path)
    parser.add_argument(
        "--on-hit",
        choices=("refuse", "quarantine", "redacted_export"),
        default="quarantine",
    )
    parser.add_argument("--max-file-bytes", type=int, default=MAX_OBJECT_BYTES)
    parser.add_argument("--max-files", type=int, default=4096)

    def run() -> tuple[dict[str, Any], int]:
        args = parser.parse_args(argv)
        scan = scan_path(args.input, max_file_bytes=args.max_file_bytes, max_files=args.max_files)
        hit = bool(scan["findings"])
        payload = {
            "ok": not hit,
            "operation": "scan_sensitive",
            "result": "SECURITY_HIT" if hit else "NO_HIT_DETECTED",
            "disposition": args.on_hit.upper() if hit else None,
            "files_scanned": scan["files_scanned"],
            "bytes_scanned": scan["bytes_scanned"],
            "findings": scan["findings"],
            "security_run_result_issued": False,
            "approved_original": False,
        }
        return payload, 3 if hit else 0

    return _execute("scan_sensitive", run)


def convert_main(format_name: str, argv: Sequence[str] | None = None) -> int:
    program = {
        "handoff_markdown": "convert_handoff_md.py",
        "och_snapshot": "convert_och.py",
        "ltm_packet": "convert_ltm.py",
    }[format_name]
    parser = JSONArgumentParser(
        prog=program,
        description="Create conservative PARTIAL/INELIGIBLE/PROPOSED native staging plus its legacy conversion report.",
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--created-at", required=True, help="Explicit RFC 3339 conversion timestamp.")
    parser.add_argument("--tenant-id", required=True, help="Stable tenant ID for conservative native staging.")
    parser.add_argument(
        "--approve-original-transfer",
        action="store_true",
        help="Declare current authority to include the clean original in the later native package object map.",
    )
    parser.add_argument(
        "--format-override",
        action="store_true",
        help="Record a user-declared format choice; this does not prove conformance.",
    )
    parser.add_argument(
        "--on-security-hit",
        choices=("REFUSE", "QUARANTINE", "REDACTED_EXPORT"),
        default="QUARANTINE",
    )

    def run() -> tuple[dict[str, Any], int]:
        args = parser.parse_args(argv)
        result = convert_legacy(
            args.input,
            args.output,
            format_name=format_name,
            format_override=args.format_override,
            on_security_hit=args.on_security_hit,
            created_at=args.created_at,
            tenant_id=args.tenant_id,
            approve_original_transfer=args.approve_original_transfer,
        )
        return result, 0 if result["ok"] else 3

    return _execute("convert_legacy", run)


def simple_main(argv: Sequence[str] | None = None) -> int:
    parser = JSONArgumentParser(
        prog="handoff.py",
        description="Select, export, validate, or receive the human-first handoff formats.",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    select_parser = commands.add_parser("select", help="Select md, zip, or audit from a strict JSON decision spec.")
    select_parser.add_argument("--input", required=True, type=Path)

    export_parser = commands.add_parser("export", help="Publish exactly one handoff artifact.")
    export_parser.add_argument("--handoff", required=True, type=Path, help="Completed handoff Markdown draft.")
    export_parser.add_argument("--output", required=True, type=Path)
    export_parser.add_argument("--format", required=True, choices=("md", "zip", "audit"))
    export_parser.add_argument(
        "--attachment",
        action="append",
        default=[],
        help="For handoff.zip: SOURCE or SOURCE::relative-name.",
    )
    export_parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="For handoff-audit.zip: SOURCE or SOURCE::relative-name.",
    )

    validate_parser = commands.add_parser("validate", help="Validate a completed handoff.md.")
    validate_parser.add_argument("input", type=Path)

    receive_parser = commands.add_parser("receive", help="Receive a human-first handoff without writing files by default.")
    receive_parser.add_argument("input", type=Path)
    receive_parser.add_argument(
        "--save-receipt",
        type=Path,
        help="Persist receipt JSON only when the user explicitly requests it.",
    )

    def run() -> tuple[dict[str, Any], int]:
        args = parser.parse_args(argv)
        if args.command == "select":
            return select_format_file(args.input), 0
        if args.command == "export":
            result = export_handoff(
                args.handoff,
                args.output,
                format_name=args.format,
                attachment_specs=args.attachment,
                evidence_specs=args.evidence,
            )
            return result, 0
        if args.command == "validate":
            validated = validate_markdown(args.input)
            return {
                "ok": True,
                "operation": "validate_handoff_markdown",
                "format": "handoff.md",
                "metadata": validated["metadata"],
                "section_names": list(validated["sections"]),
                "byte_length": validated["byte_length"],
                "sha256": validated["sha256"],
                "warnings": validated["warnings"],
            }, 0
        return receive_handoff(args.input, save_receipt=args.save_receipt), 0

    return _execute("human_first_handoff", run)
