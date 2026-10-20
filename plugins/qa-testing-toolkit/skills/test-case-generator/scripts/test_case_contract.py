#!/usr/bin/env python3
"""Shared, read-only contract validation for test-case generation and export."""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE_FIELDS = {
    "title", "directory", "tags", "priority", "case_type",
    "precondition", "steps", "expected", "functional_module",
}
TRACE_FIELDS = {
    "case_id", "requirement_ids", "acceptance_criteria_ids", "functional_point_id",
}
CASE_FIELDS = BASE_FIELDS | TRACE_FIELDS
LEGACY_FIELDS = {"design_methods", "bdd_scenario_id", "ddt_dataset_ids", "ddt_row_id"}
META_FIELDS = {"program", "module", "platform", "source", "generated_at", "artifacts"}
PLATFORMS = {"web": "web", "mobile": "app", "desktop": "pc", "api": "api"}
CASE_TYPES = {"功能用例", "移动端用例", "兼容性用例", "性能用例", "安全用例", "接口用例"}
TITLE_RE = re.compile(r"^【([^【】\[\]/\n]+)】【([^【】\[\]/\n]+)】([^【】\n]+)，([^【】\n]+)$")


class ValidationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def text(value, label: str) -> str:
    require(isinstance(value, str) and bool(value.strip()), f"{label} 必须是非空字符串")
    return value


def strings(value, label: str) -> list[str]:
    require(isinstance(value, list) and bool(value), f"{label} 必须是非空字符串数组")
    for item in value:
        text(item, label)
    require(len(value) == len(set(value)), f"{label} 不得重复")
    return value


def numbered(value, label: str) -> int:
    lines = text(value, label).splitlines()
    for number, line in enumerate(lines, 1):
        match = re.fullmatch(r"(\d+)\.\s+(\S.*)", line.strip())
        require(match is not None and int(match[1]) == number,
                f"{label} 必须从 1 连续编号且每行非空，第 {number} 行错误")
    return len(lines)


def no_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, f"JSON 存在重复字段：{key}")
        result[key] = value
    return result


def validate(payload) -> tuple[list[dict], str, list[str]]:
    warnings = []
    if isinstance(payload, list):
        version, cases, metadata = "1.0", payload, None
    else:
        require(isinstance(payload, dict), "根节点必须为对象或 V1 数组")
        require(set(payload) == {"schema_version", "metadata", "cases"}, "根对象字段不符合协议")
        version = payload["schema_version"]
        require(version in ("2.0", "3.0"), "不支持的 schema_version")
        metadata, cases = payload["metadata"], payload["cases"]
        require(isinstance(metadata, dict) and META_FIELDS <= set(metadata), "metadata 缺少必填字段")
        for key in META_FIELDS - {"artifacts"}:
            text(metadata[key], f"metadata.{key}")
        artifacts = metadata["artifacts"]
        require(isinstance(artifacts, dict), "metadata.artifacts 必须是对象")
        if version == "3.0":
            require(set(metadata) <= META_FIELDS | {"updated_at", "change_source"}, "metadata 含未知字段")
            require(set(artifacts) == {"summary"}, "artifacts 仅允许 summary")
            for key in ("generated_at", "updated_at"):
                if key in metadata:
                    value = text(metadata[key], key)
                    require(re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value) is not None,
                            f"{key} 时间格式错误")
                    try:
                        datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
                    except ValueError as exc:
                        raise ValidationError(f"{key} 日期无效") from exc
            if "change_source" in metadata:
                text(metadata["change_source"], "change_source")
            platform_list = metadata["platform"].split("|")
            require(set(platform_list) <= set(PLATFORMS) and len(platform_list) == len(set(platform_list)),
                    "metadata.platform 无效")
        else:
            require(set(metadata) <= META_FIELDS | {"generation_strategy", "updated_at", "change_source"},
                    "旧版 metadata 含未知字段，停止以避免丢失内容")
            require(metadata.get("generation_strategy") == "functional-point",
                    "仅支持旧版纯常规用例；混合资产请保留原文件并另行处理")
            require(set(artifacts) == {"summary", "bdd", "ddt"}
                    and artifacts["bdd"] is None and artifacts["ddt"] is None,
                    "旧版仍包含专项引用，不能自动转换")
        require(artifacts["summary"] is None or
                isinstance(artifacts["summary"], str) and bool(artifacts["summary"].strip()),
                "summary 必须是非空路径或 null")

    require(isinstance(cases, list) and bool(cases), "cases 必须是非空数组")
    ids, titles, seen_platforms = set(), set(), set()
    expected_fields = BASE_FIELDS if version == "1.0" else CASE_FIELDS
    if version == "2.0":
        expected_fields = CASE_FIELDS | LEGACY_FIELDS
    for index, case in enumerate(cases, 1):
        label = f"cases[{index}]"
        require(isinstance(case, dict) and set(case) == expected_fields,
                f"{label} 字段必须恰好为 {len(expected_fields)} 个规定字段")
        for key in BASE_FIELDS - {"tags"}:
            text(case[key], f"{label}.{key}")
        tags = strings(case["tags"], f"{label}.tags")
        platform_tags = set(tags) - {"destructive"}
        require(bool(platform_tags) and platform_tags <= set(PLATFORMS), f"{label} 平台 tag 无效")
        require("destructive" not in tags or tags[-1] == "destructive", f"{label} destructive 必须放末尾")
        seen_platforms.update(platform_tags)
        require(case["priority"] in ("P0", "P1", "P2"), f"{label} 优先级无效")
        parts = case["directory"].split("|")
        require(len(parts) == 3 and all(p.strip() for p in parts), f"{label} directory 必须是非空三段")
        require(case["functional_module"] == parts[2], f"{label} 模块与目录不一致")
        if version == "3.0":
            directory_platform = "all" if len(platform_tags) > 1 else PLATFORMS[next(iter(platform_tags))]
            require(parts[1] == directory_platform, f"{label} 目录平台与 tags 不一致")
            require(parts[0] == metadata["program"] and parts[2] == metadata["module"],
                    f"{label} 项目/模块与 metadata 不一致")
            require(set(case["case_type"].split("|")) <= CASE_TYPES, f"{label} case_type 无效")
            numbered(case["precondition"], f"{label}.precondition")
        require(numbered(case["steps"], f"{label}.steps") ==
                numbered(case["expected"], f"{label}.expected"), f"{label} 步骤与预期数量不一致")
        title = case["title"]
        match = TITLE_RE.fullmatch(title)
        title_ok = match is not None and all(part.strip() for part in match.groups())
        if version == "3.0":
            require(title_ok, f"{label} 标题必须为【功能分类】【场景摘要】核心操作，预期结果")
        elif not title_ok:
            warnings.append(f"{label} 旧版标题未采用新规范；原内容保持")
        if not 20 <= len(title) <= 60:
            warnings.append(f"{label} 标题长度建议 20～60 字，请人工判断可读性")
        if title in titles:
            warnings.append(f"{label} 标题重复，请检查是否为重复用例或缺少区分条件")
        titles.add(title)
        if version != "1.0":
            case_id = text(case["case_id"], f"{label}.case_id")
            fp = text(case["functional_point_id"], f"{label}.functional_point_id")
            require(re.fullmatch(r"FP-\d{3,}", fp) is not None, f"{label} FP 格式错误")
            require(re.fullmatch(re.escape(f"TC-{fp.replace('-', '')}-") + r"\d{3,}", case_id) is not None,
                    f"{label} ID 格式错误或与 FP 不对应")
            require(case_id not in ids, f"{label} case_id 重复")
            ids.add(case_id)
            strings(case["requirement_ids"], f"{label}.requirement_ids")
            strings(case["acceptance_criteria_ids"], f"{label}.acceptance_criteria_ids")
        if version == "2.0":
            require(case["design_methods"] == ["functional-point"] and case["bdd_scenario_id"] is None
                    and case["ddt_dataset_ids"] == [] and case["ddt_row_id"] is None,
                    f"{label} 不是纯常规用例，停止以避免丢失专项内容")
    if version == "3.0":
        require(seen_platforms <= set(metadata["platform"].split("|")), "用例平台超出 metadata.platform")
    if version != "3.0":
        warnings.insert(0, f"读取历史 V{version}；未修改输入，更新时请另存 V3")
    return cases, version, warnings


def load_document(path: Path) -> tuple[list[dict], str, list[str]]:
    with path.open(encoding="utf-8") as stream:
        return validate(json.load(stream, object_pairs_hook=no_duplicate_keys))


def validate_summary(path: Path, cases: list[dict]) -> None:
    """Check the default summary structure and final counts, not semantic coverage."""
    summary = path.read_text(encoding="utf-8")
    template = (Path(__file__).resolve().parents[1] / "references/test_case_template.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## .+$", template, re.MULTILINE)
    require(re.findall(r"^## .+$", summary, re.MULTILINE) == headings, "总结二级章节与默认模板不一致")
    for heading in headings:
        section = summary.split(heading, 1)[1].split("\n## ", 1)[0]
        model_section = template.split(heading, 1)[1].split("\n## ", 1)[0]
        header = next((line for line in model_section.splitlines() if line.startswith("|")), None)
        if header:
            cells = lambda row: [cell.strip() for cell in row.strip().strip("|").split("|")]
            actual = next((line for line in section.splitlines() if line.startswith("|")), "")
            require(cells(actual) == cells(header), f"{heading} 表头与默认模板不一致")
    metrics = {}
    for line in summary.splitlines():
        if line.startswith("|"):
            parts = [part.strip() for part in line.strip().strip("|").split("|")]
            if len(parts) == 2 and not all(re.fullmatch(r":?-+:?", part) for part in parts):
                require(parts[0] not in metrics or parts[0] == "指标", f"总结指标重复：{parts[0]}")
                metrics[parts[0]] = parts[1]
    for key in ("用例总数", "最终用例数"):
        require(metrics.get(key) == str(len(cases)), f"总结 {key} 与 JSON 不一致")
    counts = Counter(case["priority"] for case in cases)
    require(metrics.get("P0 / P1 / P2", "").replace(" ", "") ==
            "/".join(str(counts[p]) for p in ("P0", "P1", "P2")), "总结优先级数量与 JSON 不一致")


def main() -> int:
    parser = argparse.ArgumentParser(description="检查用例数据协议，不代替业务评审")
    parser.add_argument("cases")
    parser.add_argument("--summary", help="检查默认模板总结的章节、表头和最终数量")
    args = parser.parse_args()
    try:
        cases, version, warnings = load_document(Path(args.cases))
        if args.summary:
            validate_summary(Path(args.summary), cases)
    except (OSError, ValueError) as exc:
        print(f"校验失败：{exc}", file=sys.stderr)
        return 1
    print(f"结构校验通过：V{version}，{len(cases)} 条，优先级 {dict(Counter(c['priority'] for c in cases))}")
    for warning in warnings:
        print(f"警告：{warning}")
    if args.summary:
        print("默认总结模板与最终数量检查通过。")
    print("业务覆盖、规则来源、分类粒度与总结一致性仍需语义评审。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
