# P03 API 与数据契约

## 契约状态

- `v0.3.1 implemented / verified reference`：Task、PostgreSQL/Redis Streams/outbox、
  独立 worker、owner boundary 和 BM25 RAG retrieval 已验证。
- `planned`：文档导入、embedding/vector store、LLM generation、Agent、
  Evaluation 和生产身份系统。

参考实现不等于学习者完成。

## Authentication

除 `/health` 和 `/ready` 外，HTTP 接口都要求：

```text
Authorization: Bearer <reference-token>
```

本地 reference token 由服务端映射为不可由请求体覆盖的 principal：

| token | tenant_id | user_id | permission groups | operator |
|---|---|---|---|---|
| `reference-public-token` | tenant-reference | user-public | public | 否 |
| `reference-compliance-token` | tenant-reference | user-compliance | public, compliance_private | 否 |
| `reference-empty-token` | tenant-empty | user-empty | public | 否 |
| `reference-other-token` | tenant-other | user-other | public | 否 |
| `reference-ops-token` | tenant-reference | user-ops | public | 是 |

缺少或无效 token 返回 `401`；普通 principal 调用 operator endpoint 返回
`403 operator_permission_required`。这些 token 只是测试 fixture，生产系统必须换成
真实身份验证、服务端权限查询、密钥轮换和审计。

## Implemented API

| 方法 | 路径 | 鉴权与用途 | 模式 |
|---|---|---|---|
| `GET` | `/health` | 无鉴权；只检查进程 | memory/postgres |
| `GET` | `/ready` | 无鉴权；检查 PostgreSQL/Redis | memory/postgres |
| `POST` | `/tasks` | 任意 principal；owner-scoped 幂等创建 | memory/postgres |
| `GET` | `/tasks/{task_id}` | 仅 task tenant/user owner | memory/postgres |
| `GET` | `/metrics` | operator only | memory/postgres |
| `POST` | `/workers/run-next` | operator only；手工执行 | 仅 memory |

Compose 模式下 `/workers/run-next` 返回 `409 independent_worker_enabled`。
该接口只返回 task id、status 和 error type，不返回其他用户的输入或结果。

## POST /tasks

Mock 请求：

```json
{
  "task_type": "mock_rag",
  "priority": 5,
  "estimated_duration_ms": 25,
  "idempotency_key": "request-20260711-001",
  "input_json": {
    "query": "what is transactional outbox?",
    "sleep_ms": 25
  }
}
```

RAG retrieval 请求：

```json
{
  "task_type": "rag_retrieval",
  "priority": 5,
  "estimated_duration_ms": 0,
  "idempotency_key": "rag-20260711-001",
  "input_json": {
    "query": "客户 ZETA 为什么需要额外人工复核？",
    "top_k": 3
  }
}
```

约束：

- `task_type`: `mock_rag|mock_agent|simulated_inference|rag_retrieval`。
- `priority`: `1..10`，当前仍为 FIFO，不按 priority 排序。
- `estimated_duration_ms`: `0..86400000`，当前不用于调度。
- `idempotency_key`: `1..128`；作用域是 `(tenant_id, user_id, key)`。
- `rag_retrieval.query`: 去空白后 `1..1000` 字符。
- `rag_retrieval.top_k`: `1..5`，默认 3。
- `sleep_ms`: mock worker 限制 `0..5000`。
- `tenant_id`、`user_id`、`permission_groups`、`allowed_groups` 等安全字段
  禁止放入 `input_json`，否则返回 `422`。

响应为 `202`，其中 task 包含服务端 principal snapshot：

```json
{
  "task": {
    "task_id": "5fd4ec04-e855-4ebf-84a7-a789f468b503",
    "tenant_id": "tenant-reference",
    "user_id": "user-public",
    "allowed_permission_groups": ["public"],
    "task_type": "rag_retrieval",
    "priority": 5,
    "estimated_duration_ms": 0,
    "idempotency_key": "rag-20260711-001",
    "input_json": {"query": "客户 ZETA 为什么需要额外人工复核？", "top_k": 3},
    "status": "pending",
    "result_json": null,
    "error_type": null,
    "created_at": "2026-07-11T08:00:00Z",
    "queued_at": null,
    "started_at": null,
    "finished_at": null,
    "runtime_ms": null,
    "queue_wait_ms": null,
    "total_latency_ms": null
  },
  "created_new": true
}
```

同一 owner 和 idempotency key 返回原 task，`created_new=false`；不同 owner 可使用
相同 key，不会互相碰撞。

## RAG Result

`rag_retrieval` 先同时过滤 tenant 和 permission group，再对授权 chunks 构建
BM25 排序。worker 只使用 task 表中的 permission snapshot，不读取客户端权限字段。

```json
{
  "kind": "rag_retrieval_reference",
  "answer_mode": "deterministic_extractive",
  "quality_status": "retrieval_only_not_llm_evaluated",
  "query": "客户 ZETA 为什么需要额外人工复核？",
  "answer": "[doc_compliance_private_001] 内部合规备忘录...",
  "retrieval_ms": 0.42,
  "retrieval_status": "ok",
  "authorized_search_space_size": 5,
  "security_context": {
    "tenant_id": "tenant-reference",
    "user_id": "user-compliance",
    "allowed_permission_groups": ["compliance_private", "public"]
  },
  "sources": [
    {
      "tenant_id": "tenant-reference",
      "document_id": "doc_compliance_private_001",
      "chunk_id": "doc_compliance_private_001#chunk-000",
      "permission_group": "compliance_private",
      "text": "内部合规备忘录指出客户 ZETA 需要额外人工复核。",
      "retrieval_score": 11.33,
      "matched_query_token_count": 12
    }
  ]
}
```

没有任何授权 corpus 时，task 仍成功，`retrieval_status=empty_authorized_corpus`、
`authorized_search_space_size=0`、`sources=[]`、`answer=null`。授权 corpus 存在但
查询 token 无匹配时返回 `no_relevant_authorized_source`，不会用零相关文档凑满
top-k，也不会退回跨租户或未授权文档。

## Ownership Boundary

`GET /tasks/{task_id}` 在数据库/内存 store 查询时同时附加 tenant 和 user 条件。
其他用户查询同一 task id 返回 `404 task_not_found`，避免泄漏任务是否存在。

PostgreSQL 唯一约束：

```sql
UNIQUE (tenant_id, user_id, idempotency_key)
```

tasks 表保存 `allowed_permission_groups TEXT[]`，让异步 worker 使用提交时的
权限快照。生产系统还需要定义权限撤销后对排队任务的处理策略；当前 reference
不声称解决实时权限撤销。

## 状态与指标

```text
pending -> queued -> running -> succeeded
                            -> failed
                    -> retrying -> queued
```

数据库保留 `cancelled`，但尚无取消 API。

```text
queue_wait_ms = started_at - queued_at
total_latency_ms = finished_at - created_at
```

operator-only `/metrics` 返回 task/status counts、Redis broker backlog、outbox
backlog、最近一分钟完成量，以及 queue wait/runtime average、P95、P99。
`run_id` 过滤 task/outbox 聚合；Redis 只保存 task id，因此 broker length 仍是全局值。

## 当前错误类型

| error_type | 是否重试 | 来源 |
|---|---|---|
| `forced_failure` | 否 | reference 故障注入 |
| `invalid_sleep_ms` | 否 | mock 参数非法 |
| `invalid_rag_input` | 否 | worker 防御性 RAG 校验 |
| `invalid_input` | 否 | 预留确定性错误 |
| `permission_denied` | 否 | 预留安全错误 |
| `collection_not_found` | 否 | 预留 corpus 错误 |
| 其他错误 | 最多 2 次 | retry outbox |
| `worker_lease_expired` | 最多 2 次 | reconciliation |

## 验收状态

- [x] memory 与 postgres 模式共享 Task API 模型。
- [x] principal snapshot、owner-scoped idempotency 和 owner-scoped task query。
- [x] tenant + permission prefilter 在 BM25 候选集建立前执行。
- [x] 公开拒绝、私密授权、跨租户拒绝、空结果和来源持久化有测试。
- [x] task/outbox、CAS、lease、重复投递和 API 重启有 Compose 证据。
- [ ] 生产身份系统、实时权限撤销、文档导入和 corpus lifecycle。
- [ ] embedding/vector store、LLM generation、Agent 和 Evaluation API。
- [ ] learner-owned 实现与实验记录。
