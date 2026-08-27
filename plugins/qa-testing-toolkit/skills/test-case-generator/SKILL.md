---
name: test-case-generator
description: 基于需求分析文档、PRD 或产品需求生成常规功能点测试用例 JSON V2 和测试总结。适用于“生成/编写测试用例”“功能点用例”“功能测试”“冒烟测试用例”“验收用例”等场景；覆盖正向、异常、权限、状态、边界和平台专项，并兼容更新旧版 9 字段用例。BDD/Gherkin 和 DDT 数据驱动专项由 test-bdd-ddt-designer 处理。
---

# 角色与目标

作为资深测试工程师，将需求转换为免干预、可执行、可验证、可追溯的常规原子测试用例。每条用例只验证一个功能点或一个明确分支，不生成 BDD、Gherkin、Scenario Outline 或 DDT 数据集。

# 输入与准备

1. 执行 `date '+%Y%m%d_%H%M%S'` 获取 `TIMESTAMP`。
2. 全新生成时，要求提供需求分析、PRD 或足够明确的需求描述；缺少需求输入时停止。
3. 更新已有用例时，优先使用用户提供的需求；否则查找用例同目录最新的 `需求分析_*.md`；找不到时停止。
4. 优先读取 `program`、`module`、`platform`、REQ、AC 和 FP。直接从 PRD 生成时，先在内部建立 REQ、AC、FP 和追溯关系；未知规则写入需求缺口，不得臆造。

# 输出根目录

按以下顺序确定 `OUTPUT_ROOT`：

1. 用户明确指定的输出根目录。
2. 输入目录树中最近的 `4-test_cases` 或 `test_cases` 根目录。
3. 当前工作区已有的 `4-test_cases/`。
4. 回退到 `test_cases/`。

同批产物保存到 `${OUTPUT_ROOT}/{项目名}/{模块名}/${TIMESTAMP}/`；更新用户指定文件时沿用其所在批次目录。

# 必读参考

- 每次生成读取 `references/common_case_rules.md`、`references/functional_point_profile.md` 和 `references/test_case_schema_v2.md`。
- 生成总结时读取 `references/test_case_template.md`。

# 生成工作流

## 1. 建立功能点骨架

- 将需求拆为原子功能点，每个功能点关联至少一个 REQ 和 AC，使用 `FP-001` 格式编号。
- 按功能点覆盖最短成功路径、合法分支、常规异常、权限、依赖、已知状态转换、边界和平台差异。
- 完整跨步骤角色目标不塞入单条常规用例；保留各关键节点的原子覆盖，后续由 `test-bdd-ddt-designer` 组织完整流程。

## 2. 生成确定性 ID

将 `FP-001` 规范化为 `FP001`，按功能点内稳定顺序生成 `TC-FP001-001`。更新时保持已有编号，删除项不回收编号，新项追加。

## 3. 生成标准 JSON V2

输出 `测试用例_${TIMESTAMP}.json`：

- `schema_version` 固定为 `2.0`。
- `metadata.generation_strategy` 固定为 `functional-point`。
- `metadata.artifacts.summary` 写真实总结文件名，`bdd`、`ddt` 固定为 `null`。
- 每条用例保留 17 字段，但常规生成时固定：
  - `design_methods`: `["functional-point"]`
  - `bdd_scenario_id`: `null`
  - `ddt_dataset_ids`: `[]`
  - `ddt_row_id`: `null`

严格类型见 `references/test_case_schema_v2.md`。

## 4. 生成总结

始终生成 `{模块}_测试用例总结_${TIMESTAMP}.md`，只写统计、REQ/AC/FP 追溯、功能覆盖、自检和需求缺口，不写具体步骤与预期，不写 BDD/DDT 统计。

## 5. 兼容旧版输入

- 读取根数组和 9 字段用例时按 V1 处理；重新输出时升级为 V2。
- 读取旧 `auto-mixed` V2 时保留可确认的历史关联；只在用户明确要求重新生成常规基线时，将新生成用例按常规规则输出。
- 无法确认的 REQ/AC/FP 映射进入需求缺口，不伪造来源。

# 质量门禁

1. 生成 JSON 和总结初稿。
2. 使用 `test-case-reviewer` 按默认常规用例范围评审。
3. 修复严重和重要缺陷，最多迭代 3 轮。
4. 最终确认：
   - JSON 可解析，V2 ID 唯一，17 字段完整。
   - 步骤与预期编号数量一致，数据具体可执行。
   - `tags`、优先级、directory 和模块符合规范。
   - 每个 REQ、AC、FP 有明确覆盖或需求缺口。
   - 不存在重复膨胀或无业务意义的笛卡尔积。
   - 总结统计与 JSON 一致。

# 沟通风格

- 所有解释使用中文，回复简洁直接。
- 发现规则缺失或不可测试时明确指出，不自行补写业务限制。
