# E06-03 embedding 与检索结果缓存实验

> 安全校订：客户端只能提交 query、collection、top-k 等业务字段。tenant、user 与有效 ACL 必须来自服务端 principal；检索缓存 key 使用服务端生成的 ACL fingerprint/version，并覆盖 collection、文档/索引版本、embedding 模型、检索器、过滤条件、top-k 和 query hash。缺任一影响结果的维度都可能产生越权或陈旧结果。

> Reference 状态：`e06_sqlite_reference/` 已实现可执行的安全 retrieval cache。它使用确定性内存 LRU/TTL backend、缓存不可用故障替身、单进程 single-flight 和 E06 自有 FastAPI/worker 集成测试。该证据不等于真实 Redis 网络、持久化、集群或跨进程锁验证。

## 实验目的

本实验用于观察缓存如何减少重复 embedding 或重复检索的成本和延迟。

第一轮只做 P03 需要的最小缓存实验：

```text
相同文本或相同查询重复出现
-> 生成 cache_key
-> 先查缓存
-> 命中则直接返回
-> 未命中则计算并写入缓存
-> 记录 hit/miss、latency_ms、saved_calls
```

它不是 Redis 大全，也不是缓存架构课。

当前执行边界：E06 自身 reference 已提供 server-owned principal、owner-scoped task API、伪造身份字段拒绝、跨 tenant/owner/ACL/version 缓存隔离、损坏值恢复、TTL/LRU、缓存不可用降级和 8 线程 single-flight。E03 仍提供更完整的 RAG corpus/ACL 检索负测；P03 v0.3.1 尚未实现检索缓存，因此不能把 E06 的内存 backend 或 P03 的 RAG workload 误报为真实 Redis 缓存完成。

最小可执行入口：

```powershell
cd "40_实验练习/E06_数据库异步任务实验/e06_sqlite_reference"
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
.\.venv\Scripts\python.exe -m pytest -q tests/test_cache.py tests/test_api_integration.py
```

预期局部结果为 `12 passed`；全套 E06 为 `42 passed`。

## 自动化证据矩阵

| 风险/主张 | 测试 | 观察值 |
|---|---|---|
| owner/ACL/版本隔离 | `test_cache_key_isolated_by_owner_acl_and_content_version` | context 变化产生不同 key 与 miss |
| TTL 与有界淘汰 | `test_ttl_expiry_and_bounded_lru_eviction_are_observable` | 过期/淘汰后重新 compute |
| 损坏或越权缓存值 | `test_corrupt_or_over_scoped_cache_value_is_deleted_and_recomputed` | invalid=true，删除并按授权 scope 重算 |
| backend 不可用 | `test_backend_outage_falls_back_only_after_authorization` | 调用顺序为 authorize -> compute；unavailable=true |
| compute 越权 | `test_compute_cannot_return_a_source_outside_authorized_scope` | fail closed，不写 cache |
| 并发 miss | `test_concurrent_miss_runs_one_compute_and_shares_the_flight` | 8 callers，compute_calls=1 |
| HTTP/owner scope | `test_api_integration.py` | forged fields 422；跨 owner/tenant 404 |
| API -> DB -> worker -> cache | `test_fastapi_database_worker_and_safe_cache_form_an_end_to_end_loop` | 两个任务 succeeded，第二个 cache hit |

## 前置阅读

- [[10_学习模块/M06_数据库缓存与异步任务/M06_数据库缓存与异步任务_适配教材|M06 数据库缓存与异步任务适配教材]]
- [[40_实验练习/E03_RAG实验/E03-01 chunk 大小对检索效果的影响|E03-01 chunk 大小对检索效果的影响]]
- [[40_实验练习/E03_RAG实验/E03-02 top-k 对回答质量和延迟的影响|E03-02 top-k 对回答质量和延迟的影响]]
- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]

## 数据表/字段

缓存可以先用内存字典模拟，后续再替换 Redis。

### cache_records 记录表

用于实验记录，不一定是正式业务表。

```sql
CREATE TABLE cache_records (
    cache_key TEXT PRIMARY KEY,
    cache_type TEXT NOT NULL,
    input_hash TEXT NOT NULL,
    value_summary TEXT,
    ttl_seconds INTEGER,
    hit_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    last_hit_at TEXT
);
```

### 缓存类型

| cache_type | 用途 |
|---|---|
| embedding | 缓存 chunk 或 query 的 embedding |
| retrieval_result | 缓存 query + collection + top_k + 服务端有效 ACL 等完整结果上下文 |

## cache_key 设计

### embedding cache key

```text
embedding:v1:{model_version}:{normalizer_version}:{sha256(normalized_text)}
```

示例：

```text
embedding:v1:mock-v1:nfc-ws-v1:ab12cd...
```

模型或文本规范化规则变化会改变向量，因此也必须改变 key。embedding cache 只能在完成 tenant/文档授权过滤后读取；拥有相同文本 hash 不代表调用方有权看到该文本或其元数据。

### retrieval cache key

```text
retrieval:v1:{sha256(canonical_json(cache_context))}
```

其中 `cache_context` 至少包含：

```json
{
  "tenant_id": "tenant_demo",
  "acl_version": "acl-v1",
  "acl_fingerprint": "sha256:scope-public-...",
  "collection_id": "demo_docs",
  "document_version": "docs-v1",
  "index_version": "index-v1",
  "embedding_model_version": "embed-v1",
  "retriever_version": "bm25-v1",
  "filter_hash": "sha256:no-filter-...",
  "top_k": 3,
  "query_hash": "sha256:ef34ab..."
}
```

`canonical_json` 必须固定键顺序、编码和规范化规则，再对整体做 hash，避免简单字符串拼接的分隔符歧义。不要只用 query、客户端声称的 permission group 或 collection 当 key。相同 query 在不同租户、有效 ACL、ACL 版本、文档版本、索引、模型、检索器、filter 和 top-k 下都可能产生不同结果。

### 服务端 principal 与 ACL fixture

本实验用三个**服务端** fixture 验证隔离；客户端只通过认证令牌选择身份，不能直接提交下表字段：

| fixture | tenant_id | user_id | effective_permission_groups | acl_version |
|---|---|---|---|---|
| public_v1 | tenant_demo | user_public | public | acl-v1 |
| compliance_v1 | tenant_demo | user_compliance | public, compliance_private | acl-v1 |
| public_v2 | tenant_demo | user_public | public | acl-v2 |

`public_v1` / `compliance_v1` 可分别映射 P03 的 reference public/compliance token；`public_v2` 是为 ACL version 负测在服务端构造的 fixture，不是客户端可选字段。

服务端按规范化 JSON 计算：

```text
acl_fingerprint = sha256({tenant_id, sorted(effective_permission_groups), acl_version})
```

如果检索结果还受用户级 entitlement、region、policy 或 personalization 影响，也必须把对应的服务端版本/指纹加入 `cache_context`。缓存查找必须发生在认证和权限前置过滤之后，不能先检索或命中全量结果再做事后过滤。

## API 示例

### 创建 RAG 任务

```http
POST /tasks
Authorization: Bearer reference-public-token
Content-Type: application/json
```

```json
{
  "task_type": "rag_retrieval",
  "idempotency_key": "rag-cache-001",
  "input_json": {
    "query": "RAG 为什么需要 sources？",
    "collection_id": "demo_docs",
    "top_k": 3
  }
}
```

`input_json` 中不得出现 `tenant_id`、`user_id`、`permission_group`、`permission_groups` 或 `allowed_permission_groups`。服务端解析 token 后，把 principal/ACL snapshot 与业务输入分开保存。

### 任务结果中的缓存指标

和 E06-01/E06-02 一样，客户端不直接等待缓存和 RAG 执行完成，而是通过任务状态查询：

```http
GET /tasks/task_rag_cache_001
Authorization: Bearer reference-public-token
```

返回结果示例：

```json
{
  "task_id": "task_rag_cache_001",
  "status": "succeeded",
  "result_json": {
    "answer": "...",
    "retrieved_sources": ["doc_public_rag_001_chunk_1"],
    "metrics": {
      "embedding_cache_hit": true,
      "retrieval_cache_hit": false,
      "saved_embedding_calls": 1,
      "retrieval_ms": 8,
      "token_count": 260
    }
  }
}
```

## 状态流转

缓存实验仍然依附任务状态：

```text
pending
-> queued
-> running
-> succeeded
```

缓存命中不是任务状态，只是 `result_json.metrics` 或日志里的指标。

本实验仍然需要理解完整任务状态：

| 状态 | 在缓存实验中的含义 |
|---|---|
| pending | API 已创建缓存相关 RAG 任务 |
| queued | dispatcher 已接纳投递；可能正在发布，或已在队列等待 worker；未发布事件仍由 outbox 恢复 |
| running | worker 正在检查缓存、检索或生成 |
| succeeded | 任务完成，缓存指标写入 result_json |
| failed | 非缓存原因或不可恢复错误导致任务失败 |
| retrying | 缓存服务或检索临时失败，准备重试 |
| cancelled | 预留枚举；P03 v0.3.1 无取消 API，本实验不把它计为可达状态 |

如果缓存服务不可用，第一轮建议：

```text
cache_unavailable
-> fallback to normal computation
-> task 可以 succeeded
-> result_json.metrics.cache_error = true
```

不要因为缓存失败就让核心 RAG 请求必然失败，除非后续明确缓存是强依赖。

## 实验步骤

### 步骤 1：准备重复输入

使用同一个 query 连续执行 3 次：

```text
principal_fixture = public_v1  # 服务端 fixture，不是请求字段
query = RAG 为什么需要 sources？
collection_id = demo_docs
top_k = 3
```

### 步骤 2：第一次请求

预期：

```text
embedding_cache_hit = false
retrieval_cache_hit = false
```

记录：

- embedding_calls
- retrieval_ms
- cache_key
- result retrieved_sources

### 步骤 3：第二次请求

同样输入再次请求。

预期：

```text
embedding_cache_hit = true
retrieval_cache_hit = true 或部分 true
latency_ms 降低
saved_calls 增加
```

### 步骤 4：改变 top_k

把 `top_k` 从 3 改为 5。

预期：

```text
embedding_cache 可能命中
retrieval_cache 应该 miss
```

因为 retrieval key 包含 top_k。

### 步骤 5：切换服务端 principal fixture

保持业务请求完全相同，认证身份从 `public_v1` 切换到 `compliance_v1`。不要修改请求体或向其中添加权限字段。

预期：

```text
retrieval_cache 应该 miss
public_v1 与 compliance_v1 的 acl_fingerprint 不同
public_v1 的结果不得包含 compliance_private chunk
```

随后再次使用 `public_v1`，应命中它自己的缓存条目，且仍不得出现私有 chunk。这样才能证明缓存没有跨 ACL 污染。

### 步骤 6：改变 ACL version

保持 tenant、user、有效权限组和业务请求都不变，把服务端 fixture 从 `public_v1` 切换到 `public_v2`。

预期 `retrieval_cache` miss。即使权限组字符串没有变化，ACL policy/version 变化也必须隔离旧条目。

### 步骤 7：模拟缓存过期

设置较短 TTL，例如：

```text
ttl_seconds = 60
```

过期后再次请求，记录 miss。

### 步骤 8：执行安全负测

至少完成以下负测，并记录请求状态码、缓存条目数和 retrieved_sources：

1. 分别向请求或 `input_json` 注入 `tenant_id`、`user_id`、`permission_group`、`permission_groups`、`allowed_permission_groups`，预期 `422 forged_identity_fields` 或项目统一的等价验证错误，且 task/outbox/cache 条目数均不增加。
2. 先用 `compliance_v1` 填充缓存，再用相同 query 的 `public_v1` 请求；预期 cache miss，且私有 chunk 既不参与评分也不出现在 sources。
3. `public_v1` 填充缓存后切换到 `public_v2`；预期 cache miss，证明 ACL version 参与隔离。
4. 删除 cache key 中的 ACL fingerprint/version，确认上述第 2 或第 3 项会失败；只把这个故障实现用于测试，不能保留在正式路径。

### 步骤 9：制造并发 miss

让 8 个线程通过 barrier 同时请求同一 key，并让 compute 暂停 50 ms。预期所有请求得到相同结果，`compute_calls == 1`，其余请求标记 `singleflight_shared=true`。随后改成两个不同 query，预期每个 key 各有一个 leader；不能为了防风暴把所有 key 全局串行。

### 步骤 10：注入损坏或越权 value

绕过正常写入方法，向同一 key 写入包含 `doc-private` 的 value，再以 public principal 读取。预期该值不算有效 hit：reference 删除它、设置 `cache_value_invalid=true`，并只用 public `AuthorizedScope` 重算。未知 schema、字段类型错误和非法 JSON 走同一恢复路径。

### 步骤 11：注入 backend unavailable

替换为 `UnavailableCacheBackend`。记录调用顺序必须为 `authorize -> cache error -> compute`，任务仍可成功，但 `cache_unavailable=true`。若 authorizer 拒绝请求，compute 不得执行；缓存故障不能成为扩大 source scope 的理由。

## 失败场景

| 场景 | 预期处理 | error_type / metric |
|---|---|---|
| 客户端伪造身份或权限字段 | 422，且不创建 task/outbox/cache | forged_identity_fields |
| cache key 缺少 ACL fingerprint/version | 可能跨授权范围命中，测试必须失败 | cache_key_scope_error |
| 权限过滤发生在检索/缓存命中之后 | 私有 chunk 已参与评分，必须拒绝该实现 | authorization_order_error |
| Redis 不可用 | 回退正常计算 | cache_unavailable |
| 缓存值格式损坏 | 删除缓存并重算 | cache_value_invalid |
| 热门 key 同时过期 | 同 key single-flight；不同 key 可并行 | singleflight_shared / compute_calls |
| 条目超过容量 | 按已声明策略淘汰并记录 | cache_evicted |
| TTL 太短 | 命中率低 | cache_expired |
| TTL 太长 | 旧结果风险 | stale_cache |
| 未来实现取消时任务被取消 | 不继续读写缓存；当前版本不验收 | task_cancelled |

## 记录表

| run_id | query | collection_id | principal_fixture | acl_version | acl_fingerprint_summary | top_k | cache_type | cache_key_summary | cache_hit | ttl_seconds | saved_calls | retrieval_ms | error_type | sources_scope | 观察 |
|---|---|---|---|---|---|---:|---|---|---|---:|---:|---:|---|---|---|
| R1 | RAG 为什么需要 sources？ | demo_docs | public_v1 | acl-v1 |  | 3 | retrieval_result |  | false | 60 | 0 |  |  | public only | cold miss |
| R2 | RAG 为什么需要 sources？ | demo_docs | public_v1 | acl-v1 |  | 3 | retrieval_result |  | true | 60 |  |  |  | public only | same server principal |
| R3 | RAG 为什么需要 sources？ | demo_docs | public_v1 | acl-v1 |  | 5 | retrieval_result |  | false | 60 |  |  |  | public only | top_k changed |
| R4 | RAG 为什么需要 sources？ | demo_docs | compliance_v1 | acl-v1 |  | 3 | retrieval_result |  | false | 60 |  |  |  | effective ACL | principal changed |
| R5 | RAG 为什么需要 sources？ | demo_docs | public_v2 | acl-v2 |  | 3 | retrieval_result |  | false | 60 |  |  |  | public only | ACL version changed |

## 验收标准

- [ ] 能设计包含 model/normalizer version 的 embedding cache key，并只在授权过滤后访问缓存。
- [ ] 能用 canonical JSON + hash 设计 retrieval cache key，且包含所有影响授权与结果的服务端版本/过滤维度。
- [ ] 能记录 hit/miss、TTL、saved_calls、latency_ms。
- [ ] 能解释为什么不能信任客户端 permission_group，以及 ACL fingerprint/version 为什么必须进入 retrieval cache key。
- [ ] 能证明 public/compliance fixture 不共享检索缓存，public 结果中没有私有 chunk。
- [ ] 能证明有效权限组相同但 ACL version 改变时仍然 cache miss。
- [ ] 能证明伪造 tenant/user/权限字段的请求返回 422，且不创建 task/outbox/cache。
- [ ] 能模拟 Redis 不可用时的降级策略。
- [ ] 能用 8 个并发 caller 证明同 key 只执行一次 compute，并说明该证据只覆盖单进程。
- [ ] 能让损坏、未知 schema 或越权 source 的缓存值被拒绝并重算。
- [ ] 能区分 TTL、version invalidation、显式 delete 和 eviction 的职责。
- [ ] 能通过 `GET /tasks/{task_id}` 查询缓存实验任务状态。
- [ ] 能说明 pending/queued/running/succeeded/failed/retrying 的含义，并指出 cancelled 在 P03 v0.3.1 只是预留枚举。
- [ ] 能把缓存指标写入 `result_json.metrics`。
- [ ] 能说明缓存如何影响 P03 的 latency 和 token 成本。

## 和 P03 的连接

| 实验字段 | P03 字段 |
|---|---|
| cache_key | result_json.metrics.cache_key_summary 或 task_events |
| cache_hit | result_json.metrics.embedding_cache_hit / retrieval_cache_hit |
| saved_calls | result_json.metrics.saved_embedding_calls |
| retrieval_ms | retrieval_ms |
| total_latency_ms | task total latency |
| error_type | error_type |
| principal fixture | 认证层的 server-owned principal；不是请求字段 |
| tenant_id / user_id | tasks 的 owner 字段，由服务端 principal 写入 |
| allowed_permission_groups | P03 v0.3.1 的服务端 ACL snapshot 字段；不得来自 `input_json` |
| acl_fingerprint / acl_version | E03 reference 已由服务端 principal 生成；P03 v0.3.1 尚无专用持久化字段，接入检索缓存前必须补齐，不能伪装成已实现 |

## 暂时不做

- 不做 Redis 集群。
- 不做复杂缓存淘汰策略。
- 不做跨服务缓存一致性。
- 不缓存无权限过滤的检索结果。
- 不把缓存命中率当成唯一优化目标。
