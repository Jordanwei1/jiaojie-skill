#!/usr/bin/env python3
"""Capture an immutable-style local deterministic check record."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "evals" / "results" / "project-deterministic-2026-08-20"
PINNED = [
    "SKILL.md",
    "assets/protocol-version.json",
    "assets/registry/registry-lock.json",
    "assets/vectors/index.json",
    "examples/index.json",
    "scripts/project_check.py",
]


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "project_check.py")],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    RESULT.mkdir(parents=True, exist_ok=True)
    log = completed.stdout.replace(str(ROOT), "<PROJECT_ROOT>")
    (RESULT / "project-check.log").write_text(log, encoding="utf-8")
    match = re.search(r"Ran (\d+) tests", log)
    summary = {
        "schema_version": "jiaojie-project-evidence-v0.1",
        "evidence_id": "project-deterministic-2026-08-20",
        "captured_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "PASS" if completed.returncode == 0 and "PROJECT_CHECK_PASS" in log else "FAIL",
        "claim_scope": [
            "public package contract",
            "human-first format selection and round trip",
            "audit byte mutation rejection",
            "path and attachment safety",
            "strict JSON and pinned protocol asset integrity",
            "seven-domain synthetic candidate corpus structure"
        ],
        "not_claimed": [
            "cross-model semantic continuity",
            "cross-language model performance",
            "Runtime installation or behavior beyond the separately recorded local discovery probe",
            "source truth, origin, approval, authorization, or absence of all secrets",
            "human or third-party verification"
        ],
        "test_count": int(match.group(1)) if match else None,
        "command": "python3 scripts/project_check.py",
        "exit_code": completed.returncode,
        "python": platform.python_version(),
        "platform": platform.system(),
        "artifacts": {relative: digest(ROOT / relative) for relative in PINNED},
        "log_sha256": digest(RESULT / "project-check.log"),
    }
    (RESULT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (RESULT / "README.md").write_text(
        "# Project deterministic evidence — 2026-08-20\n\n"
        f"Status: **{summary['status']}**  \n"
        f"Tests: **{summary['test_count']}**  \n"
        "Command: `python3 scripts/project_check.py`\n\n"
        "This record covers dependency-free deterministic repository, format, archive, security, JSON, integrity-lock, and public-corpus checks. It does not claim cross-model semantics, Runtime behavior, human review, third-party reproduction, truth, approval, or current authorization.\n\n"
        "Re-run the command from the repository root and compare the pinned artifact hashes in `summary.json`.\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
