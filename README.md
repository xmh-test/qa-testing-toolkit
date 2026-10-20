# QA Testing Toolkit

面向中文软件测试工作流的 Codex/ChatGPT 插件集合，提供从需求分析到测试资产导出的完整链路。

## 包含的 skills

| Skill | 用途 |
| --- | --- |
| `requirements-analyst` | 分析 PRD 和需求，输出可追溯的测试设计输入与需求缺口 |
| `ui-test-designer` | 仅有 Figma/HTML 设计稿时，提取测试功能和证据，衔接常规用例生成 |
| `test-plan` | 生成或更新结构化测试计划 |
| `test-case-generator` | 生成或更新 JSON V3 常规测试用例及总结 |
| `test-case-reviewer` | 评审用例结构、覆盖、可执行性及业务规则依据 |
| `test-case-to-sheets` | 将测试用例 JSON 转换为本地 Excel 文件 |

## 安装

添加公开 marketplace：

```bash
codex plugin marketplace add xmh-test/qa-testing-toolkit
```

安装并启用插件：

```bash
codex plugin add qa-testing-toolkit@qa-testing-toolkit
```

安装后请新建一个 Codex 任务，让新任务加载插件中的 skills。

建议只保留一种技能来源；若工作区还有同名独立技能，应同步更新或移除旧副本，避免加载不同规范。

## 0.3.0：仅有 UI 设计稿

使用示例：“没有 PRD，请根据这些 Figma 页面（或 HTML 原型）提取测试功能，编写测试用例并导出 Excel。”

新技能按六个维度提取：页面入口、用户目标、操作反馈、数据约束、状态分支、对象影响。按独立目标聚合功能，不将控件机械转成用例。规则标注已明确、部分明确或待确认，并保留节点/文件证据。

默认交付 UI 测试依据；要求用例时继续生成 V3 JSON 与总结，Excel 按需导出。仅提取请求不自动生成全部产物，既有 PRD 流程不变。

本技能负责测试设计，不执行程序或判断界面还原度。HTML 实现不能作为验证自身正确性的唯一基准。Figma 读取依赖可用连接器和权限；访问不足时说明可读范围。

## 数据与工作流

六个技能按用户任务选用，不强制跑完整链路。默认生成 JSON 明细和 Markdown 总结，内部自检不额外输出评审报告；Excel 按需导出。

新数据使用 V3：13 个用例字段，Excel 为序号加 13 列。标题使用 `【功能分类】【场景摘要】核心操作，预期结果`，一条用例围绕一个独立验证目标。

不再提供专项场景/数据集设计、关联字段、覆盖过滤及专项 Excel 列。保留旧版纯常规 V1/V2 的只读导出兼容；旧版混合资产明确报错、不静默删减。旧文件升级默认另存 V3，不覆盖历史资产。旧版输入只保留最小兼容识别逻辑。

生成器、评审器、导出器共享数据校验；结构通过不代表业务覆盖完整。技能应整体安装，不能单独复制依赖共享脚本的导出器。

开发回归检查：

```bash
python3 -m unittest discover -s tests -v
```

## 更新

```bash
codex plugin marketplace upgrade qa-testing-toolkit
codex plugin add qa-testing-toolkit@qa-testing-toolkit
```

## 目录结构

```text
.
├── .agents/plugins/marketplace.json
└── plugins/qa-testing-toolkit/
    ├── .codex-plugin/plugin.json
    └── skills/
```

## 作者

Xu Minghong — xuminghong@miniscloud.com
