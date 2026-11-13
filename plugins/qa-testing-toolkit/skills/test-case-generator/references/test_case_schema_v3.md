# 常规测试用例 JSON V3

```json
{
  "schema_version": "3.0",
  "metadata": {
    "program": "示例应用",
    "module": "文件备份",
    "platform": "web",
    "source": "./需求.md",
    "generated_at": "2026-10-20 10:30:00",
    "artifacts": {"summary": "./文件备份_测试用例总结.md"}
  },
  "cases": []
}
```

根对象仅含以上三个字段。metadata 以上字段必填；可选 `updated_at`、`change_source` 记录更新。时间使用当地 `YYYY-MM-DD HH:mm:ss`。program、module、platform 必填，共同作为稳定模块身份；更新沿用已确认值，需改名或改变平台范围时先核对映射及影响。platform 使用平台 tag，多平台以 `|` 连接。source 为真实输入位置或标注本次用户需求。

artifacts 仅含 summary；填写实际总结文件引用，推荐相对 JSON 所在目录（如 `./文件备份_测试用例总结.md`），用户只要 JSON 时为 null。文件名由项目或用户确定，默认稳定且沿用已确认文件，不要求固定为 `cases.json`/`summary.md`，也不为每次生成追加时间戳。正式交付 cases 非空，无可测试规则时说明阻塞，不生成“成功”的空文件。

## 每条恰好 13 字段

| 字段 | 类型 | 规则 |
|---|---|---|
| case_id | string | 唯一，例如 TC-FP001-001 |
| requirement_ids | string[] | 非空、不重复，引用真实需求 |
| acceptance_criteria_ids | string[] | 非空、不重复，引用验收标准 |
| functional_point_id | string | FP-001，至少三位数字 |
| title | string | 遵守 common_case_rules.md |
| directory | string | 项目名\|平台分类\|模块名 |
| tags | string[] | 平台及可选 destructive |
| priority | string | P0 / P1 / P2 / P3，定级遵守 common_case_rules.md |
| case_type | string | common_case_rules.md 中定义的类型 |
| precondition | string | 连续编号，内容自包含 |
| steps | string | 连续编号的操作 |
| expected | string | 与步骤编号及数量对应 |
| functional_module | string | 与目录第三段和 metadata.module 一致 |

## 历史输入

支持 V1 九字段数组和 V2 纯常规用例。仍检查字段、ID、步骤编号；旧标题形式仅给警告，不以新标题规则阻断历史导出。V3 严格执行新规范。

V2 仅接受 `generation_strategy=functional-point`、每条 `design_methods=["functional-point"]`、历史专项关联和 artifacts 专项引用为空。其他策略、关联或未知字段报错，不自动筛掉部分用例。历史混合资产保留原文件，由用户另行确定处理范围。

旧文件更新默认另存 V3，保留旧文件；先补齐有依据的追溯、标题和编号。无法确认的映射列缺口，不虚构来源。Excel 的历史格式适配不改写输入。

优先级新增 P3，不改变 V3 字段结构。新总结使用四等级统计；历史三等级总结仅在用例不含 P3 时允许校验，更新总结时改为四等级并按实际用例计数，不批量重标旧用例。

## 可选关联文件检查

普通本地生成保留真实来源。需要核实关联文件或接入 Agent Case Manager 时，运行以下只读检查，`--root` 指定本地内容边界，项目接入时使用用例仓库根目录。该目录无需为 Git 仓库。

```bash
python3 <skill-dir>/scripts/check_case_links.py <JSON> --root <内容根目录>
```

提供 `--summary <实际总结文件>` 可额外核对该文件是否与 `metadata.artifacts.summary` 一致。检查器验证 V3、实际引用、存在性、路径边界、歧义和 UTF-8 可读性；默认总结的结构与数量仍由 `test_case_contract.py --summary` 校验。自定义总结按用户结构人工核对。

- `./` 或 `../` 开头的引用相对 JSON 所在目录解析，允许在边界内返回上级目录。
- 普通相对路径兼容旧文件，检查 JSON 所在目录和内容根目录；只有一个实际文件时采用它，两处指向不同文件时报告歧义，使用 `./` 或 `../` 明确引用。
- 指定文件缺失、越界、访问 `.git`、符号链接或嵌套仓库/子模块时报告错误。关联内容按 UTF-8 文本检查，PDF/Word 等二进制材料保留真实来源并另行处理。
- 总结必须指向实际文件或为 null。source 是外部 URL、绝对本机路径或无法解析为文件的文字需求时，保留来源信息并提示未捕获，不自动读取或下载。带路径或扩展名的相对文件引用缺失时报告错误。
- 项目接入时优先使用仓库内明确相对引用，并核对 JSON、需求和总结能在同一输入提交中解析。检查本地文件存在只证明本地引用可用，提交内容与捕获结果按 [Git 与项目接入](git-integration.md) 核验。
