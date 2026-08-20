"""Offline tests for the fast handoff selector, formats, and receive behavior."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
VENDOR_ROOT = PROJECT_ROOT / "scripts" / "_vendor"
if str(VENDOR_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDOR_ROOT))

from lch.simple import (  # noqa: E402
    ATTACHMENT_FORMAT,
    AUDIT_FORMAT,
    MARKDOWN_FORMAT,
    export_handoff,
    receive_handoff,
    select_format,
    validate_markdown_bytes,
)
from lch.util import LCHError  # noqa: E402


def handoff_text(*, attachments: str = "- 无 / None.", coverage: str = "PARTIAL") -> str:
    return f'''---
handoff: "task-context"
version: "1.0"
language: "zh-Hans"
coverage: "{coverage}"
---

# 任务交接 / Task Handoff

## 继续位置 / Resume

### 当前目标 / Current goal

完成快速交接格式的回环验证。

### 停止位置 / Stopped at

实现完成，等待独立接收测试。

### 建议下一步 / Recommended next action

接收文件并核对三项关键边界。

### 完成标准 / Completion criteria

- 不重复已回答问题。
- 不复活已否决方向。

## 不可丢失 / Keep

### 有效决定 / Active decisions

- Markdown 是普通交接的权威源。

### 约束与权限 / Constraints and authority

- 历史交接不转移当前外部写入权限。

### 不要复活 / Do not revive

- 不要把每次普通交接升级为完整审计包。

### 失败尝试 / Failed attempts

- 全量审计默认路径耗时过长且产生太多文件。

### 已回答问题 / Answered questions

- 默认格式已经确定为 handoff.md。

## 材料与缺口 / Materials and gaps

### 工作区与关键文件 / Workspace and important files

- 接收方可访问同一测试工作区。

### 随包附件 / Included attachments

{attachments}

### 未决问题 / Open questions

- 无 / None.

### 已知缺失 / Known omissions

- 未包含完整逐字节历史会话。

### 需要重新验证 / Revalidate

- 真实跨 Runtime 行为尚未验证。
'''


def material(*, access: str, required: bool = True) -> dict[str, object]:
    return {
        "path": "/workspace/change.patch",
        "description": "未提交补丁",
        "required_for_next_step": required,
        "available_to_receiver": access,
    }


class SelectionTests(unittest.TestCase):
    def base(self) -> dict[str, object]:
        return {
            "requested_format": "auto",
            "formal_audit": False,
            "cross_organization": False,
            "proof_required": False,
            "receiver_workspace_access": "NOT_APPLICABLE",
            "materials": [],
        }

    def test_text_is_default(self) -> None:
        result = select_format(self.base())
        self.assertEqual(result["decision"], MARKDOWN_FORMAT)
        self.assertEqual(result["decision_code"], "TEXT_IS_SUFFICIENT")
        self.assertIn("没有发现下一步必须随包携带的附件", result["message"])

    def test_accessible_required_file_does_not_force_zip(self) -> None:
        spec = self.base()
        spec["materials"] = [material(access="YES")]
        self.assertEqual(select_format(spec)["decision"], MARKDOWN_FORMAT)

    def test_global_workspace_access_applies_when_material_has_no_override(self) -> None:
        spec = self.base()
        spec["receiver_workspace_access"] = "YES"
        item = material(access="YES")
        item.pop("available_to_receiver")
        spec["materials"] = [item]
        self.assertEqual(select_format(spec)["decision"], MARKDOWN_FORMAT)

    def test_unavailable_required_file_upgrades_to_zip(self) -> None:
        spec = self.base()
        spec["materials"] = [material(access="NO")]
        result = select_format(spec)
        self.assertEqual(result["decision"], ATTACHMENT_FORMAT)
        self.assertEqual(result["required_material_count"], 1)

    def test_only_material_ambiguity_asks_user(self) -> None:
        spec = self.base()
        spec["receiver_workspace_access"] = "UNKNOWN"
        self.assertIsNone(select_format(spec)["ask_user"])
        spec["materials"] = [material(access="UNKNOWN")]
        result = select_format(spec)
        self.assertIsNone(result["decision"])
        self.assertEqual(result["ask_user"], "接收新会话是否仍能访问当前工作区？")

    def test_audit_reasons_upgrade_to_audit_zip(self) -> None:
        for flag in ("formal_audit", "cross_organization", "proof_required"):
            spec = self.base()
            spec[flag] = True
            self.assertEqual(select_format(spec)["decision"], AUDIT_FORMAT)

    def test_user_markdown_override_is_honored_and_partial(self) -> None:
        spec = self.base()
        spec["requested_format"] = "md"
        spec["materials"] = [material(access="NO")]
        result = select_format(spec)
        self.assertEqual(result["decision"], MARKDOWN_FORMAT)
        self.assertEqual(result["coverage_effect"], "PARTIAL_REQUIRED")
        self.assertTrue(result["limitations"])


class FormatRoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        safe_temp_root = Path("/private/tmp") if Path("/private/tmp").is_dir() else Path(tempfile.gettempdir()).resolve()
        self.temporary = tempfile.TemporaryDirectory(dir=safe_temp_root)
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def write_draft(self, *, attachments: str = "- 无 / None.") -> Path:
        path = self.root / "draft.md"
        path.write_text(handoff_text(attachments=attachments), encoding="utf-8")
        return path

    def test_markdown_export_is_one_file_and_receipt_is_chat_only(self) -> None:
        output = self.root / "handoff.md"
        result = export_handoff(self.write_draft(), output, format_name="md")
        self.assertEqual(result["file_count"], 1)
        before = sorted(path.name for path in self.root.iterdir())
        received = receive_handoff(output)
        after = sorted(path.name for path in self.root.iterdir())
        self.assertEqual(before, after)
        self.assertEqual(received["default_persistence"], "CHAT_ONLY")
        self.assertIsNone(received["receipt_saved"])
        self.assertEqual(received["receipt"]["status"], "RECEIVED")
        self.assertEqual(received["receipt"]["continuation"], "NOT_STARTED")

    def test_attachment_zip_has_only_handoff_and_attachments(self) -> None:
        source = self.root / "change.patch"
        source.write_text("diff --git a/a b/a\n", encoding="utf-8")
        output = self.root / "handoff.zip"
        draft = self.write_draft(attachments="- `attachments/change.patch` — 未提交补丁。")
        result = export_handoff(
            draft,
            output,
            format_name="zip",
            attachment_specs=[f"{source}::change.patch"],
        )
        self.assertEqual(result["attachment_count"], 1)
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(sorted(archive.namelist()), ["HANDOFF.md", "attachments/change.patch"])
        received = receive_handoff(output)
        self.assertEqual(received["receipt"]["format"], ATTACHMENT_FORMAT)
        self.assertEqual(received["receipt"]["carried_files"], ["attachments/change.patch"])

    def test_audit_zip_layout_and_byte_verification(self) -> None:
        source = self.root / "evidence.txt"
        source.write_text("offline evidence\n", encoding="utf-8")
        output = self.root / "handoff-audit.zip"
        result = export_handoff(
            self.write_draft(),
            output,
            format_name="audit",
            evidence_specs=[f"{source}::evidence.txt"],
        )
        self.assertEqual(result["verification_scope"], "structure_and_bytes_only")
        with zipfile.ZipFile(output) as archive:
            self.assertEqual(
                sorted(archive.namelist()),
                ["HANDOFF.md", "evidence/evidence.txt", "state.json", "verification/manifest.json"],
            )
        received = receive_handoff(output)
        self.assertEqual(received["receipt"]["format"], AUDIT_FORMAT)
        self.assertEqual(received["receipt"]["byte_check"], "VERIFIED")

    def test_audit_byte_mutation_is_rejected(self) -> None:
        output = self.root / "handoff-audit.zip"
        export_handoff(self.write_draft(), output, format_name="audit")
        tampered = self.root / "tampered.zip"
        with zipfile.ZipFile(output) as original, zipfile.ZipFile(tampered, "w") as changed:
            for name in original.namelist():
                data = original.read(name)
                if name == "HANDOFF.md":
                    data += b"\nchanged\n"
                changed.writestr(name, data)
        with self.assertRaisesRegex(LCHError, "audit file does not match manifest"):
            receive_handoff(tampered)

    def test_explicit_receipt_save_creates_one_requested_file(self) -> None:
        output = self.root / "handoff.md"
        export_handoff(self.write_draft(), output, format_name="md")
        receipt_path = self.root / "receipt.json"
        result = receive_handoff(output, save_receipt=receipt_path)
        self.assertEqual(result["receipt_saved"], str(receipt_path))
        saved = json.loads(receipt_path.read_text(encoding="utf-8"))
        self.assertEqual(saved["status"], "RECEIVED")

    def test_path_traversal_zip_is_rejected(self) -> None:
        malicious = self.root / "malicious.zip"
        with zipfile.ZipFile(malicious, "w") as archive:
            archive.writestr("HANDOFF.md", handoff_text())
            archive.writestr("attachments/../../escape.txt", "no")
        with self.assertRaisesRegex(LCHError, "parent path segments"):
            receive_handoff(malicious)

    def test_undeclared_attachment_is_rejected(self) -> None:
        source = self.root / "change.patch"
        source.write_text("patch\n", encoding="utf-8")
        with self.assertRaisesRegex(LCHError, "must exactly match"):
            export_handoff(
                self.write_draft(),
                self.root / "handoff.zip",
                format_name="zip",
                attachment_specs=[str(source)],
            )

    def test_declared_but_missing_attachment_is_rejected(self) -> None:
        draft = self.write_draft(attachments="- `attachments/missing.patch` — 必需补丁。")
        with self.assertRaisesRegex(LCHError, "must exactly match"):
            export_handoff(draft, self.root / "handoff.zip", format_name="zip")

    def test_markdown_contract_rejects_missing_negative_knowledge(self) -> None:
        data = handoff_text().replace("### 不要复活 / Do not revive", "### 删除的标题").encode("utf-8")
        with self.assertRaisesRegex(LCHError, "missing required sections"):
            validate_markdown_bytes(data)

    def test_unfilled_template_is_rejected(self) -> None:
        template = PROJECT_ROOT / "assets" / "templates" / "handoff.template.md"
        with self.assertRaisesRegex(LCHError, "placeholders must be replaced"):
            validate_markdown_bytes(template.read_bytes())

    def test_patch_shebang_is_inert_text_not_executable(self) -> None:
        source = self.root / "change.patch"
        source.write_text("+#!/usr/bin/env python3\n+print('safe patch data')\n", encoding="utf-8")
        draft = self.write_draft(attachments="- `attachments/change.patch` — 未提交补丁。")
        result = export_handoff(
            draft,
            self.root / "handoff.zip",
            format_name="zip",
            attachment_specs=[f"{source}::change.patch"],
        )
        self.assertEqual(result["attachment_count"], 1)


if __name__ == "__main__":
    unittest.main()
