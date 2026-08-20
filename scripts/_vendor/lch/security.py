"""Conservative, non-executing static security scan helpers."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from .util import LCHError, lexical_absolute, read_bytes, reject_symlink_ancestry


SECRET_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("PRIVATE_KEY", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("AWS_ACCESS_KEY", re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("GITHUB_TOKEN", re.compile(rb"\bgh[pousr]_[A-Za-z0-9_]{30,}\b")),
    ("SLACK_TOKEN", re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b")),
    ("JWT", re.compile(rb"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    (
        "CREDENTIAL_ASSIGNMENT",
        re.compile(
            rb"(?i)[\"']?(?:password|passwd|api[_-]?key|access[_-]?token|client[_-]?secret)[\"']?\s*[:=]\s*[\"']?[^\s\"',;}]{4,}"
        ),
    ),
    (
        "AUTHORIZATION_HEADER",
        re.compile(
            rb"(?i)[\"']?authorization[\"']?\s*:\s*[\"']?(?:bearer|basic)\s+[^\s\"',;}]+"
        ),
    ),
)

ABSOLUTE_PATH_PATTERNS: tuple[re.Pattern[bytes], ...] = (
    re.compile(rb"(?<![A-Za-z0-9])/(?:Users|home|root|private|tmp|var|etc|opt)/[^\s\x00]+"),
    re.compile(rb"(?i)\b[A-Z]:\\(?:[^\r\n\x00]+)"),
    re.compile(rb"(?i)\bfile://(?:/|localhost/)[^\s\x00]+"),
    re.compile(rb"\\\\[A-Za-z0-9._-]+\\[^\r\n\x00]+"),
    re.compile(rb"(?<![A-Za-z0-9:/])/(?:[A-Za-z0-9._-]+/)+[A-Za-z0-9._-]+"),
)

ACTIVE_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("HTML_SCRIPT", re.compile(rb"(?i)<\s*(?:script|iframe|object|embed|applet)\b")),
    ("JAVASCRIPT_URI", re.compile(rb"(?i)\bjavascript\s*:")),
    ("SHELL_SHEBANG", re.compile(rb"(?m)^#!\s*/(?:usr/)?bin/(?:sh|bash|zsh|fish|python|perl|ruby|node)\b")),
    ("OFFICE_MACRO_HINT", re.compile(rb"(?i)\b(?:vbaProject\.bin|AutoOpen|Document_Open|Workbook_Open)\b")),
)

ARCHIVE_MAGIC: tuple[tuple[str, bytes], ...] = (
    ("ZIP", b"PK\x03\x04"),
    ("GZIP", b"\x1f\x8b"),
    ("BZIP2", b"BZh"),
    ("XZ", b"\xfd7zXZ\x00"),
    ("RAR", b"Rar!\x1a\x07"),
    ("SEVEN_Z", b"7z\xbc\xaf\x27\x1c"),
)

ACTIVE_EXTENSIONS = {
    ".app", ".bat", ".cmd", ".com", ".dll", ".dmg", ".exe", ".hta",
    ".jar", ".js", ".jse", ".lnk", ".mjs", ".msi", ".ps1", ".scr",
    ".vbe", ".vbs", ".wsf", ".xla", ".xlam", ".xlsm", ".docm", ".pptm",
}

ARCHIVE_EXTENSIONS = {
    ".7z", ".bz2", ".gz", ".iso", ".rar", ".tar", ".tgz", ".xz", ".zip",
}

ACTIVE_MEDIA_TYPES = {
    "application/javascript",
    "application/wasm",
    "application/x-executable",
    "application/x-msdownload",
    "application/x-sh",
    "text/javascript",
}

ARCHIVE_MEDIA_TYPES = {
    "application/gzip",
    "application/vnd.rar",
    "application/x-7z-compressed",
    "application/x-bzip2",
    "application/x-rar-compressed",
    "application/x-tar",
    "application/x-xz",
    "application/zip",
}


def _finding(code: str, category: str, object_id: str) -> dict[str, str]:
    return {
        "code": code,
        "category": category,
        "object_id": object_id,
        "severity": "blocking",
    }


def scan_bytes(
    data: bytes,
    *,
    object_id: str,
    suffix: str = "",
    media_type: str = "",
    logical_name: str = "",
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    lowered_suffix = suffix.lower()
    lowered_name = Path(logical_name).name.casefold()
    if lowered_name == ".env" or lowered_name.startswith(".env."):
        findings.append(_finding("DOTENV_FILE", "secret", object_id))
    if lowered_suffix in ACTIVE_EXTENSIONS:
        findings.append(_finding("ACTIVE_FILE_TYPE", "active_content", object_id))
    if lowered_suffix in ARCHIVE_EXTENSIONS:
        findings.append(_finding("ARCHIVE_FILE_TYPE", "archive", object_id))
    normalized_media_type = media_type.split(";", 1)[0].strip().lower()
    if normalized_media_type in ACTIVE_MEDIA_TYPES:
        findings.append(_finding("ACTIVE_MEDIA_TYPE", "active_content", object_id))
    if normalized_media_type in ARCHIVE_MEDIA_TYPES:
        findings.append(_finding("ARCHIVE_MEDIA_TYPE", "archive", object_id))
    for name, magic in ARCHIVE_MAGIC:
        if data.startswith(magic):
            findings.append(_finding("ARCHIVE_MAGIC_" + name, "archive", object_id))
    if data.startswith(b"\x7fELF") or data.startswith(b"MZ") or data[:4] in {
        b"\xfe\xed\xfa\xce", b"\xfe\xed\xfa\xcf", b"\xcf\xfa\xed\xfe", b"\xce\xfa\xed\xfe"
    }:
        findings.append(_finding("EXECUTABLE_MAGIC", "active_content", object_id))
    for name, pattern in SECRET_PATTERNS:
        if pattern.search(data):
            findings.append(_finding("SECRET_" + name, "secret", object_id))
    if any(pattern.search(data) for pattern in ABSOLUTE_PATH_PATTERNS):
        findings.append(_finding("ABSOLUTE_PATH_DISCLOSURE", "absolute_path", object_id))
    for name, pattern in ACTIVE_PATTERNS:
        if pattern.search(data):
            findings.append(_finding("ACTIVE_CONTENT_" + name, "active_content", object_id))
    if any(marker in data for marker in (b"\xe2\x80\xaa", b"\xe2\x80\xab", b"\xe2\x80\xae", b"\xe2\x81\xa6", b"\xe2\x81\xa7", b"\xe2\x81\xa8")):
        findings.append(_finding("BIDI_CONTROL", "unicode_control", object_id))
    unique = {(item["code"], item["object_id"]): item for item in findings}
    return [unique[key] for key in sorted(unique)]


def scan_path(path: Path, *, max_file_bytes: int, max_files: int) -> dict[str, Any]:
    path = lexical_absolute(path)
    files: list[Path]
    if path.is_symlink():
        findings = [_finding("SYMLINK_INPUT", "unsafe_path", path.name)]
        return {"findings": findings, "files_scanned": 0, "bytes_scanned": 0}
    reject_symlink_ancestry(path.parent, code="SCAN_PARENT_SYMLINK")
    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = []
        for directory, directory_names, file_names in os.walk(path, followlinks=False):
            base = Path(directory)
            for name in sorted(tuple(directory_names)):
                candidate = base / name
                if candidate.is_symlink():
                    files.append(candidate)
                    directory_names.remove(name)
            for name in sorted(file_names):
                files.append(base / name)
            if len(files) > max_files:
                raise LCHError("SCAN_FILE_LIMIT", f"scan exceeds {max_files} files")
    else:
        raise LCHError("INPUT_UNREADABLE", "scan input is not a regular file or directory")

    findings: list[dict[str, str]] = []
    total = 0
    for candidate in files:
        object_id = candidate.name if path.is_file() else candidate.relative_to(path).as_posix()
        if candidate.is_symlink():
            findings.append(_finding("SYMLINK_MEMBER", "unsafe_path", object_id))
            continue
        data = read_bytes(candidate, max_bytes=max_file_bytes)
        total += len(data)
        findings.extend(
            scan_bytes(
                data,
                object_id=object_id,
                suffix=candidate.suffix,
                logical_name=candidate.name,
            )
        )
    unique = {(item["code"], item["object_id"]): item for item in findings}
    return {
        "findings": [unique[key] for key in sorted(unique)],
        "files_scanned": len(files),
        "bytes_scanned": total,
    }
