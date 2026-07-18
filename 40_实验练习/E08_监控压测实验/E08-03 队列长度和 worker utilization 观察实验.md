# E08-03 队列长度和 worker utilization 观察实验

> 状态（2026-07-11，当前契约 v0.3.1）：`executable / verified repeated local reference / learner pending`。P03 已完成随机化 1/2/4 worker × 3 次 mock 空库对照、500ms 队列时序、worker 容器 CPU/内存、task-processing utilization 和 95% t 区间；另有 BM25 单轮 smoke。长时稳态、8 worker、重复 RAG/LLM、多主机和学习者复现仍未完成。

## 压测目标

本实验用于判断 P03 慢是否来自 worker 不足、任务太重、队列堆积或 worker 没有正常消费。

它把 M05/P01 中的：

```text
queue length
worker utilization
```

迁移到 P03 的真实服务观察中。

核心问题是：

```text
队列是否持续增长？
worker 是否忙满？
P95/P99 是否随着队列增长而上升？
```

## 前置条件

- 已完成或设计 [[40_实验练习/E08_监控压测实验/E08-01 Locust 压测 RAG_API 请求|E08-01 Locust 压测 RAG/API 请求]]
- 已完成或设计 [[40_实验练习/E08_监控压测实验/E08-02 记录 average_P95_P99_吞吐_错误率|E08-02 记录 average/P95/P99/吞吐/错误率]]
- 已理解 [[40_实验练习/E06_数据库异步任务实验/E06-02 文档解析与 RAG 请求异步化|E06-02 文档解析与 RAG 请求异步化]]
- P03 能记录：

```text
broker_queue_length
status_counts.queued / running
worker_busy_time_ms
observation_window_ms
p95/p99_runtime_ms
p95/p99_queue_wait_ms
```

当前 reference 可以用任务状态表和 Redis 指标做基础观察：

- `broker_queue_length` = Redis consumer group 的 `pending + lag`，包括已 reserve 未 ACK 和尚未投递给 consumer 的消息。
- `queued` 状态数 = 数据库已排队但未成功认领的任务数，两者可能短暂不同。
- `running` 状态任务数 = 瞬时正在处理 task 的 worker 数近似值。
- `worker_busy_time_ms / (N * observation_window_ms)` = task-processing utilization。

当前 busy time 直接使用 `finished_at - started_at`，覆盖 claim 后到完成回写的任务占用区间；它仍不等于 CPU utilization，也不覆盖 claim 前的 Redis 等待。

## 负载模型

本实验建议固定请求内容，改变 worker 数量。

| 组别 | 并发用户 | worker_count | 持续时间 | 目标 |
|---|---:|---:|---|---|
| A | 30 | 1 | 5 min | 单 worker 是否堆积 |
| B | 30 | 2 | 5 min | 增加 worker 是否降低 queue_wait |
| C | 30 | 4 | 5 min | P95 是否继续下降 |
| D | 30 | 8 | 5 min | utilization 是否明显下降 |

当前 reference 使用真实独立 worker 进程执行确定性 mock workload。它验证平台扩缩容链路，不验证真实 RAG/LLM 性能。

## 变量

| 类型 | 变量 |
|---|---|
| 自变量 | worker_count |
| 因变量 | queue_length、worker_utilization、p95_queue_wait、p99_queue_wait、throughput |
| 控制变量 | 并发用户、请求模板、top_k、数据集、调度策略、运行时长 |

本实验只变 worker_count，不同时改变 top_k、query 或调度策略。

## 指标

| 指标 | 说明 |
|---|---|
| queue_length_avg | 平均队列长度 |
| queue_length_peak | 峰值队列长度 |
| p95_queue_wait_ms | 95% 任务排队等待 |
| p99_queue_wait_ms | 99% 任务排队等待 |
| worker_utilization | worker 忙碌时间 / 可用时间 |
| active_workers | 当前运行中的 worker 数 |
| tasks_per_minute | 完成任务吞吐 |
| error_rate | 失败任务比例 |
| worker_cpu_percent_sum | Docker 采样的 worker 容器 CPU 百分比之和 |
| worker_memory_mib_sum | worker 容器已用内存之和 |

## worker utilization 计算

当前 reference 使用任务占用 wall time：

```text
task_processing_utilization = total_claimed_task_time / total_available_time
```

如果有 N 个 worker，压测时长 T：

```text
total_available_time = N * T
```

其中：

```text
total_claimed_task_time = sum(finished_at - started_at)
```

观察窗口：

```text
T = max(finished_at) - min(created_at)
```

这个口径包含任务认领后的 workload 和完成回写等待，不包含 claim 之前的空闲轮询。它不是 CPU utilization。

## 已执行 Reference Smoke

运行命令：

```powershell
cd 50_项目产出\P03_AI_Workload_Platform\p03_service
.\scripts\run_worker_scaling_smoke.ps1 `
    -WorkerCounts 1,2,4 `
    -Users 5 `
    -SpawnRate 5 `
    -RunTime 10s `
    -SleepMs 25 `
    -RequestsPerUser 5
```

每组使用新 volume、唯一 `run_id`、固定 pacing，并强制校验 Locust 最终请求数等于数据库 task 数。

| workers | tasks | API failure | API P95 | queue P95 | queue P99 | task utilization |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 195 | 0 | 70 ms | 6598.49 ms | 6976.23 ms | 0.841 |
| 2 | 195 | 0 | 86 ms | 463.04 ms | 509.03 ms | 0.814 |
| 4 | 190 | 0 | 82 ms | 198.22 ms | 278.32 ms | 0.403 |

本轮观察到 worker 增加时 queue-wait 尾延迟下降，4 worker 的可用时间利用率也明显下降。该表只有每组一轮，2-worker API P99 还出现本机抖动，不能写成稳定规律或科研结论。

## 已执行 Repeated Reference

```powershell
.\scripts\run_worker_scaling_repeated.ps1 `
    -WorkerCounts 1,2,4 `
    -Repeats 3 `
    -Users 5 `
    -RunTime 5s `
    -SleepMs 25 `
    -RequestsPerUser 5 `
    -RandomSeed 20260711
```

| workers | runs | HTTP failures | queue P95 mean [95% CI] | queue peak mean [95% CI] | task utilization mean [95% CI] |
|---:|---:|---:|---:|---:|---:|
| 1 | 3 | 0 | 2673.41 [1940.58, 3406.25] ms | 34.67 [22.16, 47.17] | 0.825 [0.788, 0.862] |
| 2 | 3 | 0 | 398.44 [124.14, 672.75] ms | 7.33 [2.16, 12.50] | 0.722 [0.580, 0.864] |
| 4 | 3 | 0 | 225.58 [112.03, 339.14] ms | 0.00 [0.00, 0.00] | 0.441 [0.412, 0.470] |

每次运行保存 `timeseries.csv` 和 `worker_resources.csv`。CPU 指标是 Docker
容器采样值之和，不等于 task-processing utilization，也不是整机 CPU 百分比。
三次运行的区间仍宽，只能说明这台机器、这个短时 mock workload 下的观察。

## 记录表

| run_id | users | worker_count | queue_length_avg | queue_length_peak | p95_queue_wait_ms | p99_queue_wait_ms | avg_task_runtime_ms | worker_utilization | tasks_per_minute | error_rate | 观察 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| A | 30 | 1 |  |  |  |  |  |  |  |  |  |
| B | 30 | 2 |  |  |  |  |  |  |  |  |  |
| C | 30 | 4 |  |  |  |  |  |  |  |  |  |
| D | 30 | 8 |  |  |  |  |  |  |  |  |  |

## 误判提醒

| 现象 | 可能解释 | 需要追加检查 |
|---|---|---|
| queue_length 高、utilization 高、P95 高 | worker 不足或任务太重 | 增加 worker 或降低任务成本 |
| queue_length 高、utilization 低 | worker 没消费、队列连接错误、调度器问题 | 检查 worker logs 和队列连接 |
| utilization 低、P95 低 | worker 过多，资源浪费 | 评估成本 |
| utilization 高、error_rate 高 | worker 忙满且任务失败 | 看 error_type |
| worker_count 增加但 P95 不降 | 瓶颈不在 worker 数量 | 看数据库、检索、生成阶段 |

## 报告模板

```text
实验名称：E08-03 队列长度和 worker utilization 观察实验
实验日期：
服务版本：
请求模板：
并发用户：
调度策略：
worker_count 组别：

结果表：
| worker_count | queue_peak | p95_queue_wait | p99_queue_wait | utilization | throughput | error_rate |
|---|---|---|---|---|---|---|

观察：
- queue_length 是否持续增长？
- worker_utilization 是否接近 1.0？
- 增加 worker 后 P95/P99 是否下降？
- utilization 是否明显下降？

瓶颈判断：
- 当前瓶颈更像 worker 不足、任务太重、队列连接问题还是其他阶段？

和 P01/M05 的对照：
- 是否出现“worker 增加 -> P95 下降 -> utilization 下降”的现象？

局限：
- 是否使用模拟 worker？
- 是否没有真实 LLM？
- 是否只在本机测试？

下一步：
- 将结果写入 RQ01 工程压测实验记录。
```

## 和 M05/P01 的连接

P01 已经观察过：

```text
增加 worker 数量能降低 P95/P99，
但可能降低 worker utilization。
```

E08-03 要做的是在 P03 中验证同类现象是否出现。当前不能直接声称 P03 已证明该规律，只能记录真实压测观察。

## 和 RQ01 的连接

RQ01 的 H3 是：

```text
增加 worker 数量可以降低 P95/P99，但可能降低 worker utilization。
```

本实验提供 H3 的工程压测数据入口：

- worker_count。
- P95/P99 queue wait。
- worker_utilization。
- throughput。
- error_rate。
- queue_length_peak。

这些数据后续写入：

- [[60_科研训练/研究项目/RQ01_RAG_Agent请求调度尾延迟/03_实验记录|RQ01 实验记录]]
- [[60_科研训练/研究项目/RQ01_RAG_Agent请求调度尾延迟/04_实验报告|RQ01 实验报告]]

## 验收标准

- [x] reference 已执行随机化 1/2/4 worker × 3 次对比和 95% t 区间。
- [ ] 学习者补 8 worker 或说明资源上限，并亲手完成长时重复。
- [x] reference 能记录 queue length 时序和 peak。
- [x] reference 能计算 task-processing utilization。
- [x] reference 能记录 worker 容器 CPU/内存时序，并与 task utilization 区分。
- [x] reference 能记录 p95_queue_wait 和 p99_queue_wait。
- [x] reference 能展示 worker 增加后 queue P95 和 utilization 的取舍。
- [ ] 能说明该实验如何支撑 RQ01，但不提前写科研结论。
