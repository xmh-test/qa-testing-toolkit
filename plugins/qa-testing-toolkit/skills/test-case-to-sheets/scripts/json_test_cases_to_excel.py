#!/usr/bin/env python3
"""
Convert test-case JSON files to Excel .xlsx files.

Usage:
  python3 scripts/json_test_cases_to_excel.py test_cases/MINISPHOTO/相册备份/测试用例_20260525_145457.json
  python3 scripts/json_test_cases_to_excel.py input.json -o output.xlsx

The script uses only Python standard-library modules and writes a real .xlsx
workbook directly, so no pandas/openpyxl dependency is required.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any


BASE_COLUMNS = [
    ("序号", "__index__"),
    ("用例名称", "title"),
    ("所属目录", "directory"),
    ("标签", "tags"),
    ("优先级", "priority"),
    ("用例类型", "case_type"),
    ("前置条件", "precondition"),
    ("步骤", "steps"),
    ("预期结果", "expected"),
    ("功能模块", "functional_module"),
]

V2_COLUMNS = [
    ("用例ID", "case_id"),
    ("需求编号", "requirement_ids"),
    ("验收标准编号", "acceptance_criteria_ids"),
    ("功能点编号", "functional_point_id"),
    ("设计方法", "design_methods"),
    ("BDD场景ID", "bdd_scenario_id"),
    ("DDT数据集ID", "ddt_dataset_ids"),
    ("DDT数据行ID", "ddt_row_id"),
    ("资产类型", "__asset_type__"),
    ("覆盖关系", "__coverage__"),
    ("执行建议", "__execution_advice__"),
]

BASE_COLUMN_WIDTHS = [8, 44, 24, 22, 10, 18, 42, 48, 54, 18]
V2_COLUMN_WIDTHS = [20, 20, 20, 16, 24, 22, 24, 28, 18, 42, 24]
PIPE_LIST_FIELDS = {
    "tags", "requirement_ids", "acceptance_criteria_ids",
    "design_methods", "ddt_dataset_ids",
}
PRIORITY_STYLES = {"P0": 2, "P1": 3, "P2": 4}
INVALID_XML_RE = re.compile(
    r"[^\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD]",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将测试用例 JSON 转换为 Excel .xlsx 文件。",
    )
    parser.add_argument("json_file", help="测试用例 JSON 文件路径")
    parser.add_argument(
        "-o",
        "--output",
        help="输出 .xlsx 文件路径；默认与 JSON 同目录同名",
    )
    parser.add_argument(
        "--sheet-name",
        default="测试用例",
        help="工作表名称，默认：测试用例",
    )
    parser.add_argument(
        "--exclude-covered-atomic",
        action="store_true",
        help="排除被 BDD/DDT 完整覆盖且未被部分覆盖的常规原子用例",
    )
    parser.add_argument("--feature", help="显式指定覆盖关系来源的 BDD .feature 文件")
    parser.add_argument("--ddt", help="显式指定覆盖关系来源的 DDT JSON 文件")
    return parser.parse_args()


def load_case_bundle(
    json_path: Path,
) -> tuple[list[dict[str, Any]], bool, dict[str, Any] | None]:
    with json_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    is_v2 = False
    metadata: dict[str, Any] | None = None
    if isinstance(payload, list):
        cases = payload
    elif isinstance(payload, dict):
        is_v2 = payload.get("schema_version") == "2.0"
        raw_metadata = payload.get("metadata")
        metadata = raw_metadata if isinstance(raw_metadata, dict) else None
        cases = None
        for key in ("cases", "test_cases", "items", "data", "rows"):
            value = payload.get(key)
            if isinstance(value, list):
                cases = value
                break
        if cases is None:
            raise ValueError(
                "JSON 根对象不是数组，也未找到 cases/test_cases/items/data/rows 数组字段",
            )
    else:
        raise ValueError("JSON 根节点必须是数组或对象")

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(cases, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 条用例不是 JSON 对象")
        normalized.append(item)
    return normalized, is_v2, metadata


def load_case_document(json_path: Path) -> tuple[list[dict[str, Any]], bool]:
    """Backward-compatible helper returning cases and the V2 flag."""
    cases, is_v2, _ = load_case_bundle(json_path)
    return cases, is_v2


def load_cases(json_path: Path) -> list[dict[str, Any]]:
    """Backward-compatible helper returning only the case list."""
    cases, _ = load_case_document(json_path)
    return cases


def resolve_artifact_path(
    base: Path,
    explicit: str | None,
    metadata: dict[str, Any] | None,
    key: str,
) -> tuple[Path | None, bool]:
    """Return artifact path and whether it was explicitly selected."""
    if explicit:
        value = Path(explicit).expanduser()
        return (value.resolve() if value.is_absolute() else (Path.cwd() / value).resolve()), True
    artifacts = metadata.get("artifacts") if isinstance(metadata, dict) else None
    value = artifacts.get(key) if isinstance(artifacts, dict) else None
    if value is None:
        return None, False
    if not isinstance(value, str) or not value:
        raise ValueError(f"metadata.artifacts.{key} 必须是非空路径或 null")
    path = Path(value).expanduser()
    return (path.resolve() if path.is_absolute() else (base / path).resolve()), False


def add_relation(
    relations: dict[str, dict[str, set[str]]],
    case_id: str,
    level: str,
    source: str,
) -> None:
    relations.setdefault(case_id, {"full": set(), "partial": set()})[level].add(source)


def parse_feature_coverage(path: Path) -> dict[str, dict[str, set[str]]]:
    text = path.read_text(encoding="utf-8")
    if not re.search(r"^\s*Feature:\s+.+", text, re.MULTILINE):
        raise ValueError(f"Feature 无法解析或缺少 Feature 声明：{path}")
    relations: dict[str, dict[str, set[str]]] = {}
    blocks = re.finditer(
        r"(?P<tags>(?:^\s*@[^\n]+\n)+)^\s*Scenario(?: Outline)?:\s+.+",
        text,
        re.MULTILINE,
    )
    found = False
    for match in blocks:
        found = True
        tags = set(re.findall(r"@([^\s]+)", match.group("tags")))
        bdd_ids = sorted(tag for tag in tags if re.fullmatch(r"BDD-FP\d{3,}-\d{3,}", tag))
        source = bdd_ids[0] if bdd_ids else path.name
        for tag in tags:
            if tag.startswith("covers-full-"):
                add_relation(relations, tag.removeprefix("covers-full-"), "full", source)
            elif tag.startswith("covers-partial-"):
                add_relation(relations, tag.removeprefix("covers-partial-"), "partial", source)
    if not found:
        raise ValueError(f"Feature 中未找到带标签的 Scenario：{path}")
    return relations


def parse_ddt_coverage(path: Path) -> dict[str, dict[str, set[str]]]:
    with path.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError(f"DDT JSON 根节点必须是对象：{path}")
    version = payload.get("schema_version")
    if version == "1.0":
        return {}
    if version != "2.0":
        raise ValueError(f"不支持的 DDT schema_version：{version}")
    datasets = payload.get("datasets")
    if not isinstance(datasets, list):
        raise ValueError(f"DDT datasets 必须是数组：{path}")
    relations: dict[str, dict[str, set[str]]] = {}
    for index, dataset in enumerate(datasets, 1):
        if not isinstance(dataset, dict):
            raise ValueError(f"DDT 第 {index} 个 dataset 不是对象")
        dataset_id = dataset.get("dataset_id")
        if not isinstance(dataset_id, str) or not dataset_id:
            raise ValueError(f"DDT 第 {index} 个 dataset_id 缺失")
        coverage = dataset.get("coverage")
        if not isinstance(coverage, dict):
            raise ValueError(f"{dataset_id}.coverage 缺失")
        full = coverage.get("full_case_ids")
        partial = coverage.get("partial_case_ids")
        if not isinstance(full, list) or not isinstance(partial, list):
            raise ValueError(f"{dataset_id} 的 full_case_ids/partial_case_ids 必须是数组")
        if any(not isinstance(value, str) or not value for value in full + partial):
            raise ValueError(f"{dataset_id} 的 coverage 包含无效 case ID")
        for case_id in full:
            add_relation(relations, case_id, "full", dataset_id)
        for case_id in partial:
            add_relation(relations, case_id, "partial", dataset_id)
    return relations


def merge_relations(
    *sources: dict[str, dict[str, set[str]]],
) -> dict[str, dict[str, set[str]]]:
    merged: dict[str, dict[str, set[str]]] = {}
    for source in sources:
        for case_id, levels in source.items():
            for level in ("full", "partial"):
                for origin in levels[level]:
                    add_relation(merged, case_id, level, origin)
    return merged


def validate_filter_relations(
    cases: list[dict[str, Any]],
    relations: dict[str, dict[str, set[str]]],
) -> None:
    case_map: dict[str, dict[str, Any]] = {}
    for index, case in enumerate(cases, 1):
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id:
            raise ValueError(f"第 {index} 条 V2 用例缺少稳定 case_id，不能覆盖过滤")
        if case_id in case_map:
            raise ValueError(f"case_id 重复，不能覆盖过滤：{case_id}")
        case_map[case_id] = case
    unknown = set(relations) - set(case_map)
    if unknown:
        raise ValueError(f"覆盖关系引用未知 case ID：{'|'.join(sorted(unknown))}")
    conflicts = {
        case_id for case_id, levels in relations.items()
        if levels["full"] and levels["partial"]
    }
    if conflicts:
        raise ValueError(f"同一 case 同时被 full 和 partial 覆盖：{'|'.join(sorted(conflicts))}")
    invalid_full = {
        case_id for case_id, levels in relations.items()
        if levels["full"] and case_map[case_id].get("design_methods") != ["functional-point"]
    }
    if invalid_full:
        raise ValueError(f"full 覆盖指向 BDD/DDT 模板用例：{'|'.join(sorted(invalid_full))}")


def asset_type(case: dict[str, Any]) -> str:
    methods = case.get("design_methods")
    if methods == ["functional-point"]:
        return "常规原子用例"
    method_set = set(methods) if isinstance(methods, list) else set()
    if {"bdd", "ddt"} <= method_set:
        return "BDD+DDT参数化流程"
    if "bdd" in method_set:
        return "BDD完整流程"
    if "ddt" in method_set:
        return "DDT模板"
    return "常规用例"


def decorate_cases(
    cases: list[dict[str, Any]],
    relations: dict[str, dict[str, set[str]]],
) -> list[dict[str, Any]]:
    decorated: list[dict[str, Any]] = []
    for case in cases:
        copy = dict(case)
        levels = relations.get(str(case.get("case_id")), {"full": set(), "partial": set()})
        full_sources = sorted(levels["full"])
        partial_sources = sorted(levels["partial"])
        relation_parts: list[str] = []
        if full_sources:
            relation_parts.append(f"完整覆盖:{'|'.join(full_sources)}")
        if partial_sources:
            relation_parts.append(f"部分覆盖:{'|'.join(partial_sources)}")
        copy["__asset_type__"] = asset_type(case)
        copy["__coverage__"] = "；".join(relation_parts)
        if case.get("design_methods") != ["functional-point"]:
            copy["__execution_advice__"] = "专项用例，执行"
        elif partial_sources:
            copy["__execution_advice__"] = "部分覆盖，仍需执行"
        elif full_sources:
            copy["__execution_advice__"] = "已被完整覆盖，可跳过"
        else:
            copy["__execution_advice__"] = "执行"
        decorated.append(copy)
    return decorated


def column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name


def cell_ref(row: int, column: int) -> str:
    return f"{column_name(column)}{row}"


def clean_text(value: Any) -> str:
    if value is None:
        text = ""
    elif isinstance(value, list):
        text = "、".join(str(item) for item in value)
    elif isinstance(value, dict):
        text = json.dumps(value, ensure_ascii=False)
    else:
        text = str(value)
    return INVALID_XML_RE.sub("", text)


def normalize_cell_value(key: str, value: Any) -> Any:
    if key in PIPE_LIST_FIELDS and isinstance(value, list):
        return "|".join(str(item) for item in value)
    return value


def xml_text(value: Any) -> str:
    return escape(clean_text(value), quote=False)


def safe_sheet_name(name: str) -> str:
    cleaned = re.sub(r"[\[\]\:\*\?\/\\]", "_", name).strip() or "Sheet1"
    return cleaned[:31]


def row_height(values: list[Any], is_header: bool = False) -> int:
    if is_header:
        return 28
    max_lines = 1
    for value in values:
        max_lines = max(max_lines, clean_text(value).count("\n") + 1)
    return min(max(22, max_lines * 16), 140)


def cell_xml(row: int, column: int, value: Any, style: int = 0) -> str:
    ref = cell_ref(row, column)
    return (
        f'<c r="{ref}" s="{style}" t="inlineStr">'
        f'<is><t xml:space="preserve">{xml_text(value)}</t></is>'
        "</c>"
    )


def worksheet_xml(
    cases: list[dict[str, Any]],
    columns: list[tuple[str, str]] | None = None,
    column_widths: list[int] | None = None,
) -> str:
    columns = columns or BASE_COLUMNS
    column_widths = column_widths or BASE_COLUMN_WIDTHS
    row_count = len(cases) + 1
    col_count = len(columns)
    last_ref = cell_ref(max(row_count, 1), col_count)

    lines = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">',
        f'<dimension ref="A1:{last_ref}"/>',
        "<sheetViews><sheetView workbookViewId=\"0\">"
        '<pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/>'
        "</sheetView></sheetViews>",
        '<sheetFormatPr defaultRowHeight="18"/>',
        "<cols>",
    ]

    for index, width in enumerate(column_widths, start=1):
        lines.append(
            f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>',
        )
    lines.append("</cols>")
    lines.append("<sheetData>")

    headers = [header for header, _ in columns]
    lines.append(f'<row r="1" ht="{row_height(headers, True)}" customHeight="1">')
    for column, header in enumerate(headers, start=1):
        lines.append(cell_xml(1, column, header, style=1))
    lines.append("</row>")

    for row_index, case in enumerate(cases, start=2):
        values: list[Any] = []
        for _, key in columns:
            if key == "__index__":
                values.append(row_index - 1)
            else:
                values.append(normalize_cell_value(key, case.get(key, "")))

        lines.append(
            f'<row r="{row_index}" ht="{row_height(values)}" customHeight="1">',
        )
        for column, ((_, key), value) in enumerate(zip(columns, values), start=1):
            style = PRIORITY_STYLES.get(clean_text(value), 0) if key == "priority" else 0
            lines.append(cell_xml(row_index, column, value, style=style))
        lines.append("</row>")

    lines.extend(
        [
            "</sheetData>",
            f'<autoFilter ref="A1:{last_ref}"/>',
            "</worksheet>",
        ],
    )
    return "\n".join(lines)


def workbook_xml(sheet_name: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        f'<sheet name="{escape(sheet_name, quote=True)}" sheetId="1" r:id="rId1"/>'
        "</sheets>"
        "</workbook>"
    )


def workbook_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        'Target="styles.xml"/>'
        "</Relationships>"
    )


def root_rels_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" '
        'Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" '
        'Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" '
        'Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def content_types_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/styles.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" '
        'ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        "</Types>"
    )


def styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="11"/><name val="Arial"/></font>
    <font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Arial"/></font>
  </fonts>
  <fills count="7">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF2F5597"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFC7CE"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFFFE699"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFD9EAD3"/></patternFill></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FFE7E6E6"/></patternFill></fill>
  </fills>
  <borders count="2">
    <border><left/><right/><top/><bottom/><diagonal/></border>
    <border>
      <left style="thin"><color rgb="FFD9D9D9"/></left>
      <right style="thin"><color rgb="FFD9D9D9"/></right>
      <top style="thin"><color rgb="FFD9D9D9"/></top>
      <bottom style="thin"><color rgb="FFD9D9D9"/></bottom>
      <diagonal/>
    </border>
  </borders>
  <cellStyleXfs count="1">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>
  </cellStyleXfs>
  <cellXfs count="6">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="1" applyBorder="1" applyAlignment="1">
      <alignment vertical="top" wrapText="1"/>
    </xf>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center" wrapText="1"/>
    </xf>
    <xf numFmtId="0" fontId="0" fillId="3" borderId="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center" wrapText="1"/>
    </xf>
    <xf numFmtId="0" fontId="0" fillId="4" borderId="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center" wrapText="1"/>
    </xf>
    <xf numFmtId="0" fontId="0" fillId="5" borderId="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center" wrapText="1"/>
    </xf>
    <xf numFmtId="0" fontId="0" fillId="6" borderId="1" applyFill="1" applyBorder="1" applyAlignment="1">
      <alignment horizontal="center" vertical="center" wrapText="1"/>
    </xf>
  </cellXfs>
  <cellStyles count="1">
    <cellStyle name="Normal" xfId="0" builtinId="0"/>
  </cellStyles>
</styleSheet>
"""


def app_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>Python</Application>"
        "</Properties>"
    )


def core_xml() -> str:
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:creator>json_test_cases_to_excel.py</dc:creator>"
        "<cp:lastModifiedBy>json_test_cases_to_excel.py</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{created}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{created}</dcterms:modified>'
        "</cp:coreProperties>"
    )


def write_xlsx(
    cases: list[dict[str, Any]],
    output_path: Path,
    sheet_name: str,
    *,
    is_v2: bool = False,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sheet_name = safe_sheet_name(sheet_name)
    columns = BASE_COLUMNS + V2_COLUMNS if is_v2 else BASE_COLUMNS
    column_widths = BASE_COLUMN_WIDTHS + V2_COLUMN_WIDTHS if is_v2 else BASE_COLUMN_WIDTHS

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types_xml())
        archive.writestr("_rels/.rels", root_rels_xml())
        archive.writestr("docProps/app.xml", app_xml())
        archive.writestr("docProps/core.xml", core_xml())
        archive.writestr("xl/workbook.xml", workbook_xml(sheet_name))
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels_xml())
        archive.writestr("xl/styles.xml", styles_xml())
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            worksheet_xml(cases, columns, column_widths),
        )


def main() -> int:
    args = parse_args()
    json_path = Path(args.json_file).expanduser().resolve()
    if not json_path.exists():
        print(f"JSON 文件不存在：{json_path}", file=sys.stderr)
        return 1

    output_path = (
        Path(args.output).expanduser().resolve()
        if args.output
        else json_path.with_suffix(".xlsx")
    )

    temp_path: Path | None = None
    try:
        cases, is_v2, metadata = load_case_bundle(json_path)
        if args.exclude_covered_atomic and not is_v2:
            raise ValueError("V1 没有稳定 case ID，不支持 --exclude-covered-atomic")

        feature_path, feature_explicit = resolve_artifact_path(
            json_path.parent, args.feature, metadata, "bdd",
        )
        ddt_path, ddt_explicit = resolve_artifact_path(
            json_path.parent, args.ddt, metadata, "ddt",
        )
        relation_sources: list[dict[str, dict[str, set[str]]]] = []
        for path, explicit, kind, loader in (
            (feature_path, feature_explicit, "Feature", parse_feature_coverage),
            (ddt_path, ddt_explicit, "DDT", parse_ddt_coverage),
        ):
            if path is None:
                continue
            strict = args.exclude_covered_atomic or explicit
            try:
                if not path.exists():
                    raise ValueError(f"{kind} 文件不存在：{path}")
                relation_sources.append(loader(path))
            except Exception as exc:  # noqa: BLE001 - strict mode converts to CLI error.
                if strict:
                    raise ValueError(f"{kind} 覆盖关系读取失败：{exc}") from exc
                print(f"警告：忽略无法读取的 {kind} 覆盖关系：{exc}", file=sys.stderr)

        relations = merge_relations(*relation_sources)
        if args.exclude_covered_atomic:
            validate_filter_relations(cases, relations)

        total = len(cases)
        filtered: list[dict[str, Any]] = []
        excluded = 0
        for case in cases:
            levels = relations.get(str(case.get("case_id")), {"full": set(), "partial": set()})
            should_exclude = (
                args.exclude_covered_atomic
                and case.get("design_methods") == ["functional-point"]
                and bool(levels["full"])
                and not levels["partial"]
            )
            if should_exclude:
                excluded += 1
            else:
                filtered.append(case)

        decorated = decorate_cases(filtered, relations) if is_v2 else filtered
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            dir=output_path.parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
        write_xlsx(decorated, temp_path, args.sheet_name, is_v2=is_v2)
        os.replace(temp_path, output_path)
        temp_path = None
    except Exception as exc:  # noqa: BLE001 - CLI should print concise errors.
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        print(f"转换失败：{exc}", file=sys.stderr)
        return 1

    print(f"转换完成：总用例 {total}，排除完整覆盖原子用例 {excluded}，导出 {len(filtered)}。")
    print(f"输出文件：{output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
