"""Small deterministic I/O and reporting helpers."""

from __future__ import annotations

import json
import ctypes
import errno
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable

from .canonicalize import loads_strict


class LCHError(RuntimeError):
    """A stable, user-reportable protocol tooling failure."""

    def __init__(self, code: str, message: str, *, details: Any = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def json_bytes(value: Any, *, final_lf: bool = True) -> bytes:
    text = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return text.encode("utf-8") + (b"\n" if final_lf else b"")


def emit(value: Any) -> None:
    os.write(1, json_bytes(value))


def issue(code: str, message: str, *, object_id: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {
        "code": code,
        "severity": "error",
        "message": message,
    }
    if object_id is not None:
        result["object_id"] = object_id
    return result


def read_bytes(path: Path, *, max_bytes: int) -> bytes:
    candidate = lexical_absolute(path)
    directory_fd: int | None = None
    descriptor: int | None = None
    try:
        directory_fd = _open_directory_no_follow(candidate.parent)
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        no_follow = getattr(os, "O_NOFOLLOW", 0)
        if not no_follow:
            raise LCHError("NOFOLLOW_UNSUPPORTED", "runtime cannot safely open untrusted files")
        descriptor = os.open(
            candidate.name,
            flags | no_follow,
            dir_fd=directory_fd,
        )
    except OSError as exc:
        raise LCHError("INPUT_UNREADABLE", f"cannot safely open input: {candidate.name}") from exc
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise LCHError("INPUT_NOT_FILE", f"expected a regular file: {candidate.name}")
        if metadata.st_nlink != 1:
            raise LCHError("INPUT_HARDLINK", f"hard-linked input is forbidden: {candidate.name}")
        if metadata.st_size > max_bytes:
            raise LCHError(
                "INPUT_LIMIT_EXCEEDED",
                f"input exceeds the {max_bytes}-byte limit: {candidate.name}",
            )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, min(1024 * 1024, max_bytes + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            if total > max_bytes:
                raise LCHError(
                    "INPUT_LIMIT_EXCEEDED",
                    f"input exceeds the {max_bytes}-byte limit: {candidate.name}",
                )
        after = os.fstat(descriptor)
        if after.st_size != total or after.st_mtime_ns != metadata.st_mtime_ns:
            raise LCHError("INPUT_CHANGED", f"input changed while being read: {candidate.name}")
        return b"".join(chunks)
    except OSError as exc:
        raise LCHError("INPUT_UNREADABLE", f"cannot read input: {candidate.name}") from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)


def read_json(path: Path, *, max_bytes: int) -> Any:
    try:
        return loads_strict(read_bytes(path, max_bytes=max_bytes))
    except LCHError:
        raise
    except Exception as exc:
        raise LCHError("INVALID_JSON", f"invalid strict JSON: {path.name}") from exc


def check_json_depth(value: Any, *, maximum: int, maximum_nodes: int = 100_000) -> None:
    stack: list[tuple[Any, int]] = [(value, 1)]
    visited = 0
    while stack:
        current, depth = stack.pop()
        visited += 1
        if visited > maximum_nodes:
            raise LCHError("JSON_NODE_LIMIT", f"JSON value exceeds {maximum_nodes} nodes")
        if depth > maximum:
            raise LCHError("JSON_DEPTH_EXCEEDED", f"JSON nesting exceeds {maximum}")
        if isinstance(current, dict):
            stack.extend((item, depth + 1) for item in current.values())
        elif isinstance(current, list):
            stack.extend((item, depth + 1) for item in current)


_SAFE_RELATIVE_PATH = re.compile(r"^[A-Za-z0-9._/-]+$")
_WINDOWS_DEVICE_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
}


def safe_relative_path(
    value: str,
    *,
    allow_envelopes: bool = False,
    allow_root_files: bool = False,
) -> str:
    if not isinstance(value, str) or not value or not _SAFE_RELATIVE_PATH.fullmatch(value):
        raise LCHError("UNSAFE_PATH", "path must be non-empty relative ASCII")
    if value.startswith("/") or "\\" in value or ":" in value:
        raise LCHError("UNSAFE_PATH", "absolute, backslash, or ADS-like path is forbidden")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise LCHError("UNSAFE_PATH", "empty, dot, and parent path segments are forbidden")
    for part in parts:
        if part.endswith((".", " ")):
            raise LCHError("RESERVED_PATH", "path segments must not end in dot or space")
        device_stem = part.split(".", 1)[0].casefold()
        if device_stem in _WINDOWS_DEVICE_NAMES:
            raise LCHError("RESERVED_PATH", "Windows device path segments are forbidden")
    folded = value.casefold()
    if not allow_root_files and folded in {"manifest.json", "manifest.sha256"}:
        raise LCHError("RESERVED_PATH", "Manifest root files cannot be supplied as objects")
    if not allow_envelopes and folded.startswith("envelopes/"):
        raise LCHError("RESERVED_PATH", "detached envelope paths are post-seal only")
    return value


def ensure_unique_paths(paths: Iterable[str]) -> None:
    exact: set[str] = set()
    folded: set[str] = set()
    for value in paths:
        normalized = safe_relative_path(value)
        if normalized in exact or normalized.casefold() in folded:
            raise LCHError("PATH_COLLISION", "duplicate or case-colliding object path")
        exact.add(normalized)
        folded.add(normalized.casefold())


def lexical_absolute(path: Path) -> Path:
    """Return an absolute normalized path without dereferencing symlinks."""

    return Path(os.path.abspath(os.fspath(path)))


def _open_directory_no_follow(path: Path) -> int:
    candidate = lexical_absolute(path)
    no_follow = getattr(os, "O_NOFOLLOW", 0)
    directory_flag = getattr(os, "O_DIRECTORY", 0)
    if not no_follow or not directory_flag:
        raise LCHError(
            "NOFOLLOW_UNSUPPORTED",
            "runtime cannot safely traverse untrusted paths",
        )
    flags = os.O_RDONLY | directory_flag | no_follow | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(candidate.anchor or "/", flags)
    try:
        for member in candidate.parts[1:]:
            next_descriptor = os.open(member, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = next_descriptor
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def reject_symlink_ancestry(path: Path, *, code: str) -> Path:
    """Reject a lexical path when it or any existing ancestor is a symlink."""

    candidate = lexical_absolute(path)
    current = candidate
    while True:
        if current.is_symlink():
            raise LCHError(code, "path or parent chain contains a symlink")
        if current == current.parent:
            break
        current = current.parent
    return candidate


def secure_output_path(path: Path, *, approved_root: Path | None = None) -> Path:
    """Validate a fail-if-present output path without following a symlink chain."""

    target = lexical_absolute(path)
    root = lexical_absolute(approved_root) if approved_root is not None else target.parent
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise LCHError("OUTPUT_OUTSIDE_ROOT", "output is outside the caller-approved root") from exc
    if target.exists() or target.is_symlink():
        raise LCHError("OUTPUT_EXISTS", "refusing to replace an existing or symlink output")
    if not root.exists() or not root.is_dir() or root.is_symlink():
        raise LCHError("UNSAFE_OUTPUT_ROOT", "approved output root must be an existing non-symlink directory")
    reject_symlink_ancestry(root, code="OUTPUT_SYMLINK_PARENT")
    current = target.parent
    while True:
        if current.is_symlink():
            raise LCHError("OUTPUT_SYMLINK_PARENT", "output parent chain contains a symlink")
        if current == root:
            break
        if current == current.parent:
            raise LCHError("OUTPUT_OUTSIDE_ROOT", "output parent does not reach approved root")
        if not current.exists():
            raise LCHError("OUTPUT_PARENT_MISSING", "output parent directory must already exist")
        current = current.parent
    return target


def atomic_commit_no_replace(source: Path, target: Path) -> None:
    """Atomically publish one same-directory staged file or directory without overwrite."""

    source = lexical_absolute(source)
    target = lexical_absolute(target)
    if source.parent != target.parent:
        raise LCHError("ATOMIC_COMMIT_CROSS_DIRECTORY", "staged output must share the target directory")
    directory_fd = _open_directory_no_follow(target.parent)
    try:
        source_metadata = os.stat(source.name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISDIR(source_metadata.st_mode):
            _fsync_tree(source)
        elif stat.S_ISREG(source_metadata.st_mode):
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
            source_fd = os.open(source.name, flags, dir_fd=directory_fd)
            try:
                os.fsync(source_fd)
            finally:
                os.close(source_fd)
        else:
            raise LCHError("ATOMIC_SOURCE_TYPE_FAIL", "staged output must be a regular file or directory")
        library = ctypes.CDLL(None, use_errno=True)
        result: int | None = None
        if sys.platform == "darwin" and hasattr(library, "renameatx_np"):
            rename = library.renameatx_np
            rename.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            rename.restype = ctypes.c_int
            result = rename(
                directory_fd,
                os.fsencode(source.name),
                directory_fd,
                os.fsencode(target.name),
                0x00000004,
            )
        elif sys.platform.startswith("linux") and hasattr(library, "renameat2"):
            rename = library.renameat2
            rename.argtypes = [
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_int,
                ctypes.c_char_p,
                ctypes.c_uint,
            ]
            rename.restype = ctypes.c_int
            result = rename(
                directory_fd,
                os.fsencode(source.name),
                directory_fd,
                os.fsencode(target.name),
                0x00000001,
            )
        if result is None:
            if stat.S_ISDIR(source_metadata.st_mode):
                raise LCHError(
                    "ATOMIC_NOREPLACE_UNSUPPORTED",
                    "runtime lacks an atomic no-replace directory commit",
                )
            try:
                os.link(
                    source.name,
                    target.name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                os.unlink(source.name, dir_fd=directory_fd)
            except FileExistsError as exc:
                raise LCHError("OUTPUT_EXISTS", "refusing to replace an existing output") from exc
        elif result != 0:
            error_number = ctypes.get_errno()
            if error_number in {errno.EEXIST, errno.ENOTEMPTY}:
                raise LCHError("OUTPUT_EXISTS", "refusing to replace an existing output")
            raise LCHError(
                "ATOMIC_COMMIT_FAIL",
                f"atomic no-replace commit failed with errno {error_number}",
            )
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _fsync_tree(root: Path) -> None:
    """Flush a private staged tree bottom-up before its atomic publication."""

    directories: list[Path] = []
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    for directory, directory_names, file_names in os.walk(root, topdown=True, followlinks=False):
        base = Path(directory)
        directories.append(base)
        directory_names[:] = sorted(directory_names)
        for name in sorted(file_names):
            candidate = base / name
            metadata = candidate.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise LCHError("ATOMIC_SOURCE_TYPE_FAIL", "staged tree contains a non-regular file")
            descriptor = os.open(candidate, flags)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    directory_flags = flags | getattr(os, "O_DIRECTORY", 0)
    for directory in reversed(directories):
        descriptor = os.open(directory, directory_flags)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def atomic_write(
    path: Path,
    data: bytes,
    *,
    mode: int = 0o600,
    approved_root: Path | None = None,
) -> None:
    path = secure_output_path(path, approved_root=approved_root)
    descriptor, temp_name = tempfile.mkstemp(prefix=".lch-write-", dir=str(path.parent))
    temp_path = Path(temp_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        atomic_commit_no_replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        finally:
            raise


def stable_error(exc: BaseException, *, operation: str) -> dict[str, Any]:
    if isinstance(exc, LCHError):
        result: dict[str, Any] = {
            "ok": False,
            "operation": operation,
            "error": {"code": exc.code, "message": exc.message},
        }
        if exc.details is not None:
            result["error"]["details"] = exc.details
        return result
    return {
        "ok": False,
        "operation": operation,
        "error": {"code": "INTERNAL_ERROR", "message": type(exc).__name__},
    }
