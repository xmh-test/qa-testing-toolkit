#!/usr/bin/env python3
"""Validate V1/V2 test cases and explicitly requested BDD/DDT assets."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


V1_FIELDS = {
    "title", "directory", "tags", "priority", "case_type",
    "precondition", "steps", "expected", "functional_module",
}
V2_FIELDS = V1_FIELDS | {
    "case_id", "requirement_ids", "acceptance_criteria_ids",
    "functional_point_id", "design_methods", "bdd_scenario_id",
    "ddt_dataset_ids", "ddt_row_id",
}
METADATA_FIELDS = {
    "program", "module", "platform", "source", "generated_at",
    "generation_strategy", "artifacts",
}
STRATEGIES = {"functional-point", "auto-mixed", "functional-point+behavior-data"}
TAG_VALUES = {"web", "mobile", "desktop", "destructive"}
PLATFORM_TAGS = {"web", "mobile", "desktop"}
DESIGN_METHODS = {"functional-point", "bdd", "ddt"}
DDT_CLASSIFICATIONS = {
    "valid-equivalence", "invalid-equivalence", "boundary", "special", "combination",
}
PRIORITIES = {"P0", "P1", "P2"}
FP_RE = re.compile(r"^FP-\d{3,}$")
CASE_RE = re.compile(r"^TC-FP\d{3,}-\d{3,}$")
BDD_RE = re.compile(r"^BDD-FP\d{3,}-\d{3,}$")
DDT_RE = re.compile(r"^DDT-FP\d{3,}-\d{3,}$")
ROW_RE = re.compile(r"^ROW-DDT-FP\d{3,}-\d{3,}-\d{3,}$")
NUMBERED_LINE_RE = re.compile(r"^\s*\d+\.\s+", re.MULTILINE)


class ValidationError(Exception):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="校验 V1/V2 测试用例与显式要求的 BDD/DDT 资产")
    parser.add_argument("cases", help="测试用例 JSON")
    parser.add_argument("--feature", help="显式指定 BDD .feature 文件")
    parser.add_argument("--ddt", help="显式指定 DDT JSON 文件")
    parser.add_argument(
        "--all-linked", action="store_true",
        help="从 metadata.artifacts 读取并校验所有已声明 BDD/DDT 文件",
    )
    return parser.parse_args()


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"文件不存在：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"JSON 无法解析：{path}：{exc}") from exc


def require_string_list(value: Any, label: str, *, nonempty: bool = True) -> list[str]:
    if not isinstance(value, list) or (nonempty and not value):
        raise ValidationError(f"{label} 必须是{'非空' if nonempty else ''}字符串数组")
    if any(not isinstance(item, str) or not item for item in value):
        raise ValidationError(f"{label} 包含无效字符串")
    return value


def numbered_count(value: Any) -> int:
    return len(NUMBERED_LINE_RE.findall(value)) if isinstance(value, str) else 0


def is_atomic(case: dict[str, Any]) -> bool:
    return case.get("design_methods") == ["functional-point"]


def validate_common(case: dict[str, Any], label: str) -> None:
    tags = require_string_list(case.get("tags"), f"{label}.tags")
    if set(tags) - TAG_VALUES or not set(tags) & PLATFORM_TAGS:
        raise ValidationError(f"{label}.tags 不符合平台/破坏性白名单")
    if len(tags) != len(set(tags)) or ("destructive" in tags and tags[-1] != "destructive"):
        raise ValidationError(f"{label}.tags 重复或 destructive 顺序错误")
    if case.get("priority") not in PRIORITIES:
        raise ValidationError(f"{label}.priority 必须是 P0/P1/P2")
    directory = case.get("directory")
    if not isinstance(directory, str) or len(directory.split("|")) != 3:
        raise ValidationError(f"{label}.directory 必须是三段格式")
    if case.get("functional_module") != directory.split("|")[2]:
        raise ValidationError(f"{label}.functional_module 与 directory 模块不一致")
    for key in ("title", "case_type", "precondition", "steps", "expected"):
        if not isinstance(case.get(key), str) or not case[key].strip():
            raise ValidationError(f"{label}.{key} 必须是非空字符串")
    steps = numbered_count(case.get("steps"))
    expected = numbered_count(case.get("expected"))
    if steps == 0 or steps != expected:
        raise ValidationError(f"{label} 步骤与预期编号数量不一致：{steps}/{expected}")


def validate_v1(payload: list[Any]) -> tuple[list[dict[str, Any]], None]:
    cases: list[dict[str, Any]] = []
    for index, item in enumerate(payload, 1):
        if not isinstance(item, dict) or set(item) != V1_FIELDS:
            raise ValidationError(f"V1 第 {index} 条用例必须恰好包含 9 个字段")
        validate_common(item, f"V1[{index}]")
        cases.append(item)
    return cases, None


def validate_v2(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if payload.get("schema_version") != "2.0":
        raise ValidationError("V2 schema_version 必须是 2.0")
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict) or not METADATA_FIELDS <= set(metadata):
        raise ValidationError("V2 metadata 缺少必填字段")
    strategy = metadata.get("generation_strategy")
    if strategy not in STRATEGIES:
        raise ValidationError(f"不支持 generation_strategy：{strategy}")
    artifacts = metadata.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != {"summary", "bdd", "ddt"}:
        raise ValidationError("metadata.artifacts 必须恰好包含 summary/bdd/ddt")
    raw = payload.get("cases")
    if not isinstance(raw, list):
        raise ValidationError("V2 cases 必须是数组")

    cases: list[dict[str, Any]] = []
    case_ids: set[str] = set()
    for index, item in enumerate(raw, 1):
        label = f"V2.cases[{index}]"
        if not isinstance(item, dict) or set(item) != V2_FIELDS:
            raise ValidationError(f"{label} 必须恰好包含 17 个字段")
        validate_common(item, label)
        case_id = item.get("case_id")
        fp_id = item.get("functional_point_id")
        if not isinstance(case_id, str) or not CASE_RE.fullmatch(case_id):
            raise ValidationError(f"{label}.case_id 格式错误")
        if case_id in case_ids:
            raise ValidationError(f"case_id 重复：{case_id}")
        case_ids.add(case_id)
        if not isinstance(fp_id, str) or not FP_RE.fullmatch(fp_id):
            raise ValidationError(f"{label}.functional_point_id 格式错误")
        if not case_id.startswith(f"TC-{fp_id.replace('-', '')}-"):
            raise ValidationError(f"{label}.case_id 与 functional_point_id 不匹配")
        require_string_list(item.get("requirement_ids"), f"{label}.requirement_ids")
        require_string_list(item.get("acceptance_criteria_ids"), f"{label}.acceptance_criteria_ids")
        methods = require_string_list(item.get("design_methods"), f"{label}.design_methods")
        if set(methods) - DESIGN_METHODS or "functional-point" not in methods or len(methods) != len(set(methods)):
            raise ValidationError(f"{label}.design_methods 枚举、重复或基础方法错误")

        bdd_id = item.get("bdd_scenario_id")
        if "bdd" in methods:
            if not isinstance(bdd_id, str) or not BDD_RE.fullmatch(bdd_id):
                raise ValidationError(f"{label}.bdd_scenario_id 缺失或格式错误")
        elif bdd_id is not None:
            raise ValidationError(f"{label} 未使用 bdd 时 bdd_scenario_id 必须为 null")

        ddt_ids = require_string_list(
            item.get("ddt_dataset_ids"), f"{label}.ddt_dataset_ids", nonempty="ddt" in methods,
        )
        row_id = item.get("ddt_row_id")
        if "ddt" in methods:
            if any(not DDT_RE.fullmatch(value) for value in ddt_ids):
                raise ValidationError(f"{label}.ddt_dataset_ids 格式错误")
            if row_id is not None and (not isinstance(row_id, str) or not ROW_RE.fullmatch(row_id)):
                raise ValidationError(f"{label}.ddt_row_id 格式错误")
            if strategy == "functional-point+behavior-data" and row_id is not None:
                raise ValidationError(f"{label} 新 DDT 模板的 ddt_row_id 必须为 null")
        elif ddt_ids or row_id is not None:
            raise ValidationError(f"{label} 未使用 ddt 时 DDT 关联字段必须为空")
        cases.append(item)
    return cases, metadata


def artifact_path(base: Path, value: Any, label: str) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValidationError(f"{label} 必须是非空路径或 null")
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base / path).resolve()


def validate_coverage(
    full: set[str], partial: set[str], case_map: dict[str, dict[str, Any]], label: str,
) -> None:
    conflict = full & partial
    if conflict:
        raise ValidationError(f"{label} full/partial 冲突：{sorted(conflict)}")
    unknown = (full | partial) - set(case_map)
    if unknown:
        raise ValidationError(f"{label} 引用未知 case_id：{sorted(unknown)}")
    invalid = {case_id for case_id in full | partial if not is_atomic(case_map[case_id])}
    if invalid:
        raise ValidationError(f"{label} 覆盖关系指向非原子用例：{sorted(invalid)}")


def validate_feature(
    path: Path, cases: list[dict[str, Any]], strategy: str,
) -> dict[str, dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValidationError(f"BDD 文件不存在：{path}") from exc
    if not re.search(r"^\s*Feature:\s+.+", text, re.MULTILINE):
        raise ValidationError("BDD 文件缺少 Feature")
    scenario_re = re.compile(
        r"(?P<tags>(?:^\s*@[^\n]+\n)+)^\s*(?P<kind>Scenario(?: Outline)?):\s+.+",
        re.MULTILINE,
    )
    starts = list(scenario_re.finditer(text))
    if not starts:
        raise ValidationError("BDD 文件缺少带追溯标签的 Scenario/Scenario Outline")
    case_map = {case["case_id"]: case for case in cases}
    scenarios: dict[str, dict[str, Any]] = {}
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        block = text[match.start():end]
        tags = set(re.findall(r"@([^\s]+)", match.group("tags")))
        bdd_ids = {tag for tag in tags if BDD_RE.fullmatch(tag)}
        tc_ids = {tag for tag in tags if CASE_RE.fullmatch(tag)}
        if len(bdd_ids) != 1 or not tc_ids:
            raise ValidationError("每个 BDD 场景必须含唯一 BDD ID 和至少一个 TC ID")
        bdd_id = next(iter(bdd_ids))
        if bdd_id in scenarios:
            raise ValidationError(f"BDD 场景 ID 重复：{bdd_id}")
        for keyword in ("Given", "When", "Then"):
            if not re.search(rf"^\s*{keyword}\s+.+", block, re.MULTILINE):
                raise ValidationError(f"{bdd_id} 缺少 {keyword}")
        kind = match.group("kind")
        examples: dict[str, dict[str, str]] = {}
        if kind == "Scenario Outline" and not re.search(r"^\s*Examples:\s*$", block, re.MULTILINE):
            raise ValidationError(f"{bdd_id} Scenario Outline 缺少 Examples")
        if kind == "Scenario Outline":
            examples_match = re.search(r"^\s*Examples:\s*$([\s\S]*)", block, re.MULTILINE)
            table_lines = re.findall(r"^\s*\|(.+)\|\s*$", examples_match.group(1), re.MULTILINE)
            if len(table_lines) < 2:
                raise ValidationError(f"{bdd_id} Examples 必须包含表头和至少一行数据")
            table = [[cell.strip() for cell in line.split("|")] for line in table_lines]
            headers = table[0]
            if "row_id" not in headers or len(headers) != len(set(headers)):
                raise ValidationError(f"{bdd_id} Examples 缺少唯一 row_id 列")
            for values in table[1:]:
                if len(values) != len(headers):
                    raise ValidationError(f"{bdd_id} Examples 行列数不一致")
                row = dict(zip(headers, values))
                row_id = row["row_id"]
                if not ROW_RE.fullmatch(row_id) or row_id in examples:
                    raise ValidationError(f"{bdd_id} Examples row_id 无效或重复：{row_id}")
                examples[row_id] = row
        full = {tag.removeprefix("covers-full-") for tag in tags if tag.startswith("covers-full-")}
        partial = {tag.removeprefix("covers-partial-") for tag in tags if tag.startswith("covers-partial-")}
        validate_coverage(full, partial, case_map, bdd_id)
        scenarios[bdd_id] = {
            "kind": kind, "tc_ids": tc_ids, "block": block,
            "coverage": (full, partial), "examples": examples,
        }

    bdd_cases = [case for case in cases if "bdd" in case["design_methods"]]
    declared = set(scenarios)
    referenced = {case["bdd_scenario_id"] for case in bdd_cases}
    if declared != referenced:
        raise ValidationError("BDD 场景存在孤立或缺失引用")
    for bdd_id, scenario in scenarios.items():
        mapped = [case for case in bdd_cases if case["bdd_scenario_id"] == bdd_id]
        if strategy == "functional-point+behavior-data" and len(mapped) != 1:
            raise ValidationError(f"新模型要求 {bdd_id} 只对应一条 JSON 模板用例")
        mapped_ids = {case["case_id"] for case in mapped}
        if scenario["tc_ids"] != mapped_ids:
            raise ValidationError(f"{bdd_id} 的 TC 标签与 JSON 映射不一致")
        if any("ddt" in case["design_methods"] for case in mapped):
            if scenario["kind"] != "Scenario Outline":
                raise ValidationError(f"BDD+DDT 场景必须使用 Scenario Outline：{bdd_id}")
            if strategy == "auto-mixed":
                for case in mapped:
                    if case.get("ddt_row_id") and case["ddt_row_id"] not in scenario["block"]:
                        raise ValidationError(f"{bdd_id} Examples 缺少 {case['ddt_row_id']}")
    return scenarios


def validate_ddt_v1(payload: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    datasets = payload.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise ValidationError("DDT V1 datasets 必须是非空数组")
    known = {case["case_id"]: case for case in cases}
    dataset_ids: set[str] = set()
    row_ids: set[str] = set()
    mapped_case_ids: set[str] = set()
    for dataset in datasets:
        if not isinstance(dataset, dict):
            raise ValidationError("DDT V1 dataset 必须是对象")
        dataset_id = dataset.get("dataset_id")
        if not isinstance(dataset_id, str) or not DDT_RE.fullmatch(dataset_id) or dataset_id in dataset_ids:
            raise ValidationError(f"DDT dataset_id 无效或重复：{dataset_id}")
        dataset_ids.add(dataset_id)
        if not isinstance(dataset.get("parameters"), list) or not dataset["parameters"]:
            raise ValidationError(f"{dataset_id}.parameters 必须是非空数组")
        if not isinstance(dataset.get("rows"), list) or not dataset["rows"]:
            raise ValidationError(f"{dataset_id}.rows 必须是非空数组")
        for row in dataset["rows"]:
            if not isinstance(row, dict):
                raise ValidationError(f"{dataset_id} 包含非对象 row")
            row_id = row.get("row_id")
            case_id = row.get("case_id")
            if not isinstance(row_id, str) or not ROW_RE.fullmatch(row_id) or row_id in row_ids:
                raise ValidationError(f"DDT row_id 无效或重复：{row_id}")
            if case_id not in known:
                raise ValidationError(f"{row_id} 引用未知 case_id：{case_id}")
            classes = require_string_list(row.get("classifications"), f"{row_id}.classifications")
            if set(classes) - DDT_CLASSIFICATIONS:
                raise ValidationError(f"{row_id}.classifications 含非法值")
            if not isinstance(row.get("values"), dict) or not row["values"]:
                raise ValidationError(f"{row_id}.values 必须是非空对象")
            if not isinstance(row.get("expected"), str) or not row["expected"].strip():
                raise ValidationError(f"{row_id}.expected 缺失")
            if row.get("priority") not in PRIORITIES:
                raise ValidationError(f"{row_id}.priority 无效")
            case = known[case_id]
            if (
                "ddt" not in case.get("design_methods", [])
                or dataset_id not in case.get("ddt_dataset_ids", [])
                or case.get("ddt_row_id") != row_id
            ):
                raise ValidationError(f"{row_id} 与旧版 JSON 展开用例映射不一致")
            row_ids.add(row_id)
            mapped_case_ids.add(case_id)
    ddt_cases = [case for case in cases if "ddt" in case.get("design_methods", [])]
    if {case["case_id"] for case in ddt_cases} != mapped_case_ids:
        raise ValidationError("旧 DDT 文件与 JSON 展开用例存在孤立引用")
    return {"schema": "1.0", "coverage": {}}


def validate_ddt_v2(payload: dict[str, Any], cases: list[dict[str, Any]]) -> dict[str, Any]:
    datasets = payload.get("datasets")
    if not isinstance(datasets, list) or not datasets:
        raise ValidationError("DDT V2 datasets 必须是非空数组")
    case_map = {case["case_id"]: case for case in cases}
    dataset_ids: set[str] = set()
    row_ids: set[str] = set()
    template_ids: set[str] = set()
    coverage_by_dataset: dict[str, tuple[set[str], set[str]]] = {}
    bdd_by_dataset: dict[str, str | None] = {}
    rows_by_dataset: dict[str, dict[str, dict[str, Any]]] = {}
    for dataset in datasets:
        if not isinstance(dataset, dict):
            raise ValidationError("DDT V2 dataset 必须是对象")
        dataset_id = dataset.get("dataset_id")
        if not isinstance(dataset_id, str) or not DDT_RE.fullmatch(dataset_id) or dataset_id in dataset_ids:
            raise ValidationError(f"DDT dataset_id 无效或重复：{dataset_id}")
        dataset_ids.add(dataset_id)
        case_id = dataset.get("case_id")
        if case_id not in case_map or case_id in template_ids:
            raise ValidationError(f"{dataset_id}.case_id 未知或被多个 dataset 共用：{case_id}")
        template = case_map[case_id]
        template_ids.add(case_id)
        if "ddt" not in template["design_methods"] or dataset_id not in template["ddt_dataset_ids"]:
            raise ValidationError(f"{dataset_id} 未关联正确的 JSON DDT 模板")
        if template.get("ddt_row_id") is not None:
            raise ValidationError(f"{dataset_id} 的新模板 ddt_row_id 必须为 null")
        if dataset.get("functional_point_id") != template["functional_point_id"]:
            raise ValidationError(f"{dataset_id}.functional_point_id 与模板不一致")
        for key in ("requirement_ids", "acceptance_criteria_ids"):
            require_string_list(dataset.get(key), f"{dataset_id}.{key}")
        bdd_id = dataset.get("bdd_scenario_id")
        if bdd_id != template.get("bdd_scenario_id"):
            raise ValidationError(f"{dataset_id}.bdd_scenario_id 与模板不一致")
        if bdd_id is not None and not BDD_RE.fullmatch(str(bdd_id)):
            raise ValidationError(f"{dataset_id}.bdd_scenario_id 格式错误")
        bdd_by_dataset[dataset_id] = bdd_id

        coverage = dataset.get("coverage")
        if not isinstance(coverage, dict):
            raise ValidationError(f"{dataset_id}.coverage 缺失")
        full = set(require_string_list(coverage.get("full_case_ids"), f"{dataset_id}.coverage.full_case_ids", nonempty=False))
        partial = set(require_string_list(coverage.get("partial_case_ids"), f"{dataset_id}.coverage.partial_case_ids", nonempty=False))
        if coverage.get("execution_policy") != "ddt-only-for-full":
            raise ValidationError(f"{dataset_id}.coverage.execution_policy 必须是 ddt-only-for-full")
        validate_coverage(full, partial, case_map, dataset_id)
        coverage_by_dataset[dataset_id] = (full, partial)

        parameters = dataset.get("parameters")
        rows = dataset.get("rows")
        if not isinstance(parameters, list) or not parameters:
            raise ValidationError(f"{dataset_id}.parameters 必须是非空数组")
        names = {item.get("name") for item in parameters if isinstance(item, dict)}
        if len(names) != len(parameters) or None in names or "" in names:
            raise ValidationError(f"{dataset_id}.parameters 名称无效或重复")
        for parameter in parameters:
            classes = parameter.get("classes")
            if (
                not isinstance(parameter.get("type"), str)
                or not isinstance(parameter.get("required"), bool)
                or not isinstance(classes, list)
                or any(item not in DDT_CLASSIFICATIONS for item in classes)
            ):
                raise ValidationError(f"{dataset_id}.parameters 定义不完整或分类非法")
        if not isinstance(rows, list) or not rows:
            raise ValidationError(f"{dataset_id}.rows 必须是非空数组")
        dataset_rows: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise ValidationError(f"{dataset_id} 包含非对象 row")
            row_id = row.get("row_id")
            if not isinstance(row_id, str) or not ROW_RE.fullmatch(row_id) or row_id in row_ids:
                raise ValidationError(f"DDT row_id 无效或重复：{row_id}")
            row_ids.add(row_id)
            classes = require_string_list(row.get("classifications"), f"{row_id}.classifications")
            if set(classes) - DDT_CLASSIFICATIONS:
                raise ValidationError(f"{row_id}.classifications 含非法值")
            values = row.get("values")
            if not isinstance(values, dict) or not values or set(values) - names:
                raise ValidationError(f"{row_id}.values 缺失或包含未知参数")
            if not isinstance(row.get("expected"), str) or not row["expected"].strip():
                raise ValidationError(f"{row_id}.expected 缺失")
            if row.get("priority") not in PRIORITIES:
                raise ValidationError(f"{row_id}.priority 无效")
            if "case_id" in row:
                raise ValidationError(f"{row_id} 为 V2 row，不应再包含 case_id")
            dataset_rows[row_id] = row
        rows_by_dataset[dataset_id] = dataset_rows

    ddt_cases = [case for case in cases if "ddt" in case["design_methods"]]
    referenced = {dataset_id for case in ddt_cases for dataset_id in case["ddt_dataset_ids"]}
    if referenced != dataset_ids:
        raise ValidationError("DDT 文件存在孤立 dataset 或 JSON 引用缺失")
    if {case["case_id"] for case in ddt_cases} != template_ids:
        raise ValidationError("每条 JSON DDT 模板必须且只能对应一个 dataset")
    return {
        "schema": "2.0",
        "coverage": coverage_by_dataset,
        "bdd": bdd_by_dataset,
        "rows": rows_by_dataset,
    }


def validate_ddt(path: Path, cases: list[dict[str, Any]]) -> dict[str, Any]:
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValidationError("DDT JSON 根节点必须是对象")
    version = payload.get("schema_version")
    if version == "1.0":
        return validate_ddt_v1(payload, cases)
    if version == "2.0":
        return validate_ddt_v2(payload, cases)
    raise ValidationError(f"不支持的 DDT schema_version：{version}")


def main() -> int:
    args = parse_args()
    cases_path = Path(args.cases).expanduser().resolve()
    feature_path: Path | None = None
    ddt_path: Path | None = None
    try:
        payload = read_json(cases_path)
        if isinstance(payload, list):
            cases, metadata = validate_v1(payload)
            version, strategy = "V1", "legacy"
        elif isinstance(payload, dict):
            cases, metadata = validate_v2(payload)
            version, strategy = "V2", metadata["generation_strategy"]
        else:
            raise ValidationError("测试用例 JSON 根节点必须是数组或对象")

        if metadata is None and (args.feature or args.ddt or args.all_linked):
            raise ValidationError("V1 不支持 BDD/DDT 跨文件专项校验")

        if metadata is not None:
            if args.feature:
                feature_path = artifact_path(cases_path.parent, args.feature, "--feature")
            elif args.all_linked:
                feature_path = artifact_path(cases_path.parent, metadata["artifacts"].get("bdd"), "metadata.artifacts.bdd")
            if args.ddt:
                ddt_path = artifact_path(cases_path.parent, args.ddt, "--ddt")
            elif args.all_linked:
                ddt_path = artifact_path(cases_path.parent, metadata["artifacts"].get("ddt"), "metadata.artifacts.ddt")
            if args.all_linked:
                has_bdd = any("bdd" in case["design_methods"] for case in cases)
                has_ddt = any("ddt" in case["design_methods"] for case in cases)
                if has_bdd != (feature_path is not None):
                    raise ValidationError("BDD 用例与 metadata.artifacts.bdd 声明不一致")
                if has_ddt != (ddt_path is not None):
                    raise ValidationError("DDT 用例与 metadata.artifacts.ddt 声明不一致")

        feature_info: dict[str, dict[str, Any]] = {}
        ddt_info: dict[str, Any] = {}
        if feature_path is not None:
            feature_info = validate_feature(feature_path, cases, strategy)
        if ddt_path is not None:
            ddt_info = validate_ddt(ddt_path, cases)
        if feature_info and ddt_info.get("schema") == "2.0":
            for dataset_id, bdd_id in ddt_info["bdd"].items():
                if bdd_id is None:
                    continue
                scenario = feature_info.get(bdd_id)
                if scenario is None:
                    raise ValidationError(f"{dataset_id} 引用 Feature 中不存在的场景：{bdd_id}")
                if scenario["coverage"] != ddt_info["coverage"][dataset_id]:
                    raise ValidationError(f"{bdd_id} 与 {dataset_id} 的 full/partial 覆盖关系不一致")
                examples = scenario["examples"]
                ddt_rows = ddt_info["rows"][dataset_id]
                if set(examples) != set(ddt_rows):
                    raise ValidationError(f"{bdd_id} Examples 与 {dataset_id} rows 的 row_id 不一致")
                for row_id, ddt_row in ddt_rows.items():
                    example = examples[row_id]
                    if example.get("expected") != str(ddt_row["expected"]):
                        raise ValidationError(f"{row_id} 的 Examples expected 与 DDT expected 不一致")
                    for key, value in ddt_row["values"].items():
                        if example.get(key) != str(value):
                            raise ValidationError(f"{row_id} 的 Examples 参数 {key} 与 DDT values 不一致")
    except ValidationError as exc:
        print(f"校验失败：{exc}", file=sys.stderr)
        return 1

    scopes = ["常规"]
    if feature_path is not None:
        scopes.append("BDD")
    if ddt_path is not None:
        scopes.append("DDT")
    print(f"校验通过：{version}，{len(cases)} 条用例，范围：{'+'.join(scopes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
