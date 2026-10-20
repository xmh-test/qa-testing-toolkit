# 常规测试用例 JSON V3

```json
{
  "schema_version": "3.0",
  "metadata": {
    "program": "示例应用",
    "module": "文件备份",
    "platform": "web",
    "source": "需求.md",
    "generated_at": "2026-10-20 10:30:00",
    "artifacts": {"summary": "文件备份_测试用例总结_20261020_103000.md"}
  },
  "cases": []
}
```

根对象仅含以上三个字段。metadata 以上字段必填；可选 `updated_at`、`change_source` 记录更新。时间使用当地 `YYYY-MM-DD HH:mm:ss`。platform 使用平台 tag，多平台以 `|` 连接。source 为真实输入位置或标注本次用户需求。

artifacts 仅含 summary；默认是实际总结文件名，用户只要 JSON 时可为 null。正式交付 cases 非空，无可测试规则时说明阻塞，不生成“成功”的空文件。

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
| priority | string | P0 / P1 / P2 |
| case_type | string | common_case_rules.md 中定义的类型 |
| precondition | string | 连续编号，内容自包含 |
| steps | string | 连续编号的操作 |
| expected | string | 与步骤编号及数量对应 |
| functional_module | string | 与目录第三段和 metadata.module 一致 |

## 历史输入

支持 V1 九字段数组和 V2 纯常规用例。仍检查字段、ID、步骤编号；旧标题形式仅给警告，不以新标题规则阻断历史导出。V3 严格执行新规范。

V2 仅接受 `generation_strategy=functional-point`、每条 `design_methods=["functional-point"]`、历史专项关联和 artifacts 专项引用为空。其他策略、关联或未知字段报错，不自动筛掉部分用例。历史混合资产保留原文件，由用户另行确定处理范围。

旧文件更新默认另存 V3，保留旧文件；先补齐有依据的追溯、标题和编号。无法确认的映射列缺口，不虚构来源。Excel 的历史格式适配不改写输入。
