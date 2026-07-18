# P03 AI Workload Platform 项目主页

> 当前状态（2026-07-18）：`内容 draft / 实现 executable v0.3.1 reference / Reference verified / 教学 partial / 学习者 not-evaluated`。`p03_service/` 当前完整套件为 27 tests，覆盖 memory、PostgreSQL/Redis Streams/outbox/独立 worker、任务所有权、租户隔离、权限前置 BM25 检索和 fixed-replay sender；另有随机化 1/2/4 worker × 3 次短时本机 reference 与 kind 功能证据。真实服务 fixed replay、LLM generation、Agent、学习者长时压测、Prometheus/tracing、Kubernetes 自动扩缩容/生产化和真实推理服务仍未完成。参考实现不等于本人完成。

## 项目定位

面向 RAG/Agent 请求的 AI 服务调度与监控平台。

这是当前路线的主项目，目标是同时服务工程学习、科研训练和就业展示。

## 核心问题

AI 请求来了以后，系统如何排队、调度、执行、监控，并在延迟、吞吐、成本、稳定性和公平性之间做权衡？

## 长期 target design（非现行 API）

下面八项是项目长期范围，不是 v0.3.1 已实现清单。当前可执行 HTTP surface、字段和边界以
`p03_service/README.md` 与 `03_API与数据契约.md` 为准。

1. 文档进入系统：上传、解析、切分、向量化。
2. 用户发起请求：问答、总结、报告生成。
3. 请求进入队列：记录用户、任务类型、优先级、预计耗时。
4. 调度器分配 worker：FIFO / Priority / SJF / 成本感知。
5. Worker 执行任务：RAG 检索、Agent 工作流、模拟推理。
6. 系统记录指标：等待时间、执行时间、P95、失败率、token 成本。
7. 管理端查看：任务状态、队列长度、worker 利用率、错误日志。
8. Docker 一键启动，后期 Kubernetes 部署。

## 当前 RAG retrieval reference 边界

当前 RAG 不是完整企业知识库产品，而是一个进入任务生命周期和监控主线的固定语料 workload。
文档上传、chunk/embedding 生命周期和 generation 仍属 target design。

RAG v1 需要能做到：

```text
Bearer token -> 服务端解析 principal
-> POST /tasks(task_type=rag_retrieval, input_json={query, top_k})
-> PostgreSQL 同事务写 task + outbox，并持久化 owner/permission snapshot
-> dispatcher XADD task_id
-> worker XREADGROUP + 数据库 CAS/fencing
-> tenant + permission group 前置过滤后执行固定语料 BM25
-> GET /tasks/{task_id} 返回 extractive answer + sources + metrics
```

RAG 任务至少记录：

| 字段 | 作用 | 来源模块 |
|---|---|---|
| query | 用户问题 | M03 |
| top_k | 1-5 个候选上限 | M03/E03 |
| server-owned principal snapshot | tenant/user/permission groups；请求体不可覆盖 | M02/M03/P03 |
| priority | 调度优先级 | M05 |
| queue_wait_ms | 队列等待时间 | M05/M08 |
| retrieval_ms | 检索耗时 | M03/M08 |
| retrieval_status / authorized_search_space_size | 授权搜索空间和空结果原因 | M03/E03 |
| answer_mode / quality_status | 明示确定性 extractive、非 LLM 评测 | M03 |
| sources | 授权来源 metadata 与分数 | M03/E03 |

M03 负责定义 RAG 请求、引用、评估和最小 worker 边界；M05 负责队列和调度策略；M08 负责指标、压测和可观测性；M06 负责后续状态持久化和异步执行。

## Agent v1 target design 边界

Agent workload 尚未接入 P03；本节只定义后续 target design，不是现行 API 或已验证能力。

Agent v1 需要能做到：

```text
POST /agent/report
-> 生成 AgentTask
-> 进入 Queue / Scheduler / Worker
-> retrieve_docs
-> draft_report
-> waiting_approval
-> approve 后重新入队
-> finalize_report
-> 返回 report + step_logs + metrics
```

Agent 和 RAG 的区别：

| 维度 | RAG 请求 | Agent 请求 |
|---|---|---|
| 步骤 | 检索 + 生成 | 多步骤工作流 |
| 工具 | retriever 为主 | retriever、draft、approval 等工具 |
| 状态 | 相对简单 | current_step、step_logs、artifacts |
| 失败 | 引用不准、检索为空、超时 | 工具失败、权限拒绝、人工拒绝、超步数 |
| 调度 | 可估计性较强 | 更需要超时、优先级、成本控制 |

Agent 任务至少记录：

| 字段 | 作用 | 来源模块 |
|---|---|---|
| task_type | `agent_report` | M04 |
| current_step | 当前步骤 | M04/M06 |
| max_steps | 防止无限执行 | M04/M05 |
| priority | 调度优先级 | M05 |
| estimated_duration_ms | 预计耗时 | M04/M05 |
| estimated_token_cost | 成本估计 | M04/M05/M08 |
| approval_status | 人工确认状态 | M04 |
| tool_call_count | 工具调用次数 | M04/M08 |
| error_type | 失败类型 | M04/M08 |

M04 负责定义可控 Agent 工作流、工具调用、状态、失败处理和人工确认；M05 负责队列、超时、优先级和成本控制；M06 负责状态持久化；M08 负责日志、metrics 和压测。

## M06 持久化与异步执行边界

P03 第一轮不要求做复杂数据库平台，但必须让任务不再只存在于内存里。

M06 负责把 RAG/Agent 请求落成下面的工程闭环：

```text
POST /tasks
-> PostgreSQL 同事务写 task(status=pending) + outbox
-> dispatcher 租约领取 outbox，更新 queued 并 XADD task_id 到 Redis Stream
-> worker XREADGROUP reserve task_id
-> PostgreSQL CAS/fencing：queued -> running
-> 执行 mock 或 permission-prefiltered RAG retrieval
-> owner/version/lease 校验后回写 result_json / error_type / metrics
-> 数据库终态成功后 XACK/XDEL
-> GET /tasks/{task_id} 按 owner 查询
```

第一版至少需要保存：

| 字段 | 用途 |
|---|---|
| task_id | 查询和追踪任务 |
| task_type | 当前为 mock_rag / mock_agent / simulated_inference / rag_retrieval |
| status | pending / queued / running / succeeded / failed / retrying / cancelled |
| input_json | 保存请求参数 |
| result_json | 保存 answer、sources、metrics |
| error_type | 保存稳定的失败分类 |
| idempotency_key | 防止重复提交 |
| created_at / queued_at / started_at / finished_at | 计算等待、执行和总延迟 |

`document_parse`、真实 `agent_report`、金融 workload、`step_logs`、`last_error` 和持久化重试计数仍是
后续契约，不属于 v0.3.1 已实现字段。`mock_agent` 只是确定性模拟 workload，不能据此声称 P03
已经实现 Agent Runtime。

## M07 Docker Compose 交付边界

P03 第一轮的容器化目标不是生产部署，而是本地可复现启动。

M07 负责把下面服务串成一个 compose：

```text
api: FastAPI 接口
db: PostgreSQL 或本地开发数据库
redis: 队列和缓存
dispatcher: outbox 到 Redis Streams 发布
worker: RAG / 异步任务执行
```

最小验收是：

```text
docker compose up --build
-> api 可访问
-> db 数据可持久化
-> redis 可连接
-> worker 能启动
-> POST /tasks（task_type=rag_retrieval）能创建任务
-> GET /tasks/{task_id} 能查询状态
```

M07 不负责 Kubernetes、服务网格、复杂 CI/CD 或生产级安全加固，这些后续由 M09 或项目进阶阶段承接。

## M09 Kubernetes 长期进阶边界

P03 已完成一次从 Docker Compose 到 kind 的本地功能性迁移参考，但这不是第一轮学习主线，也不是生产部署。

M09 只负责建立导论级迁移路线：

```text
compose api/db/redis/worker
-> api Deployment + Service
-> worker Deployment
-> ConfigMap / Secret
-> Ingress
-> HPA
-> Job / CronJob
```

P03 业务调度和 Kubernetes 资源调度需要区分：

| 层次 | 调度对象 | 调度者 | 执行资源 |
|---|---|---|---|
| P03 业务层 | 当前：通用 Task + `rag_retrieval`；规划：AgentTask | 当前：PostgreSQL/outbox + Redis Streams；规划：策略调度器 | 当前：RAG/模拟 workload worker；规划：Agent worker |
| Kubernetes 资源层 | Pod / Job | kube-scheduler | Node |

当前 E09 reference 已覆盖 Namespace、Deployment、Service、Secret、probe、非 root UID、滚动重启和手工 replicas；尚未覆盖 metrics-server、HPA/KEDA、持久卷、Ingress/TLS、NetworkPolicy、生产 Secret、复杂 CRD/operator 或服务网格。

## M10 推理服务长期进阶边界

P03 后续会把 RAG/Agent 的生成阶段逐步连接到真实推理服务，但 M10 第一版只做导论和模拟，不做底层推理优化。

推理请求在 P03 中可以先表示为：

```text
InferenceTask
-> Queue
-> Scheduler
-> Simulated Inference Worker
-> metrics
```

推理任务至少记录：

| 字段 | 作用 | 来源模块 |
|---|---|---|
| prompt_tokens | 输入长度 | M10 |
| output_tokens | 输出长度 | M10 |
| estimated_runtime_ms | 预计推理耗时 | M10/M05 |
| estimated_token_cost | token 成本 | M10/M05 |
| ttft_ms | 首 token 等待 | M10/M08 |
| tpot_ms | 每 token 耗时 | M10/M08 |
| tokens_per_second | 推理吞吐 | M10/M08 |
| rate_limited | 是否被限流 | M10/M08 |

M10 负责解释 TTFT、TPOT、tokens/s、batching、KV cache、并发、队列、限流、吞吐和尾延迟如何影响 P03；M05 负责队列和调度策略；M08 负责监控压测。第一版不深入 CUDA、Triton kernel、显存管理源码或 vLLM 内核源码。

## M12 金融投研场景边界

P03 可以使用金融投研文档作为场景化 workload，但它不是投资建议系统，也不是完整金融终端。

M12 第一版只负责把公告、财报、研报和公开 filings 这类文档转成 RAG / Agent 请求：

```text
公开金融文档
-> document metadata
-> chunk / embedding / retrieval
-> finance_rag_query
-> Queue / Scheduler / Worker
-> answer + retrieved_sources + risk_note + metrics
```

金融 Agent 请求可以表示为：

```text
finance_agent_report
-> retrieve_relevant_docs
-> extract_key_facts
-> verify_citations
-> draft_report
-> waiting_approval
-> finalize_report
```

金融场景任务至少记录：

| 字段 | 作用 | 来源模块 |
|---|---|---|
| task_type | `finance_rag_query` / `finance_agent_report` | M12/M03/M04 |
| document_type | 10-K / announcement / report | M12 |
| company / ticker | 公司过滤和展示 | M12 |
| period | 防止混用不同年份材料 | M12 |
| source_url | 支撑引用核验 | M12/M03 |
| citation_count | 衡量证据引用情况 | M12/M08 |
| unsupported_claim_count | 记录缺证据内容 | M12/M08 |
| risk_note_included | 输出边界检查 | M12 |
| retrieval_ms / generation_ms | RAG 阶段耗时 | M03/M08 |
| queue_wait_ms / total_latency_ms | workload 调度指标 | M05/M08 |

M12 负责场景边界、文档类型、引用和风险提示；M03 负责 RAG 链路；M04 负责 Agent 工作流；M05/M06/M08 负责队列、状态和指标。

当前不做投资建议、股价预测、量化策略、完整金融终端或虚构投研结论。

## M08 监控压测与可观测性边界

P03 第一轮的监控压测目标不是搭完整运维平台，而是让 API、RAG、任务队列和 worker 的性能可以被解释。

M08 负责把 M05/P01 的调度指标迁移成真实服务指标：

| M05/P01 指标 | P03 服务指标 | 用途 |
|---|---|---|
| average waiting time | average_queue_wait_seconds | 判断平均排队等待 |
| P95/P99 waiting time | p95/p99_queue_wait_seconds | 判断尾部排队延迟 |
| worker utilization | worker_utilization | 判断 worker 是否忙满 |
| queue length | queue_length | 判断任务是否堆积 |
| failed task count | task_error_rate | 判断稳定性 |
| throughput | requests_per_second / tasks_per_minute | 判断处理能力 |

P03 第一版至少要能观察：

```text
API request latency
task total latency
queue wait latency
RAG retrieval latency
RAG generation latency
queue length
worker utilization
error rate
throughput
```

E08 压测要回答的最小问题是：

```text
在固定请求类型、固定数据规模、固定调度策略下，
不同 worker 数量或不同并发负载会如何影响 P95/P99、队列长度、吞吐和错误率？
```

M08 不负责复杂 Prometheus 运维、Grafana 大规模部署或 OpenTelemetry 深度源码，这些后续由项目进阶阶段承接。

## 技术栈与边界

当前 v0.3.1 reference：

- Python 3.13、FastAPI、Uvicorn。
- 内存模式或 PostgreSQL task + outbox。
- Redis Streams consumer group、dispatcher、独立 worker。
- 固定 corpus + BM25 权限前置检索。
- Docker Compose、Locust、kind 功能性参考。

后续候选，不是当前依赖或已实现能力：

- Agent Runtime、LangGraph/LlamaIndex、向量库或 pgvector。
- Prometheus/Grafana、k6、Kubernetes 生产化与 HPA/KEDA。
- vLLM、Ray Serve、Triton 和真实 LLM generation。
- RQ/Celery 只用于教材中的方案对比，不是 P03 当前队列实现。

## 长期架构草图（含 planned 组件）

```text
Client
-> FastAPI API
-> Task Queue
-> Scheduler
-> Worker Pool
   -> RAG Worker
   -> Agent Worker
   -> Simulated Inference Worker
-> Metrics / Logs
-> Dashboard
```

## 实验指标

- 平均等待时间
- P95/P99 延迟
- 吞吐
- 队列长度
- 失败率
- worker 利用率
- token 成本

## 当前进度

- [x] 项目工作台
- [x] 内存参考 API 骨架
- [ ] 调度器 v1
- [x] RAG retrieval v0.3.1 reference（固定 corpus/BM25/权限前置过滤/来源持久化）
- [ ] RAG generation 与文档导入
- [ ] Agent v1
- [x] 单 API 容器 Compose 参考
- [x] db/redis/outbox dispatcher/独立 worker 多服务 Compose 参考
- [x] 内存与 PostgreSQL 阶段 metrics
- [x] Locust 短时 reference smoke
- [x] 1/2/4 worker × 3 次随机化短时本机 reference、队列/资源时序和 95% t 区间
- [x] kind 多服务、权限路径、API 滚动重启和手工 1/2/4 worker 功能性 reference
- [ ] Kubernetes HPA/KEDA、持久化、Ingress/TLS、NetworkPolicy 和生产 Secret
- [ ] 学习者长时稳态、warm-up、重复 RAG/LLM 和多主机压测
- [x] 参考实现 README

## 项目工作台

- [[50_项目产出/P03_AI_Workload_Platform/00_项目目标与范围|00 项目目标与范围]]
- [[50_项目产出/P03_AI_Workload_Platform/01_需求与任务拆解|01 需求与任务拆解]]
- [[50_项目产出/P03_AI_Workload_Platform/02_技术方案|02 技术方案]]
- [[50_项目产出/P03_AI_Workload_Platform/03_API与数据契约|03 API 与数据契约]]
- [[50_项目产出/P03_AI_Workload_Platform/04_实验记录/00_实验索引|04 实验记录索引]]
- [[50_项目产出/P03_AI_Workload_Platform/05_问题与失败记录|05 问题与失败记录]]
- [[50_项目产出/P03_AI_Workload_Platform/06_README草稿|06 README 草稿]]
- [[50_项目产出/P03_AI_Workload_Platform/07_简历表达|07 简历表达]]
- [[50_项目产出/P03_AI_Workload_Platform/08_阶段执行说明_v0.1|08 阶段执行说明 v0.1]]

## 科研化方向

- RAG/Agent 请求类型差异下的调度策略对比
- 高峰负载下尾延迟优化
- 多租户配额与公平性
- 成本感知调度
- 云原生部署下的扩缩容和冷启动

## 简历表达草稿

当前 P03 已有 v0.3.1 reference，包含可执行 BM25 检索与 27 tests，但真实服务 fixed replay、LLM generation、Agent、调度器和正式压测仍未完成。以下完整项目表达只有在学习者亲手完成对应功能、测试和实验记录后才能使用；当前仍应参考 [[80_就业市场与简历/简历项目表达/项目与科研表达模板_按完成状态分级|项目与科研表达模板：按完成状态分级]] 中的“计划复现 / 正在学习”口径。

设计并实现面向 RAG/Agent 请求的 AI 服务调度与监控平台，支持文档解析、向量检索、Agent 报告生成、任务队列、FIFO/Priority/SJF 调度、异步任务、Docker 部署和基础性能指标统计；通过压测对比不同调度策略下的 P95 延迟、吞吐和队列长度。

## 关联

- [[总路线图_AI_Infra方向]]
- [[两个月快速上手路线]]
- [[M03_RAG工程_学习地图]]
- [[M03_RAG工程_适配教材]]
- [[E03_RAG实验_索引]]
- [[M04_Agent工作流_学习地图]]
- [[M04_Agent工作流_适配教材]]
- [[E04_Agent实验_索引]]
- [[M05_任务队列与调度_学习地图]]
- [[M06_数据库缓存与异步任务_学习地图]]
- [[M06_数据库缓存与异步任务_适配教材]]
- [[E06_数据库异步任务实验_索引]]
- [[M07_Docker与容器化_学习地图]]
- [[M07_Docker与容器化_适配教材]]
- [[E07_Docker实验_索引]]
- [[M08_监控压测与可观测性_学习地图]]
- [[M08_监控压测与可观测性_适配教材]]
- [[E08_监控压测实验_索引]]
- [[M09_Kubernetes与云原生_学习地图]]
- [[M09_Kubernetes与云原生_适配教材]]
- [[E09_K8s实验_索引]]
- [[M10_AI推理系统_vLLM_Triton_学习地图]]
- [[M10_AI推理系统_vLLM_Triton_适配教材]]
- [[E10_推理服务实验_索引]]
- [[M12_金融投研AI场景_学习地图]]
- [[M12_金融投研AI场景_适配教材]]
