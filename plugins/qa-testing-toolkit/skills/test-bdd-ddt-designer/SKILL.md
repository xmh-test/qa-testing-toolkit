---
name: test-bdd-ddt-designer
description: 基于需求、功能点或常规 JSON V2，先聚合业务旅程，再生成完整、独立、不过度碎片化的 BDD 场景与 DDT 数据集；在增强模式下将每个 Scenario、Scenario Outline 或 dataset 各同步为一条可人工评审的 JSON 模板用例。适用于 BDD、Gherkin、Given/When/Then、Scenario Outline、DDT、数据驱动、等价类和边界值设计；不用于仅生成常规原子用例。
---

# 目标

以“一个可独立执行的业务结果闭环”为 Scenario 边界。先跨功能点识别角色目标和业务旅程，再决定合并、拆分或参数化，避免把按钮、字段和常规原子用例机械转换成零散 BDD 场景。

覆盖关系直接写入 Feature 与 DDT JSON，不创建独立覆盖文件。现有 JSON V2、Feature 和 DDT V2 的字段协议保持兼容。

# 工作模式与输入

## 快速设计模式

用户提供需求、PRD、功能点清单、验收标准或已确认的业务说明，但没有常规 JSON V2 时使用。

- 必须有足以识别角色、业务目标、前置状态、关键规则和可观察结果的需求来源。
- 输出业务旅程清单、BDD Feature；适用时输出 DDT 设计。没有 case ID 时不虚构 `@TC-*` 或 full/partial 覆盖标签。
- 不创建或修改常规 JSON；在交付总结中列出尚不能追溯到用例 ID 的场景。
- 需求不足时记录 P0/P1/P2 缺口，不自行补写业务规则。

## 资产增强模式

用户提供需求来源和 `test-case-generator` 生成的常规 JSON V2 时使用。必须读取：

1. 需求分析文档、PRD 或其他已确认需求来源；优先使用含 REQ、AC、FP、BDD 候选场景和 DDT 数据矩阵的需求分析。
2. `test-case-generator` 生成的常规 JSON V2；根对象必须有 `schema_version: "2.0"` 与 `cases`。
3. 同批次常规总结（如存在），用于同步统计与资产链接。

若只有 V1 数组，先调用或建议使用 `test-case-generator` 升级为 V2。不得在缺少需求来源时仅凭现有用例臆造业务规则。

# 强制工作流

生成前完整读取 `references/bdd_profile.md`、`references/ddt_profile.md` 和 `references/artifact_schema.md`。

## 1. 确定模式与设计范围

- 存在角色目标、跨步骤业务流程、权限、状态变化或业务规则分支：考虑 BDD。
- 存在字段校验、有效/无效等价类、边界值、特殊值或有业务意义的条件组合：应用 DDT。
- 同一业务路径仅输入和预期数据变化：设计 `Scenario Outline` 并关联 DDT dataset。
- 两者都不满足：增强模式保留常规原子用例；快速模式说明该功能不适合创建专项资产。

## 2. 先构建业务旅程图

必须先通读同一模块的全部需求、功能点和已有用例，再按以下信息形成候选旅程：

- 角色和权限；
- 主要业务目标与业务对象；
- 初始状态、触发条件和终止状态；
- 必要动作、关键状态转换和可观察检查点；
- 成功结果、异常分支与清理责任；
- 涉及的 REQ、AC、FP 和常规用例 ID。

不得按功能点数量、页面控件数量或常规原子用例数量直接决定 Scenario 数量。一个旅程可以覆盖多个功能点和多条原子用例。

## 3. 确定 Scenario 边界

一个 Scenario 原则上只有一个主要角色、一个主要业务目标、一个明确初始状态和一个最终业务结果。

可将属于同一目标、同一对象和同一状态生命周期的连续动作合并。出现独立业务目标、不同业务对象、实质不同的执行路径、独立清理责任、多角色/权限，或不可逆状态变化时拆分。

“前置条件相同”不是合并依据。共享上下文使用 `Background` 或各 Scenario 的 Given 表达；每个 Scenario 仍必须可独立执行。

## 4. 决定普通场景、Outline 与 dataset

- 普通 Scenario：一条确定业务路径及其结果闭环。
- Scenario Outline：业务动作路径、状态转换和断言结构相同，仅输入数据及对应结果变化。
- 纯 DDT：数据规则是重点，不需要额外表达角色业务旅程。
- 不同校验层级或失败路径，例如客户端格式拦截、服务端认证失败和网络异常，默认拆成不同 Scenario/dataset，不能仅靠 Examples 行混在一起。
- DDT 生成前计算理论组合数；超过 `references/ddt_profile.md` 的默认阈值时，必须使用等价类代表值、边界值、pairwise 或风险组合削减，禁止直接展开笛卡尔积。

## 5. 执行粒度与独立性审查

生成资产前逐条检查：

- 场景标题是否表达角色、完整业务行为和最终结果，而不是按钮或控件。
- 任一步骤失败后，剩余步骤是否只是同一目标的必要后续；若后半段是另一个仍有独立价值的目标，应拆分。
- 场景是否自行建立前置状态、使用独立测试数据并清理自己创建的数据。
- 是否依赖另一 Scenario 的执行顺序、账号状态或残留数据；存在依赖则重构。
- 是否将每条原子用例机械生成成一个 Scenario；若是，返回业务旅程重新聚合。
- 是否为了减少数量而合并多个互不相关的最终断言；若是，拆分。

## 6. 生成 BDD 与 DDT

- 普通 Scenario：每个业务结果闭环生成一条 Feature 场景；增强模式同步一条完整流程 JSON 用例。
- Scenario Outline：每个参数化完整流程只同步一条 JSON 模板用例；Examples 行不展开为 JSON 用例。
- 纯 DDT：每个 dataset 只同步一条 JSON 模板用例；具体参数、分类和逐行预期仅写入独立 DDT JSON。
- BDD+DDT：JSON 展示完整参数化业务流程，Feature 展示 Outline/Examples，DDT JSON 保存权威参数与 rows。
- 新生成的专项 JSON 用例 `ddt_row_id` 固定为 null。

## 7. 完善常规覆盖与追溯（仅资产增强模式）

- 检查 REQ、AC、FP、主流程、异常流、权限和关键状态是否有必要的常规原子用例。
- 发现缺口时，在原 JSON 中先补充原子用例：`design_methods` 严格为 `["functional-point"]`，专项关联字段为空。
- 不因 BDD/DDT 会覆盖而删除常规原子用例；用 full/partial 覆盖标记控制重复执行。
- 不产生无业务意义的字段、状态、角色或平台笛卡尔积。
- Feature 在场景标签中直接写 `@covers-full-{case_id}` 与 `@covers-partial-{case_id}`。
- DDT dataset 在 `coverage.full_case_ids`、`coverage.partial_case_ids` 与 `coverage.execution_policy` 中记录覆盖。
- full 仅在平台、角色、前置、操作和全部断言一致时使用；partial 表示只覆盖部分内容。
- 同一 case ID 不得同时进入 full 和 partial。
- full/partial 只引用严格常规原子用例；不得指向 BDD、DDT 或混合模板用例。
- BDD+DDT 的 Feature 与 DDT dataset 覆盖关系必须一致。

## 8. 安全更新资产

资产增强模式在临时文件中生成并校验更新后的常规 JSON、总结、Feature 和 DDT JSON；确认 JSON 可解析、17 字段、ID 唯一、步骤/预期对应及跨文件引用后再原子替换。无适用资产时不生成空文件。

快速设计模式不得假装完成 JSON 回写；仅保存用户要求的 Feature、DDT 或 Markdown 设计结果。

# 常规 JSON 更新规则（仅资产增强模式）

- 普通 BDD：`design_methods=["functional-point","bdd"]`，填写 `bdd_scenario_id`。
- 纯 DDT：`design_methods=["functional-point","ddt"]`，填写一个 `ddt_dataset_ids`。
- BDD+DDT：三个方法均填写，同时关联一个场景和一个或多个数据集。
- 每个 Scenario、Outline 或 dataset 只对应一条专项模板用例；一个 BDD+DDT Outline 不再额外生成纯 DDT 模板。
- 专项模板的 `steps`/`expected` 应足以人工评审完整流程；数据位通过 dataset 参数名表达，具体 rows 以 DDT JSON 为准。
- `tags` 仍只保存平台与 `destructive`；`case_type` 不承载设计方法。

## 专项模板标题

- 仅 `design_methods=["functional-point"]` 的常规原子用例沿用 `[模块/功能点][前置条件/场景]核心动作，预期结果`。
- 含 `bdd` 或 `ddt` 的专项模板不强制使用常规原子用例标题格式，按 `references/bdd_profile.md` 和 `references/ddt_profile.md` 使用自然中文标题。
- 普通 BDD 标题表达“角色 + 完整业务动作链 + 最终业务结果”；Scenario Outline 或 BDD+DDT 标题表达“角色 + 参数化输入/动作 + 业务目标”，不在标题枚举各数据行结果。
- BDD 与 BDD+DDT 的 JSON `title` 必须与关联 Feature 中的 Scenario/Scenario Outline 标题逐字一致，避免跨文件语义漂移。
- 纯 DDT 的 JSON `title` 表达“业务对象 + 数据分类/参数维度 + 校验目标或结果”；dataset 不另设标题字段，具体值和逐行结果保留在 rows。
- 专项标题不得包含 BDD/DDT、case/scenario/dataset ID、`<参数占位符>` 或“测试方法”等实现性术语。

# Metadata 与输出

资产增强模式沿用输入 JSON 所在批次目录和时间戳，输出：

- 原常规 JSON：就地增强。
- 原常规总结：就地更新统计、覆盖说明和资产链接。
- `{模块}_BDD_${TIMESTAMP}.feature`：有 BDD 场景时生成。
- `{模块}_DDT_${TIMESTAMP}.json`：有 DDT 数据集时生成。

更新 metadata：

- `generation_strategy`: `functional-point+behavior-data`
- `artifacts.bdd`: Feature 文件名或 null
- `artifacts.ddt`: DDT JSON 文件名或 null
- `enriched_at`: `YYYY-MM-DD HH:mm:ss`

保留原 `generated_at`、来源、平台和常规总结信息。文件引用优先使用相对于常规 JSON 所在目录的路径。

快速设计模式至少交付业务旅程清单、场景合并/拆分依据、Feature，以及适用的 DDT 数据分类。用户要求保存文件时再落盘。

# 质量门槛

- BDD 场景必须闭合一个角色目标，不得把按钮点击或单一 UI 操作机械拆成场景。
- 场景数量必须来自业务旅程和结果分支，不得与功能点或原子用例一一对应。
- 每个 Scenario 可单独运行、可重复运行，不依赖其他 Scenario 的顺序和残留数据。
- JSON 的 BDD 流程与 Feature 语义一致，Scenario Outline Examples 与 DDT rows 一致。
- 专项标题应能独立表达业务意图；BDD/BDD+DDT 的 Feature 与 JSON 标题逐字一致，纯 DDT 标题与 dataset 的数据维度和验证目标一致。
- DDT 分类、具体值、逐行预期和优先级完整；未知限制进入需求缺口。
- DDT 必须报告参数维度、理论组合数、实际数据行数和削减策略；无明确理由不得超过默认行数上限。
- 不允许孤立 scenario/dataset、重复 ID、错误 full 标记或一个 dataset 对应多个 JSON 模板。
- 资产增强模式的所有新增用例继续遵守 17 字段、平台白名单、步骤预期一一对应和确定性 ID 规则。

# 沟通与交付

- 全程使用中文说明，Gherkin 关键字使用英文、描述使用中文。
- 明确报告采用的工作模式、业务旅程数以及主要合并/拆分依据。
- 两种模式均报告 BDD 场景数、Outline 数、DDT dataset/row 数、理论组合数、组合削减策略、需求缺口和 N/A 项。
- 资产增强模式额外报告新增常规原子用例数及 full/partial 覆盖数。
- 若需求规则不足，保留 P0/P1/P2 需求缺口，不自行补写具体限制。
