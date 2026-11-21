# 测试平台的 Flutter 源码关联

仅当目标项目使用平台执行器的 `flutter_source` 扫描时应用此规则。执行器配置和部署由平台维护。

## 测试代码关联 JSON 测试用例

- 从正式 JSON 测试用例读取实际 `case_id`。在扫描配置覆盖的 Flutter 入口中，直接在 `main()` 调用 `testWidgets`，传入字面量名称和 `tags: ['acm-case-<case_id>']`。名称第一个词是该测试的稳定运行 ID，同一目标平台上必须唯一。
- 平台按执行器配置的模块和标签中的 `case_id` 关联。用例 ID 缺失或有歧义时记录待核对。只有用例标签也能完成用例关联。
- 当前扫描支持直接注册，带标记的动态循环、嵌套组、动态跳过或框架变体需要调整注册方式后再接入。保留原有运行语义，扫描无法确认时如实记录。

## 代码断言关联预期结果

- 在正式 JSON 用例的 `expected` 中使用已有的稳定预期 ID，例如 `1. [E01] 显示保存成功`。顺序和文案调整时，语义相同的预期保留原 ID。缺少 ID 时标为待补齐；修改正式用例须按任务授权处理。
- 在测试回调内复用执行器提供的 `acm_assertions.dart`，使用 `await acmCheck('E01', 'status-visible', () { expect(...); });`。前两个参数必须是字面量，分别表示预期 ID 和断言 ID。同一预期可对应多个断言，每个「预期 ID + 断言 ID」组合在该测试内唯一。
- 回调执行真实断言，关键断言保留清晰的中文 `reason`。辅助函数会输出通过或失败事件，失败继续抛出；未执行到的断言由平台显示为未执行。扫描只证明声明存在，运行状态以原生事件为准。

```dart
void main() {
  testWidgets('SAVE-01 displays the confirmation', (tester) async {
    await acmCheck('E01', 'status-visible', () {
      expect(
        find.text('保存成功'),
        findsOneWidget,
        reason: '保存完成后应显示成功提示',
      );
    });
  }, tags: ['acm-case-TC-FP001-001']);
}
```

用执行器的 `scan` 核对用例 ID、运行 ID 和断言引用。需要文件时，从扫描结果导出 JSON 或文档；新增、改名或删除测试后重新扫描。清单和映射无需人工或 Agent 维护，业务预期原文留在正式用例库。
