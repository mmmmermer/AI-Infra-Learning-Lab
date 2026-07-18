# 教材内容优化任务矩阵状态证据审计

审计日期：2026-07-18

审计对象：`11_教材内容优化任务矩阵.csv` 的 110 个任务，以及
`optimization_matrix_status_evidence.csv` 的 34 条非 `planned` 状态证据。

本报告中的状态表示**整改任务自身**的验收状态，不表示学习者已经完成、整个模块已教学就绪，
也不表示 reference 已在生产拓扑、真实模型或所有平台上验证。教材示例、作者侧 reference 验收、
学习者复现和生产环境证明仍须分别陈述。

## 判定规则

- `completed`：任务自身的 acceptance 已有直接、可解析的仓库证据，且所有 ID 型前置均为 `completed`。
- `in-progress`：已有直接产物，但 acceptance、测试范围或 ID 型前置仍有明确缺口。
- `blocked`：外部资源或环境阻断已确认，原因和当前证据边界有文件记录。
- `planned`：尚未形成足以改变任务状态的验收闭环；现有背景材料不等同于完成证据。
- `cancelled`：仅用于已有明确替代决策且不再执行的任务；本轮没有此类任务。

## 状态汇总

| 状态 | 数量 | 判定 |
|---|---:|---|
| `completed` | 24 | Wave 0 十项、矩阵治理一项及本轮独立验收的十三项 |
| `in-progress` | 8 | 已有实现或治理产物，但仍缺完整 acceptance 或前置 |
| `blocked` | 2 | 真实 vLLM 与 Triton 执行环境或证据缺失 |
| `planned` | 76 | 尚未发现满足任务验收的新闭环产物 |
| `cancelled` | 0 | 无明确取消决策 |

总计 110 项。证据表逐项覆盖全部 34 个非 `planned` 任务，无重复 ID；矩阵和证据状态一致。

## P0 结果

矩阵共有 14 个 P0 任务：

- `completed` 13 项：`W0-001` 至 `W0-010`、`M02-002`、`M04-002`、`M06-003`。
- `in-progress` 1 项：`M03-004`。

`M03-004` 保留进行中是必要边界：当前 Mock/reference 能证明 untrusted context 结构、ACL/cache、
对抗 corpus、删除生命周期与脱敏审计，但不能证明任意真实模型在 generation 阶段抵抗间接注入。

## 已完成

### Wave 0 与治理

`W0-001`、`W0-002`、`W0-003`、`W0-004`、`W0-005`、`W0-006`、`W0-007`、
`W0-008`、`W0-009`、`W0-010`、`PLAN-001`。

其中 `W0-009` 的完成方式是收缩发布范围并明确证据边界，不是完成真实 GPU、vLLM 或 Triton 实验。

### 本轮独立验收

| 任务 | 完成依据 | 证据边界 |
|---|---|---|
| `M00-001` | 进程、退出码、信号、权限和超时回收教材及 E00 reference 闭环 | Windows fixture 不替代 POSIX/容器外部 SIGTERM 复验 |
| `M00-002` | DNS/TCP/TLS/HTTP 单变量故障矩阵及后续层不执行断言 | 注入 fixture 不证明真实网络、代理或证书配置 |
| `M01-003` | thread/process/asyncio 选择、阻塞反例、取消和资源释放测试 | 小 fixture 不外推为生产性能 benchmark |
| `M02-001` | request_id、middleware、DI、service/repository 和错误链路贯通 | reference 身份映射不替代生产身份提供方 |
| `M02-002` | server-owned Principal、tenant/owner scope 及读写、列表、metrics、日志负测 | 完成的是教材/reference 认证授权边界 |
| `M02-003` | 自包含问题详情 schema、pagination、429、readiness、pool 恢复及 OpenAPI 引用验证 | 内存依赖 fixture 不替代真实数据库池容量验证 |
| `M02-004` | deadline 无幽灵写、幂等并发只提交一次、scope 隔离与 version CAS | 不声称覆盖所有客户端断连和多进程数据库竞态 |
| `M03-001` | 同一黄金集比较 lexical/vector/hybrid，Recall@k、MRR、nDCG、原始排名与失败分类可复算 | 固定教学 corpus 不代表生产检索效果 |
| `M04-001` | 76 项 deterministic reference 覆盖 strict schema、有限循环、审计、显式取消和副作用竞态 | 单进程、无真实模型、无网络，不外推为生产 Runtime |
| `M04-002` | capability/resource、默认拒绝 egress/path、SSRF/遍历/symlink 与不可信输出负测 | 内存 handler 不证明真实外部副作用系统配置 |
| `M06-001` | constraint、migration、索引计划、锁恢复及 PostgreSQL 17.9 deadlock artifact | 一次本机隔离集群不代表 CI 或生产拓扑 |
| `M06-002` | crash-point 投递语义、fencing、有限退避与 jitter 教材及 executable reference | 明确不承诺无法证明的 exactly-once |
| `M06-003` | owner/version/lease fencing、恢复预算、迟到写拒绝和状态事件证据，且 M06-001/002 前置完成 | P03 跨项目证据仅用于对应契约，不替代 E06 FastAPI 集成 |

每项的逐文件 reason 和 evidence path 见 `optimization_matrix_status_evidence.csv`。

## 进行中

| 任务 | 已有产物 | 仍缺条件 |
|---|---|---|
| `PED-007` | M05 已拆为 13 章并建立答案或结果索引 | 其他长章、锚点迁移和全库答案隔离 |
| `PED-011` | provenance/license 台账和校验器 | 其余 review-required 条目和仓库根许可决策 |
| `PED-012` | 版本 manifest、时效阈值和校验器 | 明确 owner、Pydantic 复核及 blocked 组件处理 |
| `M03-002` | 文本 ingestion failure matrix、版本、retention、删除与缓存失效测试 | PDF/Office/OCR/表格等多格式 fixture 和解析质量报告 |
| `M03-003` | 检索失败分类、prompt 结构和引用字段基础 | answer rubric、拒答集和逐引用核对 artifact |
| `M03-004` | Mock 对抗 corpus、untrusted context、ACL/cache、生命周期和脱敏审计 | 真实模型 generation 抗间接注入证据；`M03-002` 前置仍未完成 |
| `M04-003` | version transition、审批 CAS、outbox/claim、迟到 finalize 与 cancel fence | reducer/checkpoint/replay、乱序或重复事件和跨进程恢复 |
| `M06-005` | database-only 与 P03 end-to-end 范围已分开，P03 有 worker fixture | E06 自有 FastAPI 集成及 `M06-004` 缓存前置 |

这些任务不得因相邻 reference 已通过而自动升格。

## 资源阻挡

- `M10-004`：缺满足验收的 Linux/WSL、GPU/驱动、固定模型 revision 和真实 vLLM benchmark。
- `M10-005`：缺 Triton model repository、dynamic batching、metrics 和真实执行记录。

E10 合成 simulator、章节说明或版本清单均不能替代两项真实 serving 证据。

## 保持计划

以下 76 项保持 `planned`。表中原因是任务组仍未形成的主要闭环；每项的具体 artifact 和
acceptance 仍以矩阵原行为准。

| 任务组 | 任务 ID | 数量 | 保持计划的直接原因 |
|---|---|---:|---|
| 教学一致性 | `PED-001` 至 `PED-006`、`PED-008` 至 `PED-010` | 9 | 围栏角色、答案隔离、claim-source、walkthrough、故障链、变式题、术语和可访问性未全库闭环 |
| M00 | `M00-003` | 1 | 资源与服务诊断 capstone 尚未落地 |
| M01 | `M01-001`、`M01-002`、`M01-004` | 3 | packaging、lint/type/test 和 profile/内存闭环未落地 |
| M02 | `M02-005` | 1 | 签名凭据、TLS/CORS 与 secret rotation 未闭环 |
| M04 | `M04-004` | 1 | 固定 Agent eval set、policy case 和成本或延迟报告不存在 |
| M05 | `M05-001` 至 `M05-004` | 4 | 队列桥接、饥饿实验、稳健 workload 与资源向量实验未闭环 |
| M06 | `M06-004`、`M06-006` | 2 | 安全 cache reference 与备份恢复或迁移回滚未闭环 |
| M07 | `M07-001` 至 `M07-003` | 3 | 五服务拓扑、生命周期故障和供应链实验未闭环 |
| M08 | `M08-001` 至 `M08-005` | 5 | OTel、Prometheus、可重复 workload、关联诊断和事件响应未闭环 |
| M09 | `M09-001` 至 `M09-005` | 5 | probe/资源、安全持久性、HPA/KEDA、双节点调度和 TLS/Secret 生命周期未闭环 |
| M10 | `M10-001`、`M10-002`、`M10-003`、`M10-006` | 4 | 显存预算、过载或取消、策略比较和可重建模型 manifest 未闭环 |
| M11/RQ01 | `M11-001` 至 `M11-011` | 11 | 检索协议、estimand、设计、样本量、稳健性、伦理、因果和研究包未闭环 |
| 金融 F00-F08 | `F00-001` 至 `F08-001` 中全部 24 项 | 24 | 公司行动、统计或数值、时序、组合、风险、衍生品、曲线、回测、ML 与任务激活缺口仍在 |
| 金融 AI 场景 | `M12-001` | 1 | 场景威胁模型、人工复核 rubric 与激活条件未形成独立验收包 |
| 跨模块基础 | `DS-001`、`EVAL-001` | 2 | 时钟/deadline 实验与统一 AI 评测基础章未落地 |

`M00-003`、`M06-004` 和 `M06-006` 均明确保持 `planned`；未用相邻任务完成状态替代其独立 acceptance。

## 校验结果

执行：

```powershell
py -3.13 .\00_路线总控\审计与整改\tools\validate_optimization_matrix.py .
```

结果：`passed`。校验器确认 110 行、17 列、110 个唯一任务、172 条 ID 型依赖、0 个循环、
0 个错误；34 条非 `planned` 状态均有唯一证据记录，引用路径均位于仓库内且可解析。
保留 14 项描述型外部前置警告，它们不是悬空任务 ID。
