---
type: flutter-test-changes
run_id: "{{run_id}}"
date: "{{date}}"
tags:
  - testing/flutter
  - testing/changes
---

# {{run_id}} 源码与配置改动记录

[测试报告](report.html)

## 变更基线

- 分支与提交：{{source_baseline}}
- 执行前已有差异：{{preexisting_diff}}
- 本轮应用源码改动：{{application_change_summary}}

## 文件清单

| 文件 | 分类 | 操作 | 变更编号 | 最终状态 | 验证结果 |
| --- | --- | --- | --- | --- | --- |
| {{file_link}} | {{file_category}} | {{file_operation}} | {{change_id}} | {{retained_or_reverted}} | {{validation_result}} |

## 变更详情

### {{change_id}}

| 字段 | 内容 |
| --- | --- |
| 文件及符号/控件 | {{change_location}} |
| 分类 | {{change_category}} |
| 关联用例 | {{related_cases}} |
| 修改原因与必要性 | {{change_rationale}} |
| 修改内容 | {{change_description}} |
| 行为及状态影响 | {{impact_assessment}} |
| 验证与证据 | {{validation_evidence}} |
| 最终状态 | {{change_final_state}} |
| 单项撤销方式 | {{targeted_revert_steps}} |
| 撤销后的测试影响 | {{revert_impact}} |

差异片段：

```diff
{{focused_diff}}
```

## 依赖与启动配置

- 依赖变化及用途：{{dependency_changes}}
- 锁文件核对结果：{{lockfile_review}}
- Driver 入口、开关及平台限制：{{driver_configuration}}
- 其他环境配置变化：{{environment_changes}}

## 差异核对

- 业务逻辑变化：{{business_logic_review}}
- 既有改动保留情况：{{baseline_preservation}}
- 无关格式化及生成文件变化：{{unrelated_diff_review}}
- 未验证影响：{{validation_gaps}}
