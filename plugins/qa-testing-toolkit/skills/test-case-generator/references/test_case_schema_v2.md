# 常规测试用例 JSON V2

## 根对象

```json
{
  "schema_version": "2.0",
  "metadata": {
    "program": "MyApp",
    "module": "用户认证",
    "platform": "Web",
    "source": "需求分析_20260806_100000.md",
    "generated_at": "2026-08-06 10:30:00",
    "generation_strategy": "functional-point",
    "artifacts": {
      "summary": "用户认证_测试用例总结_20260806_103000.md",
      "bdd": null,
      "ddt": null
    }
  },
  "cases": []
}
```

`metadata` 中上述字段必须存在。BDD/DDT 关联字段作为后续专项增强接口保留，常规生成器不得填充。

## 每条用例的 17 个字段

| 字段 | 类型 | 常规生成规则 |
|------|------|-------------|
| `case_id` | string | 唯一，格式 `TC-FP001-001` |
| `requirement_ids` | string[] | 非空，引用 REQ |
| `acceptance_criteria_ids` | string[] | 非空，引用 AC |
| `functional_point_id` | string | 格式 `FP-001` |
| `design_methods` | string[] | 固定 `["functional-point"]` |
| `bdd_scenario_id` | null | 固定 null |
| `ddt_dataset_ids` | string[] | 固定空数组 |
| `ddt_row_id` | null | 固定 null |
| `title` | string | `[模块/功能点][前置条件/场景]核心动作，预期结果` |
| `directory` | string | `项目名|平台分类|模块名` |
| `tags` | string[] | 平台与可选 destructive |
| `priority` | string | P0/P1/P2 |
| `case_type` | string | 测试性质，不承载设计方法 |
| `precondition` | string | 编号前置条件 |
| `steps` | string | 原子编号步骤 |
| `expected` | string | 与步骤一一对应 |
| `functional_module` | string | 与 directory 模块一致 |

## 专项增强兼容

`test-bdd-ddt-designer` 可以就地追加 BDD/DDT 专项用例并填充保留字段。新模型中一个 DDT dataset 对应一条模板用例，`ddt_row_id` 保持 null；历史按 row 展开的 V2 仍允许使用非空 `ddt_row_id`。

## V1 兼容

旧版根数组继续视为 V1，每条记录恰好包含原 9 字段。重新输出时升级为 V2。
