# E08-02 记录 average/P95/P99/吞吐/错误率

> 参考状态（2026-07-11，当前契约 v0.3.1）：P03 已能输出 API Locust CSV/JSON、task queue/runtime 分位数、队列时序、worker 资源时序，并完成每组 3 次的随机化短时 reference。样本仍小且 workload 为 mock，不能代替学习者正式长时实验。

## 指标分层

| 层次 | 指标来源 | 当前可用字段 |
|---|---|---|
| API admission | Locust CSV | average、P95、P99、requests/s、HTTP failures |
| Broker | Redis | `broker_queue_length` |
| Task state | PostgreSQL | pending、queued、running、succeeded、failed、retrying |
| Queue stage | task timestamps | average/P95/P99 `queue_wait_ms` |
| Worker stage | persisted runtime | average/P95/P99 `runtime_ms` |
| End-to-end task | task timestamps | `total_latency_ms` |
| Recovery | outbox/task | `pending_outbox_count`、retry_count、error_type |

`queue_length` 目前是兼容旧接口的 Redis backlog 别名，正式记录优先使用语义更清楚的 `broker_queue_length`。即使查询带 `run_id`，broker length 仍是全局值；run-id 过滤只适用于 PostgreSQL task/outbox 聚合，所以每个正式组别必须独占环境或另做 broker 消息标记。

## 计算契约

```text
queue_wait_ms = started_at - queued_at
runtime_ms = worker 内 mock workload 的执行时间
total_latency_ms = finished_at - created_at
HTTP error_rate = failed HTTP requests / total HTTP requests
task_error_rate = failed tasks / all terminal tasks
```

API error rate 和 task error rate 必须分开。请求可能成功返回 202，但任务随后失败。

PostgreSQL 使用 `percentile_cont(0.95/0.99)` 计算连续分位数；内存教学模式使用相同的线性插值定义。小样本 P99 不稳定，不能只报一个数字而不报样本量。

## 当前接口

任务响应包含：

```json
{
  "queued_at": "...",
  "started_at": "...",
  "finished_at": "...",
  "runtime_ms": 25.2,
  "queue_wait_ms": 120.4,
  "total_latency_ms": 151.8
}
```

`GET /metrics` 包含：

```text
task_count
broker_queue_length
active_workers
pending_outbox_count
completed_last_minute
status_counts
average/p95/p99_queue_wait_ms
average/p95/p99_runtime_ms
worker_busy_time_ms
observation_window_ms
```

`active_workers` 是查询瞬间 `running` task 数。E08-03 使用 `worker_busy_time_ms / (worker_count * observation_window_ms)` 计算 task-processing utilization；它仍不是 CPU utilization。

## Reference Smoke 结果

控制条件：空任务库、1 API、1 dispatcher、1 worker、5 users、spawn 5/s、10 秒、mock `sleep_ms=25`。

| 指标 | 结果 |
|---|---:|
| submitted requests | 195 |
| HTTP failures | 0 |
| requests/s | 25.40 |
| average API latency | 58.13 ms |
| P95 API latency | 70 ms |
| P99 API latency | 72 ms |
| succeeded tasks after drain | 195 |
| task failures | 0 |
| average queue wait | 3571.95 ms |
| P95 queue wait | 6598.49 ms |
| P99 queue wait | 6976.23 ms |
| P95 runtime | 25.36 ms |

这轮数据只证明指标链路能揭示“入口无错误但后台排队明显”的现象。它没有 warm-up、多轮重复、置信区间或 worker 数对照，不能写成容量上限或调度结论。

## 2026-07-11 Repeated Reference

固定条件：5 users、5 秒、`mock_rag sleep_ms=25`、每组新 volume、随机组序、
每个 worker_count 重复 3 次。以下区间是三次本机运行上的双侧 95% Student t 区间：

| workers | HTTP failures | queue P95 mean [95% CI] | queue P99 mean [95% CI] | task utilization mean [95% CI] |
|---:|---:|---:|---:|---:|
| 1 | 0 | 2673.41 [1940.58, 3406.25] ms | 2820.45 [2054.82, 3586.09] ms | 0.825 [0.788, 0.862] |
| 2 | 0 | 398.44 [124.14, 672.75] ms | 436.33 [185.45, 687.20] ms | 0.722 [0.580, 0.864] |
| 4 | 0 | 225.58 [112.03, 339.14] ms | 271.76 [133.21, 410.30] ms | 0.441 [0.412, 0.470] |

三次重复只提供最小不确定性提示。2-worker 区间仍很宽；不能据此声称稳定容量、
线性扩展或生产 SLO。完整数据见 `artifacts/e08_reference_repeated/`。

另有一次 `rag_retrieval` 单轮 smoke：18 tasks、0 HTTP/task failures、queue P95
139.04 ms、queue P99 162.31 ms、runtime P95 2.17 ms；所有任务持久化 `ok`
和非空 sources。该数据没有重复和 worker 对照，不能与 mock scaling 表直接合并。

## 正式记录表

| run_id | n | users | workers | avg_api | p95_api | p99_api | req/s | HTTP_error | avg_queue | p95_queue | p99_queue | p95_runtime | task_error | drain_time |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
|  |  |  |  |  |  |  |  |  |  |  |  |  |  |  |

每个组别至少保存：

- Locust `stats.csv` 与 `stats_history.csv`。
- drain 后 `/metrics` JSON。
- Compose 服务数量和镜像信息。
- 数据库是否为空、warm-up 是否剔除。
- 异常日志和失败任务样本。
- `timeseries.csv` 和 `worker_resources.csv`。
- 随机化运行计划、重复级原始结果和置信区间表。

## 误判提醒

- average 好看但 P99 很差，不能称为稳定。
- P99 queue wait 高不等于 mock workload 慢。
- completed_last_minute 是滚动快照，不是任意实验窗口的精确 throughput。
- drain 后 broker backlog 为 0，不代表压测期间没有出现峰值积压。
- 累计 `/metrics` 会混入旧任务，正式实验必须空库或按 run_id 分区统计。

## 学习者验收

- [ ] 能从原始 CSV 复核 API average/P95/P99 和 error rate。
- [ ] 能从任务时间戳复核 queue wait 与 total latency。
- [ ] 能分别报告 HTTP error rate 与 task error rate。
- [ ] 能报告样本量、重复次数和实验窗口。
- [ ] 能说明当前 reference smoke 的所有局限。
