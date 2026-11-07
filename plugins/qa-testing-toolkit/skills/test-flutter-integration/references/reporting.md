# 本地报告数据与通用脚本

## 项目优先

已有运行器负责从 Flutter 原生 JSONL 解析结果、收集失败截图、保存重跑快照，并生成按平台统计的 HTML 时继续使用。不要为适配通用脚本改写既有历史结果或复制一份业务运行器到技能。

运行器路径、结果目录及仅重建报告的参数以目标项目为准。原生 JSONL 是执行证据，HTML 的中文说明可能来自程序提取或人工分析，需区分说明来源，推测不作为根因。

## 状态与统计口径

| 状态 | 含义 | 计入实际启动/通过 |
| --- | --- | --- |
| passed | 完成预定自动断言及必要清理 | 是/是，人工辅助另标 |
| failed | 断言或测试执行错误，附问题分类 | 是/否 |
| blocked | 无法完成验证，写明环境/能力/前置原因 | 只有 started=true 计入启动 |
| interrupted | 没有完整结束事件，不能沿用旧通过 | 依据 started/否 |
| skipped | 框架跳过且未实际验证 | 依据 started/否 |
| not_run | 已编写但未尝试 | 否/否 |
| not_implemented | 适用但尚未编写代码 | 否/否 |
| not_applicable | 原始用例不适用当前平台，需依据 | 否/否 |
| covered | 只关联其他用例，未独立验证 | 否/否 |

按当前模块/搜索/平台/结果范围分别统计。设计用例数按稳定 ID 去重；各平台运行数不能当作设计数量。每个平台每例只取最新尝试作当前结果，旧失败和重试仍可查看；没有完整结果的新尝试应显示 interrupted，不能回退为旧通过。未开始的构建失败也保存中断记录。

同时给出运行记录数、实际启动数、执行结果分布及尚无记录的覆盖分布；blocked 的尚无运行记录项称“环境前置”，已尝试项称“运行阻塞”。先根据当前筛选确定行集合再计算统计。

## 通用 HTML 输入

scripts/render_html.py 仅消费已解析且脱敏的数据，不执行用例、不解析不同版本的 Flutter 日志、不推断测试通过。需要时由当前运行器适配以下独立格式，保留原生证据，避免长期维护双份业务清单。

脚本从项目根目录运行，输出和证据均在该项目 reports/ 内。证据路径相对输入 JSON 所在目录；使用已有 PNG/JPEG 截图和文本/JSONL 日志，不复制到技能文件夹。attempts 按旧到新排列，最后一条为最新；平台名称不限 macos/android。

示例数据：

```json
{
  "schema_version": 1,
  "title": "客户端验收",
  "platforms": ["macos", "android"],
  "cases": [{
    "case_id": "CASE-001",
    "title": "新建文件",
    "module": "files",
    "steps": ["打开文件管理", "新建文件"],
    "expected": ["文件存在且内容正确"],
    "availability": {"macos": "not_run", "android": "not_implemented"},
    "notes": {"android": "尚未适配"}
  }],
  "attempts": [{
    "case_id": "CASE-001",
    "platform": "macos",
    "run_id": "RUN-001",
    "status": "failed",
    "started": true,
    "timestamp": "2026-11-04T08:00:00Z",
    "description": "已提交新建，但列表刷新后未找到目标文件。",
    "explanation_source": "检查点及实际结果整理",
    "category": "待定位",
    "error": "Expected file was not found",
    "log": "runs/RUN-001/native.jsonl",
    "screenshot": "runs/RUN-001/failure.png",
    "automation_mode": "automated",
    "manual_steps": []
  }],
  "issues": [{
    "local_id": "ISSUE-001",
    "case_ids": ["CASE-001"],
    "platform": "macos",
    "category": "待定位",
    "expected": "文件存在",
    "actual": "列表未显示文件",
    "attempt_count": 1,
    "submission_mode": "local_only"
  }]
}
```

automation_mode 使用 automated、host_assisted、manual_assisted；manual_steps 列出实际辅助动作和影响。失败、阻塞和中断必须提供 description；原始错误单独保留，不只堆日志。steps/expected 可为数组或文本。availability 还可指定 blocked、not_applicable 或 covered，notes 给原因。

本地问题可直接嵌在结果的 issues，或由项目现有 defects.json/问题文件保存并链接 HTML，不强制重复生成多种格式。记录步骤、预期、实际、证据引用、分类、发现时间及实际尝试次数；缺失项明确未知。不虚构飞书 ID 或归因。

## 检查范围

check_report.py 检查报告位于 reports/、本地证据未越出 reports/ 且存在、截图和日志链接在新选项卡打开。外部链接只做语法检查，不访问网络。额外核验界面统计、展开详情、原图和日志；脚本通过不能证明用例业务通过或报告视觉正确。
