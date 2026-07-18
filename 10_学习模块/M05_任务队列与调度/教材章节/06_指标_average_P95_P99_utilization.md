# 第 6 章：指标：average / P95 / P99 / utilization

## 6.1 本章目标

前面你已经写了三种策略：

- FIFO
- Priority
- SJF

现在问题来了：你怎么判断一个策略表现好不好？

只看执行顺序不够。

只说“感觉更快”也不够。

你需要指标。

学完本章，你要能做到：

- 计算 waiting time。
- 计算 turnaround time。
- 计算 average。
- 理解 P95 / P99 的含义。
- 理解 worker utilization 的含义。
- 用同一套指标比较 FIFO / Priority / SJF。
- 解释为什么平均值不够。

本章仍然只使用小样例，不进入高峰负载。高峰负载会放到第 7 章。

## 6.2 为什么指标是调度系统的一部分

调度策略不是写完就结束。

你必须回答：

```text
这个策略到底改善了什么？
又牺牲了什么？
```

这就需要指标。

没有指标时，你只能说：

```text
SJF 看起来更快。
Priority 看起来更照顾重要任务。
FIFO 看起来更公平。
```

有指标后，你可以说：

```text
SJF 在这组任务中把平均等待时间从 3.50 降到 3.25。
Priority 在这组任务中把 P95/P99 拉高到 13.00，因为低优先级短任务被推迟。
FIFO 平均等待不是最低，但行为稳定，尾部没有被拉爆。
```

这就是工程表达和感觉判断的区别。

## 6.3 最重要的时间字段

先复习第 2 章的时间字段。

| 字段 | 含义 |
|---|---|
| `submit_time` | 任务进入系统的时间 |
| `start_time` | worker 真正开始执行任务的时间 |
| `finish_time` | worker 执行完成任务的时间 |
| `estimated_duration` | 任务预计执行耗时 |

从这些字段可以推出两个最基础指标：

```text
waiting_time = start_time - submit_time
turnaround_time = finish_time - submit_time
```

waiting time 关注“任务等了多久才开始”。

turnaround time 关注“任务从提交到完成总共用了多久”。

在调度策略对比里，waiting time 通常更直接反映排队效果。

turnaround time 则包含等待和执行本身：

```text
turnaround_time = waiting_time + actual_duration
```

在当前模拟里，actual duration 近似等于 `estimated_duration`。

## 6.4 手写 waiting time

先写最小函数：

```python
def calculate_wait_time(task: Task) -> float:
    if task.start_time is None:
        raise ValueError(f"task {task.id} has not started")
    return task.start_time - task.submit_time
```

为什么要检查 `start_time is None`？

因为如果任务还没开始，就不能计算等待时间。

直接写：

```python
return task.start_time - task.submit_time
```

会有两个问题：

第一，`start_time` 可能是 `None`，代码会报错。

第二，更重要的是，语义上不对。没有开始执行的任务，等待时间还没有最终确定。

P01 参考答案里也是这样做的。

## 6.5 手写 turnaround time

再写周转时间：

```python
def calculate_turnaround_time(task: Task) -> float:
    if task.finish_time is None:
        raise ValueError(f"task {task.id} has not finished")
    return task.finish_time - task.submit_time
```

turnaround time 比 waiting time 更完整，因为它包含执行时间。

例如：

```text
submit_time = 1
start_time = 5
finish_time = 7
```

那么：

```text
waiting_time = 5 - 1 = 4
turnaround_time = 7 - 1 = 6
```

这说明任务等了 4 个时间单位，执行用了 2 个时间单位，从提交到完成一共用了 6 个时间单位。

## 6.6 手写 average

平均值是最容易理解的汇总指标。

```python
def average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
```

它回答的是：

```text
整体上，每个任务平均等多久？
```

例如等待时间是：

```text
0.0, 4.0, 5.0, 5.0
```

平均等待时间是：

```text
(0 + 4 + 5 + 5) / 4 = 3.5
```

平均值很好用，但它有一个问题：它会把不同任务的体验揉在一起。

如果大多数任务很快，少数任务特别慢，平均值可能没有充分暴露尾部问题。

## 6.7 为什么平均值不够

看两个任务集。

任务集 A：

```text
等待时间：5, 5, 5, 5
平均等待：5
```

任务集 B：

```text
等待时间：0, 0, 0, 20
平均等待：5
```

两个任务集平均等待都是 5。

但它们的体验完全不同。

任务集 A 是所有任务都一样慢。

任务集 B 是大部分任务很快，但有一个任务特别惨。

如果那个特别惨的任务是关键用户请求，或者是某类长期被牺牲的任务，平均值就掩盖了问题。

这就是为什么要看 P95 / P99 / max wait。

> **这个 A/B 对比里藏着一条贯穿所有性能工程的原则,务必刻进脑子:平均值会掩盖分布,尤其掩盖尾部。** 任务集 B 的那个等了 20 的任务,在平均值 5 里**完全看不见**——而它很可能就是你最该关心的那个用户(关键请求、付费大客户、被反复牺牲的长任务)。
>
> 为什么尾部比平均更重要?因为**用户体验是由最差的那几次决定的,不是由平均决定的。** 一个 App 平时很快、但每 20 次卡一次,用户记住的是"卡",不是"平时快"。系统领域有句名言:"平均延迟是给管理层看的,P99 才是用户真正感受到的。"
>
> **可迁移的原则**：**衡量性能永远不要只看平均值，要看分布、尤其看尾部（P95/P99/max）；一个被平均值掩盖的尾部问题，往往正是最该解决的问题。** 这条是 M08 监控压测的灵魂——你会发现压测报告的核心从来不是"平均 QPS"，而是"P99 延迟在多大压力下崩掉"。也是为什么 RQ01 整个研究问题是围绕"尾延迟"而不是"平均延迟"展开的。**从今天起，看到任何"平均"数字，都要追问一句：那最差的 5% 呢？**

## 6.8 percentile 是什么

P95 / P99 属于 percentile，也就是百分位数。

可以先用直觉理解：

```text
P95 表示 95% 的任务等待时间不超过这个值。
P99 表示 99% 的任务等待时间不超过这个值。
```

在工程里，P95 / P99 常用来观察尾部体验。

平均值回答：

```text
整体平均怎么样？
```

P95 / P99 回答：

```text
尾部任务有多糟？
```

调度系统里，这两个问题都重要。

## 6.9 手写一个简单 percentile

P01 里的 percentile 实现是：

```python
import math


def percentile(values: list[float], percentile_value: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = math.ceil(percentile_value * len(ordered)) - 1
    index = max(0, min(index, len(ordered) - 1))
    return ordered[index]
```

然后：

```python
def p95(values: list[float]) -> float:
    return percentile(values, 0.95)


def p99(values: list[float]) -> float:
    return percentile(values, 0.99)
```

第一轮你不需要纠结所有 percentile 定义的细微差别。不同系统可能有不同插值方法。

当前教材只需要一个稳定、可复现、容易理解的版本。

这段代码做了四件事：

第一，把 values 排序。

第二，按照百分位计算索引。

第三，防止索引越界。

第四，返回对应位置的值。

## 6.10 小样例里 P95/P99 为什么不明显

第 2 章的任务集只有 4 个任务。

这么小的数据集里，P95/P99 往往会接近最大值。

例如：

```text
等待时间：0, 4, 5, 5
```

P95 和 P99 都会落在最后一个值附近，也就是 5。

这没问题。

你现在要先学会：

```text
如何计算，如何解释。
```

真正看出 P95/P99 的价值，要到第 7 章高峰负载实验。因为任务数量变多、排队变严重、尾部差异才会明显。

所以本章只打基础，不急着做大结论。

> **可迁移的原则**：**任何指标结论都依赖样本规模和负载条件；小样本里看不出尾部，不代表尾部不重要。** 在 4 个任务的小例子里，P99 很可能接近 max，这只是统计粒度太粗，不是 P99 没价值。到第 7 章高峰负载、M08 压测和 RQ01 科研实验里，任务数量变多、排队变重，尾部指标才会真正暴露系统风险。

## 6.11 worker utilization 是什么

前面指标都在看任务体验。

worker utilization 看的是资源利用率。

公式是：

```text
worker_utilization = worker.total_busy_time / total_time
```

它回答的是：

```text
worker 有多少比例的时间真的在干活？
```

例如：

```text
worker 总共忙了 16 个时间单位
整个模拟从 0 到 16
utilization = 16 / 16 = 1.0
```

如果 worker 总共忙了 16，但模拟时间到 32：

```text
utilization = 16 / 32 = 0.5
```

说明有一半时间 worker 是空闲的。

## 6.12 utilization 为什么重要

调度系统不能只看延迟。

如果你加很多 worker，等待时间可能下降，但资源利用率也可能下降。

这就是工程里的成本问题。

例如：

```text
1 个 worker：P95 很高，但 utilization 很高。
8 个 worker：P95 很低，但 utilization 可能很低。
```

哪一个更好？

不能只看一个指标。

在线服务可能愿意牺牲利用率换低延迟。

离线批处理可能更关注资源利用率。

所以 utilization 是连接调度策略和资源成本的重要指标。

本章先理解概念。多 worker 利用率会在第 11 章详细展开。

> **可迁移的原则**：**高利用率不一定代表系统健康，它也可能意味着系统已经逼近容量天花板，几乎没有缓冲。** utilization 接近 1.0 时，worker 看起来“没有浪费”，但这也说明新任务一来就很容易排队，任何突发流量、慢请求或外部依赖抖动都可能把 P95/P99 打穿。
>
> 这就是第 1 章“识别取舍”三问题里的典型场景：你优化了资源成本，可能牺牲了尾延迟和稳定余量。后面会反复遇到这件事：
>
> - **第 7 章**：高峰负载下，高 utilization 往往和队列堆积一起出现。
> - **第 11 章**：增加 worker 会降低 P95/P99，但也会降低 utilization，本质是在用资源冗余换延迟稳定。
> - **M08/P03**：做压测和平台容量规划时，不能只问“资源有没有跑满”，还要同时看 queue length、P95/P99、error rate 和成本。

## 6.13 手写 worker utilization

最小函数如下：

```python
def calculate_worker_utilization(worker: Worker, total_time: float) -> float:
    if total_time <= 0:
        return 0.0
    return worker.total_busy_time / total_time
```

这里要检查 `total_time <= 0`，避免除以 0。

在单 worker 小样例里，如果任务连续执行，中间没有空闲，utilization 往往是 1.0。

但如果任务之间到达间隔很大，worker 会空等，utilization 就会下降。

例如：

```text
task-001 submit_time=0, duration=1
task-002 submit_time=10, duration=1
```

worker 忙碌时间是 2。

总模拟时间是 11。

utilization 大约是：

```text
2 / 11 = 0.18
```

这说明 worker 大部分时间在等任务。

## 6.14 用同一套指标比较三种策略

现在把前面三种策略的结果统一放进指标表。

P01 小样例结果是：

| 策略 | 平均等待时间 | 平均周转时间 | P95 | P99 | worker 利用率 |
|---|---:|---:|---:|---:|---:|
| FIFO | 3.50 | 7.50 | 5.00 | 5.00 | 1.00 |
| Priority | 5.25 | 9.25 | 13.00 | 13.00 | 1.00 |
| SJF | 3.25 | 7.25 | 5.00 | 5.00 | 1.00 |

这张表应该这样读。

FIFO：

```text
平均等待中等，尾部没有特别爆炸，行为稳定。
```

Priority：

```text
平均等待更差，P95/P99 也更差，说明低优先级短任务被推迟到最后。
```

SJF：

```text
平均等待最低，因为短任务更早执行。
```

worker utilization 都是 1.00，说明这组小样例里 worker 一直在忙，策略差异不是因为资源空闲，而是因为执行顺序不同。

## 6.15 指标解释要避免过度结论

这张小表不能推出：

```text
SJF 永远最好。
Priority 没有用。
FIFO 一定稳定。
```

它只能推出：

```text
在这组小样例里，SJF 平均等待最低；Priority 因为推迟低优先级短任务，尾部等待变差；FIFO 作为 baseline 行为稳定。
```

工程报告里要避免把小样例结论夸大。

真正的稳定结论需要：

- 更大的任务集。
- 低负载和高峰负载对比。
- 不同 worker 数量对比。
- 分组指标。
- 多轮实验。

这些会在后面章节逐步展开。

## 6.16 和 P01 参考答案对照

指标参考代码位置：

```text
50_项目产出/P01_Mini_Scheduler/mini_scheduler/scheduler/metrics.py
```

对应函数：

```python
calculate_wait_time
calculate_turnaround_time
average
percentile
p95
p99
calculate_worker_utilization
```

你对照时重点看：

第一，函数是否只做一件事。

第二，空列表和异常状态是否有处理。

第三，P95/P99 是否用同一套 percentile 口径。

第四，utilization 是否处理了 `total_time <= 0`。

## 6.17 本章对应哪些后续内容

本章是后面实验章节的基础。

第 7 章高峰负载会用：

- average wait
- max wait
- P95
- P99
- queue length

第 8 章 Cost-aware 会用：

- average wait
- P95/P99
- task_type 分组指标

第 11 章多 worker 会重点用：

- P95/P99
- worker utilization

所以第 6 章不是附属内容，而是整个实验分析的语言基础。

如果你不会算指标，后面实验就会变成“跑了一堆结果但不知道怎么解释”。

## 6.18 常见错误

第一个错误：只看平均值。

平均值可能掩盖尾部任务的糟糕体验。

第二个错误：P95/P99 口径每次都变。

同一组实验必须用同一套 percentile 计算方法。

第三个错误：忘记检查任务是否已经开始或完成。

未开始任务不能算最终 waiting time，未完成任务不能算 turnaround time。

第四个错误：把 utilization 当成越高越好。

利用率高说明资源不浪费，但也可能说明系统接近饱和，尾延迟会变差。

第五个错误：用不同任务集比较指标。

策略对比必须保持输入一致。

## 6.19 本章你要做什么

本章任务分六步。

第一步，手写：

```python
calculate_wait_time
calculate_turnaround_time
average
percentile
p95
p99
calculate_worker_utilization
```

第二步，用 FIFO 的 completed tasks 计算 waiting time 列表。

第三步，用 Priority 和 SJF 的结果也计算同样指标。

第四步，把三种策略放进一张表。

第五步，用自己的话解释：

```text
谁平均等待最低？
谁尾部等待最差？
worker utilization 是否有差异？
为什么这些指标会这样？
```

第六步，对照 P01 的 `metrics.py`。

## 6.20 本章复盘问题

你可以用下面问题检查自己。

1. waiting time 和 turnaround time 有什么区别？
2. 为什么 average 不够？
3. P95 / P99 大致表示什么？
4. 为什么小样例里的 P95/P99 不一定明显？
5. worker utilization 是什么？
6. utilization 高一定好吗？
7. 为什么策略对比必须使用同一组任务和同一套指标？

## 6.21 本章检查标准

- 能手写 waiting time、turnaround time、average、percentile、P95/P99。
- 能计算 worker utilization。
- 能用同一套指标比较 FIFO / Priority / SJF。
- 能解释为什么 average 不足以反映尾部体验。
- 能说明 utilization 高为什么不一定代表系统健康。
- 能避免用不同任务集比较不同策略。

如果这些问题能说清楚，就可以进入第 7 章：高峰负载实验。

---
