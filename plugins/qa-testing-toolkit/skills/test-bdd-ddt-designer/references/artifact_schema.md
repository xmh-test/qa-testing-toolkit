# BDD/DDT 资产结构

## 常规 JSON 专项模板字段

常规 JSON 的每条 case 仍恰好包含 17 个字段。专项模板只改变以下关联值：

| 类型 | design_methods | bdd_scenario_id | ddt_dataset_ids | ddt_row_id |
|---|---|---|---|---|
| 常规原子 | `["functional-point"]` | null | `[]` | null |
| BDD | `["functional-point","bdd"]` | BDD ID | `[]` | null |
| DDT | `["functional-point","ddt"]` | null | 一个或多个 dataset ID | null |
| BDD+DDT | `["functional-point","bdd","ddt"]` | BDD ID | 一个或多个 dataset ID | null |

完整 17 字段仍为：`case_id`、`requirement_ids`、`acceptance_criteria_ids`、`functional_point_id`、`design_methods`、`bdd_scenario_id`、`ddt_dataset_ids`、`ddt_row_id`、`title`、`directory`、`tags`、`priority`、`case_type`、`precondition`、`steps`、`expected`、`functional_module`。

## title 字段分流规则

| 模板类型 | title 规则 |
|---|---|
| 常规原子用例 | `【模块/功能点】【前置条件/场景】核心动作，预期结果`；必须使用中文全角方括号 `【】` |
| 普通 BDD | 与 Feature 的 Scenario 标题逐字一致；表达角色、完整业务动作链和最终结果 |
| Scenario Outline / BDD+DDT | 与 Feature 的 Scenario Outline 标题逐字一致；表达角色、参数化输入/动作和业务目标 |
| 纯 DDT | 表达业务对象、数据分类/参数维度和校验目标或结果 |

专项模板不因共用 17 字段而强制套用常规原子标题格式。标题规则不改变 schema，也不改变 `case_type`：设计方法仍只记录在 `design_methods`。

## DDT JSON V2

```json
{
  "schema_version": "2.0",
  "metadata": {
    "program": "MyApp",
    "module": "用户认证",
    "source_cases": "测试用例_20260806_100000.json",
    "generated_at": "2026-08-06 10:10:00"
  },
  "datasets": [
    {
      "dataset_id": "DDT-FP001-001",
      "case_id": "TC-FP001-010",
      "functional_point_id": "FP-001",
      "requirement_ids": ["REQ-001"],
      "acceptance_criteria_ids": ["AC-001"],
      "bdd_scenario_id": "BDD-FP001-001",
      "coverage": {
        "full_case_ids": ["TC-FP001-001"],
        "partial_case_ids": ["TC-FP001-002"],
        "execution_policy": "ddt-only-for-full"
      },
      "parameters": [
        {
          "name": "password",
          "type": "string",
          "required": true,
          "classes": ["valid-equivalence", "boundary"]
        }
      ],
      "rows": [
        {
          "row_id": "ROW-DDT-FP001-001-001",
          "classifications": ["valid-equivalence"],
          "values": {"password": "Correct#2026"},
          "expected": "登录成功并进入设备主页",
          "priority": "P0"
        }
      ]
    }
  ]
}
```

约束：

- `schema_version` 固定为 `2.0`。
- `metadata.source_cases` 必须指向被增强的常规 JSON。
- dataset/row ID 全局唯一。
- dataset `case_id` 必须存在且只属于该 dataset 对应的专项模板。
- `bdd_scenario_id` 仅 BDD+DDT 填写，纯 DDT 为 null。
- `coverage.execution_policy` 固定为 `ddt-only-for-full`。
- row 不包含 `case_id`；旧 V1 仅限读取兼容。

## Feature 覆盖示例

```gherkin
# source_cases: 测试用例_20260806_100000.json
Feature: 用户认证

  @BDD-FP001-001 @TC-FP001-010 @FP-001 @REQ-001 @AC-001 @P0
  @covers-full-TC-FP001-001 @covers-partial-TC-FP001-002
  Scenario Outline: 管理员使用不同凭据完成登录
    Given 管理员位于登录页
    When 管理员输入 "<account>" 和 "<password>" 并提交
    Then 系统显示 "<expected>"

    Examples:
      | row_id                    | account           | password     | expected             |
      | ROW-DDT-FP001-001-001     | admin@example.com | Correct#2026 | 登录成功并进入设备主页 |
```

Feature 标签中的覆盖集合必须与关联 dataset 的 coverage 一致。
