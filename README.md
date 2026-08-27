# QA Testing Toolkit

面向中文软件测试工作流的 Codex/ChatGPT 插件集合，提供从需求分析到测试资产导出的完整链路。

## 包含的 skills

| Skill | 用途 |
| --- | --- |
| `requirements-analyst` | 分析 PRD 和需求，输出可追溯的测试设计输入与需求缺口 |
| `test-plan` | 生成或更新结构化测试计划 |
| `test-case-generator` | 生成常规功能点测试用例 JSON V2 和测试总结 |
| `test-bdd-ddt-designer` | 设计完整、独立的 BDD 场景与 DDT 数据集 |
| `test-case-reviewer` | 评审功能、API、E2E、BDD 和 DDT 测试资产 |
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
