"""Behavioral regression tests; fixtures are synthetic and confined to temp dirs."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.dont_write_bytecode = True
SKILLS = Path(__file__).resolve().parents[1] / "plugins/qa-testing-toolkit/skills"
sys.path.insert(0, str(SKILLS / "test-case-generator/scripts"))
from test_case_contract import ValidationError, validate, load_document, validate_summary

EXPORT = SKILLS / "test-case-to-sheets/scripts/json_test_cases_to_excel.py"
spec = importlib.util.spec_from_file_location("exporter", EXPORT)
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


def fixture():
    return {
        "schema_version": "3.0",
        "metadata": {
            "program": "示例", "module": "文件备份", "platform": "web",
            "source": "合成需求", "generated_at": "2026-10-20 10:00:00",
            "artifacts": {"summary": None},
        },
        "cases": [{
            "case_id": "TC-FP001-001", "functional_point_id": "FP-001",
            "requirement_ids": ["REQ-001"], "acceptance_criteria_ids": ["AC-001"],
            "title": "【新建与编辑】【已填写配置】点击取消，返回列表且不创建任务",
            "directory": "示例|web|文件备份", "functional_module": "文件备份",
            "tags": ["web"], "priority": "P1", "case_type": "功能用例",
            "precondition": "1. 已登录并打开新建页面\n2. 本用例数据已隔离",
            "steps": "1. 输入任务名称「备份😀」\n2. 点击取消",
            "expected": "1. 名称显示为「备份😀」\n2. 返回列表且无新增任务",
        }],
    }


def legacy():
    doc = fixture()
    doc["schema_version"] = "2.0"
    doc["metadata"]["generation_strategy"] = "functional-point"
    doc["metadata"]["artifacts"].update(bdd=None, ddt=None)
    doc["cases"][0].update(
        design_methods=["functional-point"], bdd_scenario_id=None,
        ddt_dataset_ids=[], ddt_row_id=None,
    )
    return doc


class ContractTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate(fixture())[1], "3.0")

    def test_titles_rejected(self):
        for title in ("[模块][条件]测试正常", "【新建/取消】【条件】取消，返回",
                      "【新建】【条件】创建任务", "【 】【条件】操作，结果"):
            with self.subTest(title=title), self.assertRaises(ValidationError):
                doc = fixture()
                doc["cases"][0]["title"] = title
                validate(doc)

    def test_numbering_rejected(self):
        for field, value in (
            ("steps", "2. 点击\n4. 提交"),
            ("expected", "7. 显示\n9. 成功"),
            ("steps", "1. 点击\n1. 提交"),
            ("expected", "1. 显示"),
            ("precondition", "已登录"),
            ("steps", "1. 点击\n未编号内容"),
        ):
            with self.subTest(field=field, value=value), self.assertRaises(ValidationError):
                doc = fixture()
                doc["cases"][0][field] = value
                validate(doc)

    def test_invalid_structure(self):
        for key, value in (("priority", "P3"), ("tags", ["web", "web"]),
                           ("directory", "示例|app|文件备份"),
                           ("case_id", "TC-FP002-001"), ("requirement_ids", [])):
            with self.subTest(key=key), self.assertRaises(ValidationError):
                doc = fixture()
                doc["cases"][0][key] = value
                validate(doc)
        for change in ("duplicate", "empty", "extra"):
            with self.subTest(change=change), self.assertRaises(ValidationError):
                doc = fixture()
                if change == "duplicate":
                    doc["cases"].append(copy.deepcopy(doc["cases"][0]))
                elif change == "empty":
                    doc["cases"] = []
                else:
                    doc["cases"][0]["unknown"] = True
                validate(doc)

    def test_legacy_and_mixed(self):
        doc = legacy()
        doc["cases"][0]["title"] = "[旧模块][旧条件]取消后不创建"
        self.assertTrue(validate(doc)[2])
        for kind in ("strategy", "reference", "case"):
            with self.subTest(kind=kind), self.assertRaises(ValidationError):
                doc = legacy()
                if kind == "strategy":
                    doc["metadata"]["generation_strategy"] = "auto-mixed"
                elif kind == "reference":
                    doc["metadata"]["artifacts"]["bdd"] = "old.feature"
                else:
                    doc["cases"][0]["design_methods"].append("bdd")
                validate(doc)

    def test_v1(self):
        doc = fixture()["cases"]
        for key in ("case_id", "functional_point_id", "requirement_ids", "acceptance_criteria_ids"):
            doc[0].pop(key)
        self.assertEqual(validate(doc)[1], "1.0")

    def test_api_and_risk_priority(self):
        doc = fixture()
        doc["metadata"]["platform"] = "api"
        doc["cases"][0].update(tags=["api"], directory="示例|api|文件备份",
                               priority="P0", case_type="安全用例")
        validate(doc)

    def test_duplicate_json_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "duplicate.json"
            path.write_text('{"cases": [], "cases": []}', encoding="utf-8")
            with self.assertRaises(ValidationError):
                load_document(path)

    def test_summary_structure_and_counts(self):
        template = (SKILLS / "test-case-generator/references/test_case_template.md").read_text()
        valid = (template.replace("| 用例总数 | |", "| 用例总数 | 1 |")
                 .replace("| 最终用例数 | |", "| 最终用例数 | 1 |")
                 .replace("| P0 / P1 / P2 | |", "| P0 / P1 / P2 | 0 / 1 / 0 |"))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.md"
            path.write_text(valid, encoding="utf-8")
            validate_summary(path, fixture()["cases"])
            for broken in (
                valid.replace("| 用例总数 | 1 |", "| 用例总数 | 2 |"),
                valid.replace("## 需求缺口", "## 待确认项"),
                valid.replace("| 指标 | 值 |", "| 名称 | 数量 |"),
                valid.replace("0 / 1 / 0", "1 / 0 / 0"),
            ):
                path.write_text(broken, encoding="utf-8")
                with self.assertRaises(ValidationError):
                    validate_summary(path, fixture()["cases"])


class ExportTests(unittest.TestCase):
    def run_export(self, doc):
        with tempfile.TemporaryDirectory() as tmp:
            source, target = Path(tmp) / "cases.json", Path(tmp) / "cases.xlsx"
            source.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
            original = source.read_bytes()
            result = subprocess.run([sys.executable, str(EXPORT), str(source)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            cases, version, _ = validate(doc)
            exporter.verify_xlsx(target, cases, version != "1.0")
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(sorted(p.name for p in Path(tmp).iterdir()), ["cases.json", "cases.xlsx"])
            with zipfile.ZipFile(target) as z:
                root = ET.fromstring(z.read("xl/worksheets/sheet1.xml"))
                ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                self.assertEqual(len(root.findall("s:sheetData/s:row", ns)), len(cases) + 1)
                self.assertIn("备份😀", "".join(root.itertext()))

    def test_v3_and_v2_roundtrip(self):
        for doc in (fixture(), legacy()):
            self.run_export(doc)

    def test_v1_roundtrip(self):
        doc = fixture()["cases"]
        for key in ("case_id", "functional_point_id", "requirement_ids", "acceptance_criteria_ids"):
            doc[0].pop(key)
        self.run_export(doc)

    def test_windows_newlines_and_special_characters(self):
        doc = fixture()
        doc["cases"][0]["expected"] = doc["cases"][0]["expected"].replace("\n", "\r\n") + '，保留 & < > "'
        self.run_export(doc)

    def test_failures_preserve_existing_file(self):
        for kind in ("title", "mixed", "xml", "oversize"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as tmp:
                source, target = Path(tmp) / "cases.json", Path(tmp) / "cases.xlsx"
                doc = legacy() if kind == "mixed" else fixture()
                if kind == "title":
                    doc["cases"][0]["title"] = "坏标题"
                elif kind == "mixed":
                    doc["cases"][0]["design_methods"].append("ddt")
                elif kind == "xml":
                    doc["cases"][0]["expected"] += "\x01"
                else:
                    doc["cases"][0]["expected"] += "长" * 32768
                source.write_text(json.dumps(doc), encoding="utf-8")
                target.write_bytes(b"existing workbook")
                result = subprocess.run([sys.executable, str(EXPORT), str(source)],
                                        capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(target.read_bytes(), b"existing workbook")
                self.assertEqual(len(list(Path(tmp).iterdir())), 2)

    def test_never_overwrite_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cases.json"
            path.write_text(json.dumps(fixture()), encoding="utf-8")
            original = path.read_bytes()
            result = subprocess.run([sys.executable, str(EXPORT), str(path), "-o", str(path)],
                                    capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
