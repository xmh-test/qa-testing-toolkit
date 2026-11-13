"""Reference resolution in ordinary local folders and optional ACM content roots."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_contract_and_export import SKILLS, fixture
from check_case_links import check_links
from test_case_contract import ValidationError


class CaseLinkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.cases = self.root / "项目/模块/测试用例.json"
        self.cases.parent.mkdir(parents=True)
        self.document = fixture()
        self.write_document()

    def write_document(self):
        self.cases.write_text(json.dumps(self.document, ensure_ascii=False), encoding="utf-8")

    def material(self, name, content="材料正文"):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def test_explicit_paths_and_actual_summary(self):
        source = self.material("项目/需求.md")
        summary = self.material("项目/模块/模块_测试用例总结.md")
        self.document["metadata"].update(source="../需求.md", artifacts={"summary": "./模块_测试用例总结.md"})
        self.write_document()
        original = self.cases.read_bytes()
        links, warnings = check_links(self.cases, self.root, summary)
        self.assertEqual(links, {"source": source, "summary": summary})
        self.assertEqual(warnings, [])
        self.assertEqual(self.cases.read_bytes(), original)

    def test_bare_reference_and_root_legacy_paths(self):
        for name, reference in (("需求/需求.md", "需求/需求.md"),
                                ("项目/模块/需求.md", "需求.md")):
            with self.subTest(reference=reference):
                target = self.material(name)
                self.document["metadata"]["source"] = reference
                self.write_document()
                self.assertEqual(check_links(self.cases, self.root)[0]["source"], target)

    def test_ambiguous_reference_requires_explicit_path(self):
        self.material("需求.md")
        local = self.material("项目/模块/需求.md")
        self.document["metadata"]["source"] = "需求.md"
        self.write_document()
        with self.assertRaisesRegex(ValidationError, "歧义"):
            check_links(self.cases, self.root)
        self.document["metadata"]["source"] = "./需求.md"
        self.write_document()
        self.assertEqual(check_links(self.cases, self.root)[0]["source"], local)

    def test_null_summary_and_external_or_prose_source(self):
        for source in ("本次用户明确需求", "https://example.org/prd", "/private/prd.md", "C:\\docs\\prd.md"):
            with self.subTest(source=source):
                self.document["metadata"]["source"] = source
                self.write_document()
                links, warnings = check_links(self.cases, self.root)
                self.assertEqual(links, {})
                self.assertTrue(any("内容未捕获" in message for message in warnings))

    def test_missing_explicit_source_or_summary_is_error(self):
        for field in ("source", "summary"):
            with self.subTest(field=field):
                self.document = fixture()
                if field == "source":
                    self.document["metadata"]["source"] = "缺失需求.md"
                else:
                    self.document["metadata"]["artifacts"]["summary"] = "./缺失总结.md"
                self.write_document()
                with self.assertRaisesRegex(ValidationError, "不存在"):
                    check_links(self.cases, self.root)

    def test_actual_summary_must_match_metadata(self):
        first = self.material("项目/模块/总结.md")
        second = self.material("项目/模块/另一总结.md")
        with self.assertRaisesRegex(ValidationError, "null"):
            check_links(self.cases, self.root, first)
        self.document["metadata"]["artifacts"]["summary"] = "./总结.md"
        self.write_document()
        with self.assertRaisesRegex(ValidationError, "不一致"):
            check_links(self.cases, self.root, second)

    def test_unsafe_or_external_summary_is_error(self):
        for reference in ("../../../outside.md", "../../.git/config", "https://example.org/summary.md",
                          "/tmp/summary.md", "..\\summary.md"):
            with self.subTest(reference=reference):
                self.document["metadata"]["artifacts"]["summary"] = reference
                self.write_document()
                with self.assertRaises(ValidationError):
                    check_links(self.cases, self.root)

    def test_symlink_and_submodule_are_rejected(self):
        target = self.material("原始.md")
        link = self.cases.parent / "符号链接.md"
        link.symlink_to(target)
        submodule = self.cases.parent / "子模块"
        submodule.mkdir()
        (submodule / ".git").write_text("gitdir: ignored")
        (submodule / "需求.md").write_text("需求")
        for reference in ("./符号链接.md", "./子模块/需求.md"):
            with self.subTest(reference=reference):
                self.document["metadata"]["source"] = reference
                self.write_document()
                with self.assertRaises(ValidationError):
                    check_links(self.cases, self.root)

    def test_json_itself_must_be_inside_root_without_symlink(self):
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        with self.assertRaisesRegex(ValidationError, "根目录"):
            check_links(self.cases, unrelated)
        alias = self.root / "alias.json"
        alias.symlink_to(self.cases)
        with self.assertRaisesRegex(ValidationError, "符号链接"):
            check_links(alias, self.root)

    def test_non_text_reference_rejected(self):
        target = self.material("项目/模块/需求.md")
        self.document["metadata"]["source"] = "./需求.md"
        self.write_document()
        for content in (b"\xff\xfe", b"text\x00binary"):
            target.write_bytes(content)
            with self.assertRaises(ValueError):
                check_links(self.cases, self.root)

    def test_directory_is_not_treated_as_uncaptured_prose(self):
        (self.cases.parent / "需求目录").mkdir()
        self.document["metadata"]["source"] = "需求目录"
        self.write_document()
        with self.assertRaisesRegex(ValidationError, "必须是文件"):
            check_links(self.cases, self.root)

    def test_cli_and_existing_contract_do_not_require_git(self):
        script = SKILLS / "test-case-generator/scripts/check_case_links.py"
        result = subprocess.run([sys.executable, "-B", str(script), str(self.cases),
                                 "--root", str(self.root)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("内容未捕获", result.stdout)
        self.document["metadata"]["source"] = "missing.md"
        self.write_document()
        result = subprocess.run([sys.executable, "-B", str(script), str(self.cases),
                                 "--root", str(self.root)], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        contract = SKILLS / "test-case-generator/scripts/test_case_contract.py"
        result = subprocess.run([sys.executable, "-B", str(contract), str(self.cases)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
