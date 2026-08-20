"""Public-package and deterministic protocol contract tests."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "scripts" / "_vendor"
if str(VENDOR) not in sys.path:
    sys.path.insert(0, str(VENDOR))

from lch.canonicalize import DuplicateKeyError, UnsupportedNumberError, canonicalize, loads_strict  # noqa: E402
from lch.converters import convert_legacy  # noqa: E402
from lch.registry import protocol_assets, verified_vectors  # noqa: E402
from lch.security import scan_bytes  # noqa: E402
from lch.simple import validate_markdown_bytes  # noqa: E402


class SkillContractTests(unittest.TestCase):
    def test_skill_frontmatter_has_only_public_fields(self) -> None:
        text = (ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("---\n"))
        block = text.split("---", 2)[1]
        keys = [line.split(":", 1)[0] for line in block.splitlines() if ":" in line]
        self.assertEqual(keys, ["name", "description"])
        self.assertIn("name: jiaojie", block)

    def test_openai_metadata_invokes_public_name(self) -> None:
        text = (ROOT / "agents" / "openai.yaml").read_text(encoding="utf-8")
        self.assertIn("$jiaojie", text)
        self.assertNotIn("$handoff-context", text)


class ExampleCorpusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.index = json.loads((ROOT / "examples" / "index.json").read_text(encoding="utf-8"))

    def test_seven_domains_have_one_public_candidate_each(self) -> None:
        cases = self.index["cases"]
        self.assertEqual(len(cases), 7)
        self.assertEqual(
            {case["domain"] for case in cases},
            {"coding", "research", "learning", "writing", "business", "product-design", "general-chat"},
        )
        for case in cases:
            self.assertTrue(case["synthetic"])
            self.assertEqual(case["license"], "MIT")
            self.assertEqual(case["publication_clearance"], "APPROVED_BY_PROJECT_OWNER")
            self.assertEqual(case["status"], "GOLD_CANDIDATE")
            self.assertEqual(case["human_verification"], "NOT_PERFORMED")

    def test_every_case_contains_the_five_review_artifacts(self) -> None:
        required = {"source.md", "handoff.md", "gold.json", "expected-receipt.md", "expected-next-action.md", "case.json"}
        for case in self.index["cases"]:
            case_dir = ROOT / "examples" / case["path"]
            self.assertEqual(required, {path.name for path in case_dir.iterdir() if path.is_file()})
            parsed = validate_markdown_bytes((case_dir / "handoff.md").read_bytes())
            self.assertEqual(parsed["metadata"]["coverage"], "PARTIAL")

    def test_corpus_covers_same_and_cross_language_semantics(self) -> None:
        directions = {(case["source_language"], case["receipt_language"]) for case in self.index["cases"]}
        self.assertEqual(len(directions), 7)
        self.assertTrue(any(source != target for source, target in directions))


class DeterministicProtocolTests(unittest.TestCase):
    def test_protocol_assets_and_vectors_are_integrity_locked(self) -> None:
        assets = protocol_assets()
        self.assertEqual(assets["protocol_version"]["status"], "IMPLEMENTED")
        self.assertEqual(len(verified_vectors()), 4)

    def test_canonical_json_is_stable_and_rejects_ambiguous_numbers(self) -> None:
        self.assertEqual(canonicalize({"b": 2, "a": 1}), b'{"a":1,"b":2}')
        with self.assertRaises(DuplicateKeyError):
            loads_strict('{"a":1,"a":2}')
        with self.assertRaises(UnsupportedNumberError):
            loads_strict('{"a":1.5}')

    def test_security_scan_detects_secret_bidi_and_active_content(self) -> None:
        sample = b"api_key=not-a-real-secret-value\n<script>x</script>\n" + "safe\u202epdf".encode("utf-8")
        categories = {finding["category"] for finding in scan_bytes(sample, object_id="fixture")}
        self.assertTrue({"secret", "active_content", "unicode_control"}.issubset(categories))


class LegacyConversionTests(unittest.TestCase):
    def setUp(self) -> None:
        safe_temp_root = Path("/private/tmp") if Path("/private/tmp").is_dir() else Path(tempfile.gettempdir()).resolve()
        self.temporary = tempfile.TemporaryDirectory(dir=safe_temp_root)
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def convert(self, fixture: str, format_name: str, output_name: str) -> dict[str, object]:
        return convert_legacy(
            ROOT / "tests" / "fixtures" / "legacy" / fixture,
            self.root / output_name,
            format_name=format_name,
            format_override=False,
            on_security_hit="REFUSE",
            created_at="2026-08-20T00:00:00Z",
            tenant_id="tenant.public.test",
            approve_original_transfer=False,
        )

    def test_three_legacy_importers_stay_partial_and_ineligible(self) -> None:
        cases = (
            ("handoff-v1.md", "handoff_markdown"),
            ("och-snapshot.md", "och_snapshot"),
            ("ltm-packet.json", "ltm_packet"),
        )
        for index, (fixture, format_name) in enumerate(cases):
            result = self.convert(fixture, format_name, f"output-{index}")
            self.assertTrue(result["ok"])
            self.assertEqual(result["claims"]["CONTENT_COVERAGE_CLAIM"], "PARTIAL")
            self.assertEqual(result["claims"]["CONTINUITY_EVAL_ELIGIBILITY_CLAIM"], "INELIGIBLE")
            self.assertEqual(result["original_transfer"], "NOT_APPROVED_EXCLUDED_FROM_OBJECT_MAP")

    def test_repeated_legacy_import_is_byte_stable(self) -> None:
        self.convert("ltm-packet.json", "ltm_packet", "first")
        self.convert("ltm-packet.json", "ltm_packet", "second")
        first = self.root / "first"
        second = self.root / "second"
        names = sorted(path.relative_to(first) for path in first.rglob("*") if path.is_file())
        self.assertEqual(names, sorted(path.relative_to(second) for path in second.rglob("*") if path.is_file()))
        for name in names:
            if name.as_posix() == "object-map.json":
                left = json.loads((first / name).read_text(encoding="utf-8"))
                right = json.loads((second / name).read_text(encoding="utf-8"))
                for value in (left, right):
                    for item in value["objects"]:
                        item["source_path"] = Path(item["source_path"]).name
                self.assertEqual(left, right)
            else:
                self.assertEqual((first / name).read_bytes(), (second / name).read_bytes())


if __name__ == "__main__":
    unittest.main()
