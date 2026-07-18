# E08-01 Locust 压测任务创建 API

> 参考状态（2026-07-11，当前契约 v0.3.1）：P03 的 `locustfile.py` 可显式选择 `mock_rag` 或 `rag_retrieval`。worker scaling 使用 `mock_rag` 做 1/2/4 × 3 随机化 reference；另完成 18-task BM25 `rag_retrieval` 单轮 smoke。两者都不是 LLM 或生产容量结论。

## 压测目标

第一轮只压测异步任务入口：

```text
Locust POST /tasks
-> API 事务写 task + outbox
-> 返回 202 和 task_id
-> 后台 dispatcher/worker 独立完成任务
```

本实验必须分别记录：

- HTTP 提交延迟、吞吐和失败率。
- 任务 queue wait、runtime 和最终失败率。

`POST /tasks` 很快不代表 worker 没有积压。

## 前置条件

```powershell
cd 50_项目产出\P03_AI_Workload_Platform\p03_service
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.lock
docker compose up --build -d
Invoke-RestMethod http://127.0.0.1:8001/ready
```

正式组别开始前应使用空任务库。清空 named volume 会删除所有本地任务数据，只能在确认无需保留后执行：

```powershell
docker compose down -v --remove-orphans
docker compose up -d
```

## 当前请求模板

```json
{
  "task_type": "mock_rag",
  "priority": 5,
  "estimated_duration_ms": 25,
  "idempotency_key": "locust-<uuid>",
  "input_json": {
    "query": "RAG why does queue wait affect tail latency?",
    "sleep_ms": 25
  }
}
```

真实 BM25 retrieval 模式将 `task_type` 改为 `rag_retrieval`，并用
`input_json.query/top_k/run_id`；tenant/user/permission 仍由 bearer principal
在服务端决定。

每次请求必须使用新的 idempotency key，否则会测成“重复请求查询已有任务”，而不是任务创建。

## 可执行负载文件

参考实现位于：

```text
50_项目产出/P03_AI_Workload_Platform/p03_service/load/locustfile.py
```

核心逻辑：

```python
from uuid import uuid4

from locust import HttpUser, constant_throughput, task


class TaskSubmissionUser(HttpUser):
    wait_time = constant_throughput(5)

    @task
    def submit_mock_rag(self):
        payload = {
            "task_type": "mock_rag",
            "priority": 5,
            "estimated_duration_ms": 25,
            "idempotency_key": f"locust-{uuid4()}",
            "input_json": {"query": "tail latency", "sleep_ms": 25},
        }
        with self.client.post(
            "/tasks",
            json=payload,
            headers={"Authorization": "Bearer reference-ops-token"},
            catch_response=True,
        ) as response:
            if response.status_code != 202:
                response.failure(f"unexpected status {response.status_code}")
```

## Reference Smoke

```powershell
.\scripts\run_load_smoke.ps1 `
    -Users 5 `
    -SpawnRate 5 `
    -RunTime 10s `
    -RequestsPerUser 5
```

脚本会：

1. 等待 `/ready`。
2. 拒绝在非空任务库上运行，防止累计指标污染。
3. 后台运行 headless Locust，并按 500ms 记录 queue/outbox/task 时序。
4. 并行记录 worker 容器 CPU 和内存时序。
5. 等待所有 task 进入终态，并校验 Locust 请求数等于数据库 task 数。
6. 保存 drain 后指标、原始 CSV/JSON、stdout/stderr 和 run summary。

2026-07-10 一轮 reference smoke：

| requests | HTTP failures | req/s | avg API | P95 API | P99 API |
|---:|---:|---:|---:|---:|---:|
| 195 | 0 | 25.40 | 58.13 ms | 70 ms | 72 ms |

原始文件位于：

```text
50_项目产出/P03_AI_Workload_Platform/p03_service/artifacts/e08_reference_smoke/
```

2026-07-11 还执行了随机化 1/2/4 worker × 3 次 reference，原始文件位于：

```text
50_项目产出/P03_AI_Workload_Platform/p03_service/artifacts/e08_reference_repeated/
```

它补齐了最小重复、运行顺序随机化、队列时序、worker 容器 CPU/内存和 95% t
区间，但仍是 5 秒本机 mock workload，不能替代下方学习者长时组别。

BM25 单轮 smoke：

```powershell
.\scripts\run_load_smoke.ps1 `
    -TaskType rag_retrieval `
    -TopK 3 `
    -Users 3 `
    -RunTime 4s `
    -ArtifactRootName e08_rag_reference_smoke `
    -Label bm25_single_worker
```

该轮 18 个 HTTP 请求和数据库 task 全部成功，18 个结果均为
`rag_retrieval_reference`、`retrieval_status=ok` 且 sources 非空。它只验证真实
retrieval workload 接入采集链路，不比较扩缩容或 RAG 质量。

## 正式学习组别

| 组别 | users | spawn_rate | duration | worker_count | 重复次数 |
|---|---:|---:|---|---:|---:|
| A | 1 | 1/s | 2 min | 1 | >= 3 |
| B | 10 | 2/s | 5 min | 1 | >= 3 |
| C | 30 | 5/s | 5 min | 1 | >= 3 |
| D | 50 | 10/s | 5 min | 1 | >= 3 |

若本机能力不足可以降低 users，但必须固定 workload、worker 数、镜像、数据库初始状态和 warm-up 规则。

## 误判提醒

| 误判 | 正确判断 |
|---|---|
| HTTP 0 failures 就说明平台无积压 | 同时看 queue wait、未完成任务和 drain 时间 |
| Locust P99 等于任务 P99 | Locust 只测提交请求，任务在后台继续执行 |
| 一轮 10 秒 smoke 可用于容量规划 | smoke 只验证链路，正式实验要长时、多轮、控变量 |
| Redis Streams backlog 等于所有 queued task | `pending + lag` 包含已 reserve 未 ACK 与尚未投递给 consumer 的消息；数据库 queued/running 是另一状态面 |
| 改 users 时同时改 sleep_ms | 会混淆到达率与服务时间的影响 |

## 学习者验收

- [ ] 亲自完成至少四组负载并保留原始 CSV。
- [ ] 每组至少重复三轮并记录机器与镜像版本。
- [ ] 同时记录 HTTP 与任务最终失败率。
- [ ] 能解释 API latency 和 task total latency 的差异。
- [ ] 不把 reference smoke 写成性能或科研结论。
