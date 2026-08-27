---
name: test-case-to-sheets
description: 将 test-case-generator 或 test-bdd-ddt-designer 生成的 V1/V2 JSON 测试用例转换为本地 Excel（.xlsx）。默认导出全部常规、BDD、DDT 和混合模板用例；用户要求排除已完整覆盖的常规原子用例时，使用 --exclude-covered-atomic 并从 Feature/DDT JSON 读取覆盖关系。
---

# 测试用例 JSON 转 Excel

使用内置 scripts/json_test_cases_to_excel.py 将 JSON 明细转换为 Excel。默认输出到 JSON 同目录、同名 .xlsx；MD 总结不是数据源。

# 输入定位

1. 优先使用用户明确提供的 JSON。
2. 用户给目录时，定位目录下最新 测试用例_*.json。
3. 未指定时，依次搜索输入所在测试根目录、工作区、4-test_cases/、test_cases/。
4. 支持 V1 顶层数组与 V2 schema_version=2.0 根对象中的 cases。

# 默认全量转换

    python3 scripts/json_test_cases_to_excel.py <测试用例JSON>

默认导出：

- 常规原子用例。
- BDD 完整流程用例。
- DDT 模板用例。
- BDD+DDT 参数化流程用例。
- 已被 full 覆盖的常规原子用例。

指定输出时应保持在 JSON 同目录：

    python3 scripts/json_test_cases_to_excel.py <测试用例JSON> -o <同目录输出.xlsx>

# 排除完整覆盖的常规原子用例

只有用户明确要求时启用：

    python3 scripts/json_test_cases_to_excel.py \
      <测试用例JSON> \
      --exclude-covered-atomic

脚本默认从 metadata.artifacts.bdd 与 metadata.artifacts.ddt 读取覆盖文件。显式路径优先：

    python3 scripts/json_test_cases_to_excel.py \
      <测试用例JSON> \
      --exclude-covered-atomic \
      --feature <BDD.feature> \
      --ddt <DDT.json>

过滤条件必须全部满足：

- case ID 位于 Feature @covers-full-* 或 DDT coverage.full_case_ids。
- design_methods 严格等于 [\"functional-point\"]。
- case ID 不在任何 partial 覆盖集合。

BDD、DDT、BDD+DDT 模板、partial 覆盖和未覆盖用例始终保留。没有 full 覆盖项时正常导出全部，排除数为 0。

# Excel 列

V1 保持原 10 列：序号及 9 个旧字段。V2 在其后追加：

- 用例ID、需求编号、验收标准编号、功能点编号。
- 设计方法、BDD场景ID、DDT数据集ID、DDT数据行ID。
- 资产类型、覆盖关系、执行建议。

数组统一使用 | 分隔，包括 tags。新增展示规则：

- full 覆盖原子：已被完整覆盖，可跳过。
- partial 覆盖原子：部分覆盖，仍需执行。
- BDD/DDT/混合模板：专项用例，执行。
- 无覆盖：执行。

# 安全失败

启用 --exclude-covered-atomic 后不得静默降级：

- V1 没有稳定 case ID：停止。
- 声明或显式指定的 Feature/DDT 缺失、无法解析：停止。
- 覆盖关系引用未知 case ID：停止。
- 同一 case 同时 full 与 partial：停止。
- full 指向 BDD/DDT 模板而非严格常规原子：停止。

所有校验在写入前完成，并通过临时文件原子替换输出。失败时不生成新的不完整 Excel。

# 输出与验证

成功输出：

    转换完成：总用例 120，排除完整覆盖原子用例 18，导出 102。
    输出文件：/absolute/path/测试用例.xlsx

Excel 保留换行、冻结首行、启用筛选并设置列宽。转换后验证：

    python3 -c "import zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); print(z.testzip())" <输出xlsx>
