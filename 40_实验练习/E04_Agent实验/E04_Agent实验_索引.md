# E04 Agent 实验索引

## 定位

E04 用于训练可控 Agent 工作流、状态机、能力式工具门禁、失败重试、人工确认节点和 session
隔离。模型只提出动作；身份、授权、审批与执行边界由服务端控制。

实验目标不是做复杂多 Agent，而是让 Agent 请求成为 P03 中可调度、可记录、可监控的 workload。

## Reference 状态

`e04_runtime_reference/` 已实现确定性内存版的 server-owned principal、capability/resource
授权、检索前 ACL、状态/步骤分离、审批目标绑定与 CAS、resume outbox/claim fencing、幂等副作用、
显式取消生命周期、默认拒绝的 URL/path validator、不可信输出边界、session 隔离和递归脱敏审计。
2026-07-18 在 Python 3.13 项目 `.venv` 运行结果为 `76 passed`、`0 skipped`。

该结果属于 `reference-verified`，不等于学习者已完成；它也不证明数据库事务、真实队列、模型
抗注入、生产策略引擎或 P03 `/agent/*` 集成。命令和边界见
[[40_实验练习/E04_Agent实验/e04_runtime_reference/README|reference README]]。

新增闭环的证据入口：

| 验收方向 | 测试文件 | 关键断言 |
|---|---|---|
| cancel 生命周期 | `tests/test_cancellation_and_injection.py` | CAS、`cancelled` 终态、pending approval/outbox 关闭、worker 不改写为 failed |
| 副作用栅栏 | `tests/test_cancellation_and_injection.py` | 共享 `effect_started` 原子栅栏决定跨 runtime 取消/handler 顺序，开始后拒绝假取消并可幂等 finalize |
| 重投与租户 claim | `tests/test_approval_workflow.py` | waiting approval 重投幂等，其他阶段无损拒绝；worker tenant scope 在领取前过滤并在执行时复核 |
| egress / SSRF | `tests/test_target_security.py` | 无 allowlist 默认拒绝；loopback、私网、link-local、metadata、userinfo、缺端口均不调用 handler |
| path | `tests/test_target_security.py` | `..`、单双重编码、绝对路径、盘符/UNC、解析后符号链接逃逸均不调用 handler |
| 不可信工具输出 | `tests/test_cancellation_and_injection.py` | 恶意 chunk 不改变 capability、proposal、审批与副作用次数 |
| trace | `tests/test_sessions_and_audit.py` | 嵌套 credential、URL、私有路径、完整 tool output 与后缀伪装字段不出现在序列化记录 |

## 实验闭环

```text
M03 RAG 工具
-> M04 Agent 工作流
-> AgentTask
-> M05 调度字段
-> M08 step log / metrics
-> P03 planned Agent v1
```

E04-01 到 E04-03 服务 P03 planned Agent v1：把 RAG 工具、多步骤状态、人工确认和失败处理做成可控 workload；当前 P03 v0.3.1 尚未接入 Agent。

E04-04 到 E04-07 服务 P03 post-v0.3.1 / vNext planned Agent Runtime：把 agent loop、session、context/memory、异步工具和 busy state 拆成可测试的 runtime 能力。二阶段实验是后续进阶入口，不表示当前 P03 已实现或学习者已经亲手完成。

## 推荐实验

| 实验 | 对应教材 | 目标 | 产出 |
|---|---|---|---|
| [[40_实验练习/E04_Agent实验/E04-01 工具调用最小实验|E04-01 工具调用最小实验]] | 第 2-3 章：工具调用、状态记录 | 用 server principal、capability 与检索前 ACL 把 M03 RAG 包装成受控工具 | workflow 图、严格 schema、负向测试、step_logs |
| [[40_实验练习/E04_Agent实验/E04-02 多步骤 Agent 状态流转实验|E04-02 多步骤 Agent 状态流转实验]] | 第 3-7 章：状态、固定工作流、调度字段 | 做 `retrieve_docs -> draft_report -> human_approval -> finalize_report` | 分离的 task status/current_step、状态图、恢复点 |
| [[40_实验练习/E04_Agent实验/E04-03 人工确认与失败处理实验|E04-03 人工确认与失败处理实验]] | 第 5-9 章：失败处理、人工确认、监控 | 处理 timeout、权限失败，并用目标绑定、CAS、expires_at、outbox 完成审批 | error_type 表、approval 契约、并发/过期测试 |

## 二阶段 Runtime 实验

以下实验用于承接 M04 第 10 章“最小 Agent Runtime”。E04-04、E04-05、E04-06、E04-07 均已有初版实验页；reference 只覆盖其中的确定性核心契约。它们不表示已经亲手完成实验，也不要求在正式学习前立刻执行。

| 实验 | 对应教材 | 目标 | 产出 |
|---|---|---|---|
| [[40_实验练习/E04_Agent实验/E04-04 最小 Agent Runtime 实现|E04-04 最小 Agent Runtime 实现]] | 第 10 章：agent loop / ToolRegistry / 输出解析 | 从零写一个最小 loop，支持直接回复、工具调用、解析失败和 max_turns | runtime 伪代码、ToolRegistry、基础测试矩阵 |
| [[40_实验练习/E04_Agent实验/E04-05 Session 隔离与多轮追问|E04-05 Session 隔离与多轮追问]] | 第 10 章：session / context | 验证 tenant/owner 隔离、CAS 与同一用户多窗口追问 | `session_id/version`、messages、所有权/并发/注入负向测试 |
| [[40_实验练习/E04_Agent实验/E04-06 Context 压缩与 memory 召回|E04-06 Context 压缩与 memory 召回]] | 第 10 章：context_summary / memory_hits | 设计基础摘要压缩和保守 memory 召回规则 | context 构造表、memory 召回记录、误召回案例 |
| [[40_实验练习/E04_Agent实验/E04-07 异步工具与 busy state|E04-07 异步工具与 busy state]] | 第 10 章：async tool / runtime_events | 处理长工具执行、新消息到达、工具完成事件和取消请求 | runtime 状态图、event 表、busy state 处理规则 |

## 最小练习路线

```text
先做固定检索-总结
-> 加 step 状态记录
-> 加失败类型和超时
-> 加人工确认
-> 把 AgentTask 字段接到 P03
-> 二阶段再进入最小 Runtime、session、context、memory 和异步工具
```

## 必须记录的内容

| 内容 | 用途 |
|---|---|
| task_id | 串起 API、worker、step log |
| step_name | 定位失败或慢步骤 |
| tool_name | 统计工具调用 |
| status | 表示步骤成功/失败/等待 |
| error_type | 失败分类 |
| duration_ms | 后续接 M08 |
| token_count | 后续接成本控制 |
| approval_status | 人工确认状态 |
| retry_count / max_retries | 连接 M06 失败重试 |
| timeout_ms | 连接 M05 超时控制 |
| current_step | 任务恢复和状态查询 |
| tenant_id / owner_user_id | server principal 的任务/session 归属快照，不来自业务请求 |
| version / workflow_version | CAS、旧页面/旧 worker 拒绝与恢复兼容性 |
| approval target / expires_at | 绑定草稿、动作和时限，防止批准后替换目标 |
| expected_version / cancellation event | 显式取消 CAS 与迟到 worker 栅栏；理由只记是否存在和长度 |
| egress origin / normalized path | 模型外执行目标策略；默认无策略即拒绝能力 |
| trust_label / redaction result | 不可信输出与递归 trace 脱敏证明 |

`status` 只表示任务生命周期（如 `running/waiting_approval/failed`），`current_step` 只表示业务
步骤（如 `retrieve_docs/human_approval/finalize_report`），不能创建 `retrieving/finalizing` 之类
把两种维度混在一起的状态。审批拒绝和过期统一进入 `failed`，错误码分别为
`approval_rejected`、`approval_timeout`；`cancelled` 只用于显式取消。

## 与 M03 的连接

E04 不重新学习 RAG，而是把 M03 的 RAG 检索作为 Agent 工具：

```text
M03: business input(query + collection_id + top_k)
+ server principal(tenant + effective ACL snapshot)
-> capability gate -> ACL prefilter -> retrieve_docs
-> chunks / retrieved_sources
-> M04 steps: draft_report / human_approval / finalize_report
```

身份和 permission groups 不能来自客户端或模型参数；额外身份字段必须 `422`。ACL 过滤发生在
候选计数、打分和重排之前。如果检索没有授权 `retrieved_sources`，Agent 不应该编造报告，而应
记录 `empty_result` 或 `no_citation`。RAG 文本和 tool output 始终是不可信数据，不能改写工具
policy、扩大 capability、关闭审批或触发副作用。

## 与 M05/M06/M08 的连接

| 模块 | E04 要提供的字段或行为 |
|---|---|
| M05 任务队列与调度 | `priority`、`timeout_ms`、`max_steps`、`estimated_duration_ms`、重新入队 |
| M06 数据库缓存与异步任务 | `status`、`current_step`、`retry_count`、`approval_status`、`step_logs` 持久化 |
| M08 监控压测与可观测性 | `step_duration_ms`、`tool_error_count`、`approval_wait_ms`、`agent_total_latency_ms` |

## 对应模块

- [[10_学习模块/M04_Agent工作流/M04_Agent工作流_学习地图|M04 Agent 工作流学习地图]]
- [[10_学习模块/M04_Agent工作流/M04_Agent工作流_适配教材|M04 Agent 工作流适配教材]]
- [[10_学习模块/M03_RAG工程/M03_RAG工程_适配教材|M03 RAG 工程适配教材]]
- [[10_学习模块/M05_任务队列与调度/M05_任务队列与调度_学习地图|M05 任务队列与调度学习地图]]

## 对应项目

- [[50_项目产出/P02_RAG_Agent_Service/P02_RAG_Agent_Service 项目主页|P02 RAG Agent Service]]
- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]

## 验收标准

- [ ] 能解释每个实验对应 M04 教材哪一章。
- [ ] 能说明 Agent 和普通 RAG 的区别。
- [ ] 能输出 AgentTask、AgentState、AgentStep 的最小结构。
- [ ] 能记录每一步日志和失败类型。
- [ ] 能说明 AgentTask 如何进入 M05 队列和 P03 worker。
- [ ] 能说明 `waiting_approval` 时为什么应释放 worker，确认后再重新入队。
- [ ] 能证明伪造身份、跨 tenant/owner、未授权工具、恶意 RAG/tool output 不会产生越权读取或副作用。
- [ ] 能用审批目标绑定、CAS、`expires_at` 和事务内 outbox 处理批准、拒绝、重复点击与过期竞态。
- [ ] 能用 tenant/owner/session/version 条件保证 session 隔离与并发更新不丢失。
- [ ] 能用 CAS 取消任务并同步关闭 pending approval/outbox；已知副作用执行后不能伪装取消成功。
- [ ] 能证明 SSRF/path 攻击在 handler 前被拒绝，恶意 tool output 不能升级为指令或扩大权限。
- [ ] 能证明 trace 不包含嵌套 credential、原始 URL、私有路径和完整工具输出。
- [ ] 能识别并避免 AutoGPT、多 Agent、强化学习 Agent、复杂规划算法等发散方向。
