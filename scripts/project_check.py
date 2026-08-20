#!/usr/bin/env python3
"""Run the dependency-free public-repository checks."""

from __future__ import annotations

import compileall
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
REQUIRED = [
    "README.md", "README_EN.md", "README_FR.md", "README_ES.md", "README_JA.md", "README_KO.md",
    "SKILL.md", "LICENSE", "CONTRIBUTING.md", "COMMUNITY.md", "SECURITY.md", "CODE_OF_CONDUCT.md",
    "GOVERNANCE.md", "CHANGELOG.md", "NOTICE.md", "agents/openai.yaml", "assets/hero.gif",
]


def fail(message: str) -> None:
    raise RuntimeError(message)


def check_required() -> None:
    for relative in REQUIRED:
        path = ROOT / relative
        if not path.is_file() or path.stat().st_size == 0:
            fail(f"required file is absent or empty: {relative}")


def check_json() -> None:
    for path in sorted(ROOT.rglob("*.json")):
        if any(part in {".git", "dist", "build"} for part in path.parts):
            continue
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise RuntimeError(f"invalid JSON: {path.relative_to(ROOT)}: {exc}") from exc


def check_markdown_links() -> None:
    for path in sorted(ROOT.rglob("*.md")):
        if ".git" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for raw in MARKDOWN_LINK.findall(text):
            target = raw.strip().split()[0].strip("<>")
            if not target or target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            relative = target.split("#", 1)[0]
            if relative and not (path.parent / relative).resolve().exists():
                fail(f"broken local link in {path.relative_to(ROOT)}: {target}")


def check_portability() -> None:
    forbidden = ("app:" + "//-", "/Users/" + "jordanwei/", "C:\\Users\\" + "jordanwei\\")
    text_suffixes = {".md", ".json", ".yaml", ".yml", ".py", ".txt"}
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or ".git" in path.parts or path.suffix.lower() not in text_suffixes:
            continue
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                fail(f"non-portable token {token!r} in {path.relative_to(ROOT)}")


def check_generated_examples() -> None:
    subprocess.run([sys.executable, str(ROOT / "tools" / "build_public_examples.py")], cwd=ROOT, check=True)


def run_tests() -> None:
    suite = unittest.defaultTestLoader.discover(str(ROOT / "tests"))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        fail("unit tests failed")


def main() -> int:
    check_required()
    check_generated_examples()
    check_json()
    check_markdown_links()
    check_portability()
    if not compileall.compile_dir(str(ROOT / "scripts"), quiet=1):
        fail("script compilation failed")
    if not compileall.compile_dir(str(ROOT / "tools"), quiet=1):
        fail("tool compilation failed")
    run_tests()
    print("PROJECT_CHECK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
