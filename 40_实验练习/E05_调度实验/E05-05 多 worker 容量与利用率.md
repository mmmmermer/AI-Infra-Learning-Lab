# E05-05 多 worker 容量与利用率

## 状态与边界

- 类型：学习者实验。
- 状态：`runnable task / learner-unverified`。
- 前置：E05-03，以及 [[10_学习模块/M05_任务队列与调度/教材章节/11_多_worker_与资源利用率|第 11 章]]。
- 参考实现：完成自己的版本后，才查看 P01；本页不提供完整调度循环。

本实验验证的是确定性模拟器里的容量与利用率关系，不代表真实服务容量，也不能外推到
RAG、Agent、GPU 或 Kubernetes 集群。

## 学习目标

完成后应能够：

1. 用多个 worker 的 `available_at` 表示资源状态。
2. 保证每个任务只执行一次，同一 worker 的执行区间不重叠。
3. 在相同任务流和调度策略下比较 1、2、4、8 个 worker。
4. 分开解释 queue wait、makespan、尾延迟和 utilization，避免把扩容写成无条件收益。

## 固定输入

复用 E05-03 的固定高峰任务流，并满足：

- 输入任务和提交时间完全相同。
- 每个 worker 数量使用同一个调度策略。
- 不在不同组之间重新抽样任务。
- worker id 固定为 `worker-00`、`worker-01` 等稳定名称。

把 workload 保存为独立 JSON 或 CSV，并记录 SHA-256。实验脚本只能读取该文件，不能在
每个 worker 组内重新生成任务。

## 待实现接口

在自己的练习目录中实现下面接口；函数体由学习者完成。

```python
from collections.abc import Sequence


def simulate_worker_pool(
    tasks: Sequence["Task"],
    worker_count: int,
) -> list["TaskResult"]:
    """Return one result per task without overlapping work on a worker."""
    raise NotImplementedError
```

禁止从 P01 复制完整实现。可以使用 `heapq` 维护最早可用 worker，但必须在实验记录中解释：

- heap 中每个字段的含义。
- worker 可用时间如何更新。
- submit time 晚于 worker 可用时间时，start time 为什么仍不能早于 submit time。

## 必写测试

至少覆盖以下不变量：

```text
结果条数 == 输入任务条数
每个 task_id 恰好出现一次
start_time >= submit_time
finish_time >= start_time
同一 worker 的相邻执行区间不重叠
worker_count <= 0 时明确拒绝
相同输入重复运行得到完全相同的结果
```

不要把“worker 越多，所有指标必然严格变好”写成测试。utilization 下降可能是扩容后的正常
结果，P99 在小样本中也可能因为离散排序而不严格单调。

## 实验矩阵

| 变量 | 固定值或取值 |
|---|---|
| workload | 同一个已哈希固定文件 |
| policy | FIFO；完成后可追加 Priority/SJF |
| worker count | 1、2、4、8 |
| 重复次数 | 确定性实现为 1；若引入随机任务则至少多个固定 seed |
| 指标 | average/P95/P99 wait、makespan、throughput、per-worker utilization |

输出一行一个 `worker_count` 的 CSV，并另存逐任务结果，不能只保留汇总表。

## 结果解释模板

```text
本次扩容改变了：

没有被本实验证明的内容：

P95/P99 变化的任务级证据：

utilization 下降是否代表浪费，以及还需要哪些成本信息：

若迁移到真实服务，还需要补哪些队列、资源和故障指标：
```

## 验收

- [ ] 固定 workload、哈希、环境和完整命令已保存。
- [ ] 不变量测试全部通过。
- [ ] 1、2、4、8 worker 的逐任务结果和汇总 CSV 均存在。
- [ ] 能解释尾延迟与 utilization 的共同变化，而不是只写“扩容有效”。
- [ ] 完成实验前未查看 P01 多 worker 完整实现或结果表。
- [ ] 对照 P01 后单独记录差异，没有覆盖自己的原始结果。
