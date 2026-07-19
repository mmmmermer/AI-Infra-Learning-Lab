# 教材内容优化任务矩阵状态证据审计

审计日期：2026-07-19

审计对象：`11_教材内容优化任务矩阵.csv` 的 110 个任务、
`optimization_matrix_status_evidence.csv` 的 34 条非 `planned` 状态证据，以及本轮 E03
多格式 ingestion/lineage/generation 与 E04 reducer/checkpoint 验收候选。

本报告只判定**整改任务自身**是否达到 acceptance。它不表示学习者已经完成、整个模块已
`instructional-ready`，也不表示 reference 已在生产拓扑、真实模型、真实 OCR 或所有平台上验证。
教材内容、作者侧 reference、学习者复现和生产环境证据继续分轴陈述。

## 判定规则

- `completed`：任务 acceptance 有直接、可解析、可重复的仓库证据，且所有 ID 型前置均为
  `completed`。
- `in-progress`：已有直接产物，但 acceptance、测试范围或前置仍有明确缺口。
- `blocked`：外部资源或环境阻断已确认，原因与当前证据边界有文件记录。
- `planned`：尚未形成足以改变任务状态的验收闭环；背景材料和相邻任务不能代替本任务证据。
- `cancelled`：仅用于已有明确替代决策且不再执行的任务；本轮没有此类任务。

## 状态汇总

| 状态 | 数量 | 本轮变化 |
|---|---:|---|
| `completed` | 26 | `M03-002`、`M04-003` 从 `in-progress` 升格 |
| `in-progress` | 6 | `M03-004` 仍保留，未被离线 evaluator 冒充为真实模型证据 |
| `blocked` | 2 | 无变化 |
| `planned` | 76 | 无变化 |
| `cancelled` | 0 | 无变化 |

总计 110 项。非 `planned` 数仍为 34，证据表逐项一一对应，无重复 ID。

## P0 结果

矩阵共有 14 个 P0 任务：

- `completed` 13 项：`W0-001` 至 `W0-010`、`M02-002`、`M04-002`、`M06-003`。
- `in-progress` 1 项：`M03-004`。

`M03-004` 继续进行中是有意的证据边界。当前 reference 能验证不可信 context 结构、检索前
ACL、cache scope、poison/unauthorized observation、敏感日志最小化、lineage 删除和 simulated
generation 输出规则；它没有可信 adapter 捕获并绑定的真实模型 raw response，不能证明真实模型
在 generation 阶段抵抗间接注入。

## 本轮升格：M03-002 与 M04-003

`M03-002` 的 acceptance 是：损坏、空白、重复和过期文档有确定状态，且删除后不可被检索或
缓存命中。本轮证据已把该闭环从理想文本扩展到受控多格式 reference：

| 验收面 | 直接证据 | 明确边界 |
|---|---|---|
| 多格式 fixture | text/Markdown、HTML 隐藏标签栈、CSV/TSV、DOCX、XLSX、born-digital、blank、image-only、mixed、inline/nested/shared Form、继承资源、循环图与 unused-XObject PDF，另有 OCR provider 路由 | 不证明复杂版式或真实 OCR 精度；无 provider 时不猜 OCR |
| 损坏与资源限制 | media type/签名、HTML 受限 tokenizer/隐藏子树、独立 XHTML namespace/XML、Office relationship/content type/root QName、DTD/entity、ZIP CRC/read、负 shared-string index、bytes/provider-page/cell/展开量负测 | parser 仍同步运行在进程内，HTML 路径不计算 CSS/ARIA/浏览器 DOM；生产必须加受限 worker、HTML5 sanitizer/renderer、超时和资源隔离 |
| 解析质量 | raw/parsed SHA、版本、locator fingerprint、字符/页/表/单元格计数、marker recall 与白名单 warning | 普通 SHA-256 不是匿名化，报告不能替代 telemetry 访问控制和保留期 |
| 生命周期 | 版本、重复、过期、单调 retention watermark、锁外慢解析与提交 CAS、collection version、tombstone-first | 当前状态在内存中，不证明重启后恢复或分布式原子性 |
| 删除与 cache 传播 | raw、parsed、chunk、vector、cache、prompt、output、citation lineage 级联失效；cache generation 变更传递失效后代；中途失败可幂等续删 | 不证明对象库、数据库、向量库、模型提供方或备份已物理擦除 |
| 授权可观测性 | active documents、artifact inventory 与 retention 清理先校验 `rag:query`、tenant、permission group，未授权时不泄露存在性或产生副作用 | 假定上游已提供可信 `Principal`，不是令牌认证实现；时间必须由服务端注入 |

严格 E03 回归为 `154 collected / 154 passed`，`pip check` 通过，锁文件 dry-run 可满足；测试同时以
`-X dev -W error::ResourceWarning` 运行，未用 skip 或 xfail 掩盖资源告警。

因此，`M03-002` 只在“离线教材 reference 与 provider adapter contract”范围内完成。生产 parser
沙箱、真实 OCR、外部存储删除回执和进程重启恢复不是该升格的隐含结论。

`M04-003` 的 acceptance 是事件转换原子、重放确定，以及取消后迟到 completion 不改变终态。
本轮新增 `task-reducer/v1` 和事件 schema v1：批次按可信 sequence 排序，同 sequence 同 fingerprint
幂等忽略、内容冲突拒绝；状态事件 task version 必须严格递增，观察事件保持版本；checkpoint 绑定
reducer/schema、最后事件 fingerprint 和状态 SHA-256。10 个新增用例直接覆盖 owner cursor、乱序、
重复、冲突、version gap、增量恢复、摘要篡改、版本不兼容、混合 task 和取消后迟到完成。

严格 E04 回归为 `86 collected / 86 passed`。这只完成本地确定性 reducer/checkpoint 任务；没有
数据库事件表、持久 checkpoint store、跨进程 crash recovery、broker delivery 或外部副作用对账，
因此不能把 `M04-003 completed` 解读为生产 Agent Runtime 已完成。

## 继续进行

| 任务 | 已有产物 | 仍缺条件 |
|---|---|---|
| `PED-007` | M05 已拆为 13 章并建立答案或结果索引 | 其他长章、锚点迁移和全库答案隔离 |
| `PED-011` | provenance/license 台账与校验器 | 34 个 `review-required` 条目和仓库根许可证决策 |
| `PED-012` | 版本 manifest、时效阈值与校验器 | 明确 owner、Pydantic 复核及 blocked 组件处理 |
| `M03-003` | 检索失败分类、prompt 结构、离线 citation 存在性/quote 匹配基础 | answer rubric、拒答集和逐引用 entailment 核对 artifact |
| `M03-004` | 离线对抗 corpus、ACL/cache、lineage 删除、脱敏报告和 simulated generation evaluator | 可信真实模型输出绑定与重复对抗运行 |
| `M06-005` | database-only 与 P03 end-to-end 范围分离，P03 有 worker fixture | E06 自有 FastAPI 集成及 `M06-004` 缓存前置 |

相邻 reference 通过不会自动升格这些任务。

## 资源阻挡

- `M10-004`：缺满足验收的 Linux/WSL、GPU/驱动、固定模型 revision 和真实 vLLM benchmark。
- `M10-005`：缺 Triton model repository、dynamic batching、metrics 和真实执行记录。

E10 合成 simulator、章节说明或版本清单均不能替代真实 serving 证据。

## 仍计划的 76 项

76 项 `planned` 的任务组和数量相较 2026-07-18 审计没有变化：教学一致性 9、M00 1、M01 3、
M02 1、M04 1、M05 4、M06 2、M07 3、M08 5、M09 5、M10 4、M11/RQ01 11、金融
F00-F08 24、金融 AI 场景 1、跨模块基础 2。

它们继续以矩阵各行的 `expected_artifact` 与 `acceptance` 为准；本轮 E03 代码增加不能替代这些
独立任务的证据。

## 校验入口

```powershell
py -3.13 .\00_路线总控\审计与整改\tools\validate_optimization_matrix.py .
.\00_路线总控\审计与整改\tools\run_full_validation.ps1
```

发布结论必须以 2026-07-19 同一候选提交上的无跳过完整门禁 artifact 为准；旧的
`full_validation_2026-07-18` 只保留为历史证据，不能替代本轮验证。
