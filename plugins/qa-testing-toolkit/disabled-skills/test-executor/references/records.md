# 执行记录协议 v1

## 单一数据源

从 `assets/run-template.json` 创建本轮副本。原用例仍是设计内容来源，执行 JSON 是结果来源，Excel和总结是派生输出。脚本仅校验并统计，不控制设备或重写旧项目记录。历史格式需在本轮副本中显式映射；原因不明的旧“阻塞/部分执行”必须人工复核，不能自动迁移为通过。

- `input_case_ids`：输入设计用例的全部编号；`case_ids`：本轮实际纳入的全部编号，不只录已执行项。
- `excluded_cases`：全部范围外用例清单，每项含 `case_id/kind/categories/reason/enable_condition`，kind为scope（例如未入选冒烟）或special（专项未启用）；旧记录缺kind按special兼容；与case_ids不重叠，两者并集须等于input_case_ids。未启用专项不放入checks，不标记未执行或不适用。旧记录未提供input_case_ids时默认与case_ids相同。
- 混合用例按原ID保留，记录本轮纳入的断言与明确排除的专项分支；原文不删改。报表说明部分范围，不声称完整原用例通过。无法明确拆分时先确认，不自行缩减断言。
- `platforms`：本轮目标平台标识；一个标识包含 OS/设备类型和必要浏览器变体。
- `checks`：每个用例×平台恰好一项，包括有依据的不适用项，禁止省略未执行行。
- `attempts`：不可覆盖的尝试历史；`id` 唯一，含 `case_id/platform/build/at/steps/evidence`。证据使用本轮目录内的相对路径。当前检查项引用自己的 `attempt_ids`。
- `checks[].build` 是当前结果构建。当前断言的 `attempt_id` 必须对应相同构建；新构建不能继承旧断言通过。保留旧尝试，当前检查项改为新构建并重新填实际断言。
- `assertions` 是执行前从原用例展开的全部必需断言，ID不能因未测而删除；结果为 `pass/fail/not_run`，已执行断言必须指向尝试并有支持该断言的证据。动态新增分支保留来源。
- `cause.category`：`product/environment/permission/tool/data/requirement`；未完成项需要具体 `details` 和 `resume_condition`，产品原因另有 `bug_ids`。
- `bugs`：去重后的稳定本地ID及事实、证据、已复现平台；远端 `remote_id/url/submission_state` 独立保存。一个缺陷可关联多项用例，创建未知结果不得再次盲建。
- `analysis_gate/environment_gate`：保存是否就绪及产物/证据；门禁记录不计为实际执行尝试。
- `restoration`：每项原始状态、变更、恢复方法、状态、核验及无法恢复原因；外部缺口单列 `resources`。

## 确定性分类

1. 明确不适用且有依据 → 不适用；不能把资源不足标为不适用。
2. 任一已验证断言失败 → 失败；未完成分支仍保留原因。
3. 必需断言全部通过 → 通过。
4. 否则产品原因、关联缺陷、继续条件齐备 → 阻塞。
5. 否则 → 未执行；已尝试或部分断言执行则进度为部分完成。

直接验证“应有该功能却没有”是失败；依赖该功能的其他断言无法执行是阻塞。部分完成数量是进度的交叉统计，不在主状态总和中重复相加。失败也可能进度部分完成。

## 导出与核验

运行 `python3 scripts/execution_state.py run.json --output summary.json`。生成每项最新主状态、进度、分平台/构建覆盖、本轮纳入设计用例数、输入设计用例数、范围外总数及其中专项数、适用平台项数、尝试数、去重缺陷数和未完整执行项数。主状态总和等于矩阵项数；适用项数排除不适用。报告同时展示“已实际执行过的项”与“全部断言完成项”，不能拿前者冒充完成率。

Excel保留原用例内容/顺序及全部平台行，附当前状态、进度、版本、尝试链接、证据、缺陷、原因、继续条件；另有尝试历史、缺陷、资源、恢复和汇总页。状态计数直接取脚本结果，校验回读值与JSON一致。公式有缓存时核对缓存值，不把公式存在当作计算成功。

断点恢复时先读取：输入指纹→当前构建→最后尝试→未知结果操作→缺陷提交映射→恢复台账。仅处理未完成分支，不重复报告相同缺口；有新证据后追加尝试，再更新当前检查项快照并重新统计。

## 一次尝试与缺陷记录示例

下面是结构示意，示例值不能当作真实执行结果。`steps`写实际执行动作与观察；断言证据位于检查项内，必须能支持该条结论。

```json
{
  "attempt": {
    "id": "attempt-unique-id", "case_id": "CASE-001", "platform": "local-desktop",
    "build": "实际构建或已观测前端指纹", "at": "带时区的实际执行时间",
    "steps": ["实际操作与观察"], "evidence": ["evidence/actual-shot.png"]
  },
  "bug": {
    "id": "LOCAL-BUG-001", "title": "条件与现象", "case_ids": ["CASE-001"],
    "reproduced_platforms": [{"platform": "local-desktop", "build": "实际构建"}],
    "steps": [], "expected": "依据已确认规则", "actual": "实际观察",
    "evidence": ["evidence/actual-shot.png"],
    "submission_state": "local_only", "remote_id": null, "url": null
  }
}
```

没有截图但有足够的日志/文件证据时不强行补造截图。事实尚不确定的问题单列待验证发现，不将其混入已确认缺陷数量。


## 暂停与交还记录

每次交还使用 `handoff` 保存最近一次状态，并将先前记录追加到 `handoff_history`，不覆盖历史。

- `state`：`not_started/restoring/incomplete/verified`；仅配置恢复、进程清理和停止后的客户端验证均有证据时取verified。
- `trigger/checkpoint/affected_platforms`：暂停、结束或交还的原因、续测断点及受影响平台。
- `configuration_restoration`：每条目标、基线、恢复实际值、结果、证据；未改变项注明未改变。
- `owned_process_cleanup`：本轮进程/端口、停止或释放的实际结果及证据；无进程也明确说明。
- `client_checks_after_cleanup`：平台、客户端/构建、清理完成时间、之后的实际操作时间/操作、观察结果及证据。操作需晚于依赖进程停止，不能复用停止前截图。
- `residual_impact/verified_at`：未解决影响、接管方法；验证全部通过才记录verified_at。

这些字段是现场核验记录，统计脚本不自动证明真实UI恢复。交还状态不能从用例通过率或一轮遍历完成推导。


## 执行范围快照

`execution_scope` 保存本轮解析后的 `requested_scopes`、`combination`（union）、`filters`（模块、平台、显式优先级等交集限制）、`selection_basis`、`selection_state`（pending_confirmation/confirmed）和`confirmation_ref`。默认范围是functional；明确范围缺少标签/清单时不伪造选择依据。

范围选择由执行者按scope参考文档完成；统计脚本校验最终纳入/排除清单，不解析自然语言、不自动选冒烟或推导回归影响。`special_test_scope` 保留专项启用类别，兼容性请求或指定专项编号的启用也记录于此。

Excel与报告保留输入总数、本轮纳入数、范围外总数及其中专项数，并展示筛选依据。筛选只变更本轮副本，不删除原用例；执行开始后扩缩范围需用户依据和新的快照，不能以环境不足为由缩小范围美化结果。
