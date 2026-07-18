# 官方技术学习文档格式检查证据

> 历史快照：本目录保留 2026-07-12 至 2026-07-13 的 202 章原始结果，不回写为当前数字。
> 现行 210 章结果见 `../content_quality_audit_2026-07-18/official_docs_structure.json` 与
> `../content_quality_audit_2026-07-18/official_docs_chapter_matrix.csv`。
>
> 首次生成：2026-07-12；最近刷新：2026-07-13
> 范围：22 份现行教材、202 个可识别章节
> 明确排除：学习者试学、本人复现、前后测、迁移测验和延迟保持

## 文件

- `official_docs_structure.json`：模块入口、章级显式结构信号、候选内容类型和复核标记。
- `chapter_matrix.csv`：202 行逐章矩阵，便于筛选和排序。
- 主报告：`00_路线总控/审计与整改/09_权威技术学习文档格式对标与教材内容检查_2026-07-12.md`。

## 快照

- 模块入口显式信号：受众、前置、范围、版本、预计用时、产物、完成检查、导航和内容类型
  均为 22/22。预计用时是作者侧初步估计，不是学习者实测或发布门禁。
- 章级显式标题信号：上下文 136/202、过程 111/202、预期结果 136/202、排错 124/202、
  总结 25/202、下一步 18/202、前置 13/202、清理 4/202。
- 既有教学角色信号：目标 158/202、worked example 62/202、反例 130/202、练习 125/202、
  验收 142/202、章内来源 51/202。
- 内容类型为 `instructional` 158 章、`workbook` 2 章、`reference` 4 章、`design-note` 27 章、
  `appendix` 11 章；`unclassified` 和类型冲突均为 0。
- 在 158 个 `instructional` 章内，显式目标为 135、worked example 61、反例 112、练习 108、
  验收 121、章内来源 39。这些是后续人工复核排序信号，不是教学质量得分。
- 章内共有 1415 个代码围栏，49 个具有显式 `textbook-code` 角色，1366 个尚未标记。
- 本快照已包含 2026-07-12 Wave 0 事实/契约修复、Wave 1 入口/类型归类和 Wave 2 第一批
  八个高影响教学锚点章的闭环增强。第一批涉及 F01 第 1 章、F04 第 4 章、F05 第 3-4 章、
  M00 第 8 章、M01 第 12 章和 M02 第 7-8 章；没有因此把其余章节或学习者进度升级。
- 后续又增强 M00 第 7 章和 M01 第 7 章：前者用 HTTPX `MockTransport` 建立离线 HTTP/JSON
  正负链路，后者修正 `project_root` 层级语义并建立文件/JSON 往返和错误恢复；两章新增的
  18 个围栏均有显式角色。该增量仍只授予作者侧结构与可执行证据，不代表全书成熟。
- M02 第 2、4、9 章随后补资源决策、八类 Pydantic 正负输入和创建/查询/metrics 状态观察，
  并校正 E02/P03 图示边界、fixture teardown 证据口径、UUID/UTC 断言与就近安全/队列来源。
- E02 reference 当前包含 9 个运行时 API 契约用例和 1 个 OpenAPI schema 用例，实跑结果为
  `10 passed`；该结果只证明 reference 可执行，不代表学习者已经完成实验。
- 本轮完整门禁为七套 reference `82 passed`、内容审计 blocker 0、30 份含 Mermaid 文档
  渲染失败 0；这些仍不代表学习者完成或全库已经 `content-reviewed`。

## 解释限制

自动结果只识别显式标题、编号步骤、代码角色和本地元数据。缺少标题不等于正文完全没有相同
语义，有标题也不证明步骤正确、示例可运行或来源支持主张。逐章内容结论以主报告中的人工复核
为准，任何计数都不解释为规范符合率、学习效果或官方认证。

预计时长、统一占位符样式和固定代码行宽没有作为通过条件：不同官方项目对此采用不同 house
style。检查器只保留跨 Microsoft Learn、Google、Kubernetes、Python 和 GitHub Docs 稳定的
内容结构候选。

## 复现

```powershell
py -3.13 .\00_路线总控\审计与整改\tools\content_quality\analyze_official_docs_structure.py `
  . `
  .\00_路线总控\审计与整改\artifacts\content_quality_audit_2026-07-11\pedagogy_analysis.json `
  .\00_路线总控\审计与整改\artifacts\official_docs_content_audit_2026-07-12\official_docs_structure.json `
  .\00_路线总控\审计与整改\artifacts\official_docs_content_audit_2026-07-12\chapter_matrix.csv
```
