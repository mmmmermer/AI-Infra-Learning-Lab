# 第 11 章：多 worker 与资源利用率

## 11.1 本章目标

前面几章一直在固定单 worker 的条件下讨论调度策略。

你已经学过：

- FIFO / Priority / SJF 如何改变执行顺序。
- Cost-aware 如何把多个成本信号合成分数。
- 分组分析如何看出谁被牺牲。
- Aging 如何保护长期等待任务。

这些都是策略层面的优化。

本章开始看另一个维度：

```text
如果资源数量变多，尾延迟会怎样？
```

也就是从单 worker 进入多 worker。

学完本章，你应该能做到：

- 解释为什么增加 worker 能降低 P95/P99。
- 理解 worker 数量、队列长度、尾延迟和利用率之间的关系。
- 手写一个最小多 worker 调度循环。
- 读懂 1 / 2 / 4 / 8 worker 的实验结果。
- 说明为什么利用率下降不是代码错，而是资源扩容的代价。
- 区分“调度策略优化”和“资源扩容”。

本章仍然不进入 Kubernetes、真实 RAG、GPU 调度或自动扩缩容。

本章只解决一个问题：

```text
增加 worker 为什么能降低 P95/P99，以及为什么资源利用率会下降？
```

## 11.2 策略优化和资源扩容不是一回事

先建立一个边界。

第 8-10 章讨论的是策略：

```text
在同样的资源数量下，先执行谁？
```

本章讨论的是资源数量：

```text
同时能执行多少任务？
```

策略优化能重新分配等待时间。

例如 SJF 让短任务更快，Priority 保护高优先级任务，Aging 保护等待太久的任务。

但如果高峰负载太重，单 worker 一直满负荷，策略再怎么调整也只能重新排序。

它不能凭空增加处理能力。

多 worker 的作用是：

```text
提高系统并行处理能力，减少排队。
```

但它的代价是：

```text
资源可能空闲，利用率下降。
```

所以本章不是在说“多 worker 一定更好”。

而是训练你看懂：

```text
延迟下降和资源成本上升之间的取舍。
```

## 11.3 单 worker 为什么容易出现高 P95

第 7 章高峰负载里，单 worker 的 FIFO 结果是：

```text
P95 = 97.70
worker utilization = 0.97
```

这说明两个事实。

第一，P95 很高，尾部任务等了很久。

第二，worker utilization 很高，worker 几乎一直在忙。

这时系统处于接近饱和状态。

如果任务继续到达，队列会继续积压。

单 worker 的瓶颈很直观：

```text
同一时刻只能处理一个任务。
```

如果 36 个 burst 任务密集到达，worker 只能一个一个做。

即使你用 SJF 或 Cost-aware 让一部分任务更快，仍然会有任务排在后面。

## 11.4 多 worker 的直觉

多 worker 的直觉是：

```text
如果 1 个 worker 同时只能做 1 个任务，那么 4 个 worker 同时可以做 4 个任务。
```

这会带来两个变化。

第一，队列积压变少。

因为 worker 空闲得更快，等待任务更容易被取走。

第二，尾延迟下降。

因为排在很后面的任务不需要等前面所有任务一个个执行完。

但也会带来一个变化：

```text
worker 不一定总是满的。
```

高峰过去以后，如果任务到达变少，多个 worker 会出现空闲。

所以利用率会下降。

这不是坏事本身，而是扩容的成本。

## 11.5 多 worker 调度循环怎么写

单 worker 调度循环的核心是：

```text
当前 worker 什么时候空闲？
当前有哪些任务已经到达？
选一个任务执行。
```

多 worker 只是在外面多了一步：

```text
每轮先选择最早空闲的 worker。
```

完整多 worker 循环是 E05-05 的学习者任务。教材先保留状态机伪代码：

```text
while pending is not empty:
    choose the earliest available worker with a deterministic tie-breaker
    derive current_time from worker availability and task arrivals
    filter tasks that have actually arrived
    choose one task through the selected scheduling policy
    assign a non-overlapping interval to that worker
    update task, worker, pending and completed exactly once
```

其中最关键的不变量是每一轮选择最早空闲的 worker。

如果多个 worker 同时空闲，就按 `id` 稳定排序。

这让实验结果可复现。

## 11.6 多 worker 里仍然只能选已到达任务

多 worker 不改变一个原则：

```text
不能提前调度未来任务。
```

即使有多个 worker，也只能从：

```text
submit_time <= current_time
```

的任务里选。

如果当前没有任何任务已经到达，worker 会等待下一次任务提交：

```python
if not available_tasks:
    current_time = min(task.submit_time for task in pending)
    worker.available_at = current_time
```

这一步很重要。

否则模拟会把未来任务提前执行，指标就会失真。

## 11.7 utilization 在多 worker 下怎么计算

单 worker 的利用率是：

```text
worker busy time / total simulation time
```

多 worker 的利用率要改成：

```text
所有 worker 忙碌时间之和 / (总模拟时间 * worker 数量)
```

例如：

```text
总忙碌时间 = 80
总模拟时间 = 40
worker 数量 = 4
```

那么总资源容量是：

```text
40 * 4 = 160
```

利用率是：

```text
80 / 160 = 0.50
```

这表示：

```text
整体上只有一半 worker 时间被任务占用。
```

P01 里对应的思路是把多个 worker 的 busy time 加起来，再除以 `total_time * worker_count`。

## 11.8 运行 worker 数量实验

运行目录：

```text
50_项目产出/P01_Mini_Scheduler/mini_scheduler
```

运行命令：

```bash
python examples/run_worker_count_experiment.py
```

实验设置：

```text
任务流：build_peak_load_tasks()
worker 数量：1 / 2 / 4 / 8
策略：FIFO / Priority / SJF / Cost-aware
```

本章先重点看 FIFO。

原因是 FIFO 最容易解释资源数量变化。

策略差异可以作为附加观察，但不要让它盖过本章主线。

本章主线是：

```text
worker 数量增加 -> P95/P99 降低 -> utilization 下降
```

## 11.9 FIFO 结果怎么读

FIFO 的结果是：

| workers | 平均等待 | 最大等待 | P95 | P99 | 最大队列 | 利用率 |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 48.71 | 101.45 | 97.70 | 101.45 | 31 | 0.97 |
| 2 | 19.74 | 44.40 | 42.80 | 44.40 | 29 | 0.86 |
| 4 | 5.31 | 17.20 | 15.70 | 17.20 | 22 | 0.61 |
| 8 | 0.88 | 3.70 | 3.50 | 3.70 | 11 | 0.30 |

先看 P95：

```text
1 worker: 97.70
2 workers: 42.80
4 workers: 15.70
8 workers: 3.50
```

worker 越多，P95 越低。

这是因为排队压力被更多 worker 吸收了。

再看 utilization：

```text
1 worker: 0.97
2 workers: 0.86
4 workers: 0.61
8 workers: 0.30
```

worker 越多，利用率越低。

这说明资源越来越不满。

所以 FIFO 这一组结果已经能说明本章核心：

```text
增加 worker 可以显著降低尾延迟，但会降低资源利用率。
```

## 11.10 为什么 8 个 worker 不是一定最好

8 个 worker 的 P95 很低：

```text
3.50
```

看起来非常好。

但 utilization 只有：

```text
0.30
```

这表示大部分 worker 时间处于空闲。

如果 worker 是普通线程，这可能还能接受。

但如果 worker 代表 GPU、昂贵机器、独占容器或付费推理实例，利用率 0.30 可能意味着成本很高。

所以不能只写：

```text
8 workers 最好。
```

更准确的写法是：

```text
8 workers 将 FIFO 的 P95 从 97.70 降到 3.50，但利用率从 0.97 降到 0.30，说明尾延迟改善来自显著资源冗余。
```

这才是工程表达。

## 11.11 策略差异为什么会随着 worker 增加而缩小

单 worker 时，策略差异很明显。

例如高峰负载下：

```text
FIFO P95 = 97.70
SJF P95 = 108.45
Cost-aware P95 = 108.45
```

当 worker 增加到 8 时：

```text
FIFO P95 = 3.50
SJF P95 = 3.50
Cost-aware P95 = 3.50
Priority P95 = 4.00
```

差异变小了。

原因很简单：

```text
资源足够时，排队少，策略选择空间也变小。
```

当大部分任务一到就能被 worker 接住，调度策略就没有太多机会制造巨大差异。

这和第 7 章低负载实验的结论一致：

```text
排队压力越小，策略差异越不明显。
```

> **可迁移的原则**：**加资源和优化算法是两个不同维度；资源足够时，策略差异会被资源冗余抹平。** 单 worker 高峰负载下，调度策略决定谁先等、谁后等；多 worker 足够多时，大部分任务不用等，策略就没有太多发挥空间。
>
> 这对工程判断很关键：如果 P95/P99 下降是因为 worker 从 1 个加到 8 个，你不能把功劳全部归给某个调度算法。更准确的表达应该同时写清：
>
> - **资源变化**：worker 数量增加，系统容量变大。
> - **策略变化**：FIFO/SJF/Priority/Cost-aware 在同一资源条件下的差异。
> - **成本变化**：P95/P99 下降的同时，utilization 可能下降，说明你用资源冗余购买了延迟稳定。

## 11.12 max queue length 怎么读

FIFO 的最大队列长度从：

```text
31 -> 29 -> 22 -> 11
```

整体下降。

这说明增加 worker 确实减少了积压。

但注意 2 worker 时最大队列仍然是 29。

也就是说，2 worker 虽然明显改善了 P95，但高峰期间仍然有大量任务排队。

所以 max queue length 可以帮助你判断：

```text
延迟下降是因为队列真的被压下来了，还是只是尾部任务被更快消化了？
```

它不是最终业务指标，但能帮助解释系统状态。

## 11.13 本章和 Kubernetes 的边界

看到多 worker，很容易想到 Kubernetes。

但本章不要进入 Kubernetes Scheduler。

本章里的 worker 是抽象执行资源：

```text
一个线程
一个进程
一个容器
一个模型服务实例
一个 GPU worker
```

Kubernetes 里的 Pod / Node 调度会在 M09 或后续云原生模块里展开。

本章只做概念映射：

```text
worker 数量增加，相当于可并行处理能力增加。
```

不要读源码。

不要改调度器。

不要引入真实集群。

先把模拟实验里的指标解释清楚。

## 11.14 和 P01 参考答案对照

本章对应文件：

```text
50_项目产出/P01_Mini_Scheduler/mini_scheduler/scheduler/simulator.py
50_项目产出/P01_Mini_Scheduler/mini_scheduler/scheduler/experiments.py
50_项目产出/P01_Mini_Scheduler/mini_scheduler/examples/run_worker_count_experiment.py
50_项目产出/P01_Mini_Scheduler/mini_scheduler/artifacts/worker_count_summary.csv
50_项目产出/P01_Mini_Scheduler/04_实验记录/Worker数量对P95延迟的影响.md
```

重点看：

```python
run_multi_worker
summarize_multi_worker_strategy
summarize_workers
```

对照时要问：

第一，是否每次选择最早空闲 worker？

第二，是否仍然只从已到达任务里选择？

第三，worker utilization 的分母是否乘了 worker 数量？

第四，P95 下降和 utilization 下降是否同时报告？

第五，实验是否保持任务流一致？

## 11.15 本章你要做什么

本章任务分六步。

第一步，手写稳定命名的 `workers` 列表，但不要照抄固定表达式：

```python
workers = build_workers(worker_count)  # TODO: validate count and stable ids.
```

第二步，自己实现最早空闲 worker 选择，并说明相同 `available_at` 时的 tie-breaker：

```python
def choose_earliest_worker(workers: list[Worker]) -> Worker:
    raise NotImplementedError
```

第三步，复用单 worker 的策略选择逻辑。

第四步，分别跑：

```text
worker_count = 1 / 2 / 4 / 8
```

第五步，输出：

```text
average wait
max wait
P95
P99
max queue length
worker utilization
```

第六步，用自己的话解释：

```text
P95 为什么下降？
utilization 为什么下降？
哪个 worker 数量是更合理的折中？
为什么不能只看 P95？
```

## 11.16 常见错误

第一个错误：只看延迟，不看利用率。

如果只看 P95，8 workers 最好。

如果看资源成本，就不能这么简单。

第二个错误：utilization 分母没乘 worker 数量。

多 worker 利用率必须除以：

```text
total_time * worker_count
```

第三个错误：每次随便选 worker。

实验里应该选择最早空闲 worker，并用 id 作为 tie-breaker。

第四个错误：worker 增加后还用不同任务流。

worker 数量实验必须保持同一组任务。

第五个错误：提前进入 Kubernetes。

本章只研究抽象 worker 数量，不研究真实集群调度。

## 11.17 本章复盘问题

你可以用下面问题检查自己。

1. 多 worker 和单 worker 的调度循环最大区别是什么？
2. 为什么增加 worker 会降低 P95/P99？
3. 为什么增加 worker 会降低 utilization？
4. 多 worker utilization 的分母为什么要乘 worker 数量？
5. 为什么 8 workers 不一定是最合理选择？
6. 策略优化和资源扩容有什么区别？
7. 为什么资源充足时策略差异会变小？
8. 本章为什么不进入 Kubernetes Scheduler？

## 11.18 本章检查标准

- 能写出多 worker 调度循环的核心逻辑：选择最早空闲 worker，再选择已到达任务。
- 能解释 worker 数量增加为什么通常降低 P95/P99。
- 能解释 worker 数量增加为什么可能降低 utilization。
- 能正确计算多 worker utilization，分母包含 `total_time * worker_count`。
- 能比较 1 / 2 / 4 / 8 worker 的延迟收益和资源代价。
- 能说明本章只研究抽象 worker 数量，不进入 Kubernetes Scheduler 源码或真实集群调度。

## 11.19 本章小结

本章把调度系统从单 worker 推进到了多 worker。

你现在应该理解：

```text
增加 worker 可以降低尾延迟，但会带来资源利用率下降。
```

P01 当前结果说明：

- FIFO 的 P95 从 1 worker 的 97.70 降到 8 workers 的 3.50。
- FIFO 的 utilization 从 0.97 降到 0.30。
- 多 worker 会减少队列积压，使策略差异逐渐缩小。
- 资源扩容和策略优化是两种不同手段，不能混为一谈。

本章最重要的能力是：

```text
同时报告延迟收益和资源成本。
```

如果这些内容能说清楚，就可以进入第 12 章：项目总结与复盘。

---
