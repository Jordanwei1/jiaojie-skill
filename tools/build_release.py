#!/usr/bin/env python3
"""Build a deterministic, skill-only Jiaojie release archive and checksum."""

from __future__ import annotations

import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
INCLUDE = ("SKILL.md", "agents", "assets", "references", "scripts")
EXCLUDE_NAMES = {"__pycache__", ".DS_Store", "project_check.py"}
FIXED_TIME = (2026, 8, 20, 0, 0, 0)


def version() -> str:
    value = json.loads((ROOT / "assets" / "protocol-version.json").read_text(encoding="utf-8"))
    return str(value["skill_version"])


def members() -> list[Path]:
    values: list[Path] = []
    for name in INCLUDE:
        path = ROOT / name
        if path.is_file():
            values.append(path)
            continue
        values.extend(item for item in path.rglob("*") if item.is_file())
    return sorted(
        path for path in values
        if not any(part in EXCLUDE_NAMES for part in path.relative_to(ROOT).parts)
        and path.suffix not in {".pyc", ".pyo"}
    )


def safe_archive_name(path: Path) -> str:
    relative = path.relative_to(ROOT).as_posix()
    parsed = PurePosixPath(relative)
    if parsed.is_absolute() or any(part in {"", ".", ".."} for part in parsed.parts):
        raise RuntimeError(f"unsafe release path: {relative}")
    return "jiaojie/" + relative


def build() -> tuple[Path, Path]:
    DIST.mkdir(exist_ok=True)
    archive = DIST / f"jiaojie-skill-{version()}.zip"
    checksum = archive.with_suffix(archive.suffix + ".sha256")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as output:
        for path in members():
            if path.is_symlink():
                raise RuntimeError(f"release member is a symlink: {path.relative_to(ROOT)}")
            info = zipfile.ZipInfo(safe_archive_name(path), FIXED_TIME)
            executable = path.suffix == ".py"
            mode = 0o755 if executable else 0o644
            info.external_attr = (stat.S_IFREG | mode) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum.write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    return archive, checksum


if __name__ == "__main__":
    built, digest_file = build()
    print(built.relative_to(ROOT))
    print(digest_file.relative_to(ROOT))
