# 第 8 章：Cost-aware 调度

## 8.1 本章目标

前面你已经学过三类基础策略：

```text
FIFO：按到达顺序
Priority：按业务优先级
SJF：按预计耗时
```

这三类策略都很重要，但它们各自只盯住一个主要信号。

真实 AI workload 往往更复杂。

一个请求可能：

- 执行时间很短，但 token 很多。
- token 很少，但执行时间很长。
- 优先级很高，但成本也很高。
- 优先级很低，但其实很快就能做完。

这时只看一个字段就不够了。

Cost-aware 调度要解决的问题是：

```text
能不能把多个成本信号合成一个可解释的分数，用它来选择下一个任务？
```

学完本章，你应该能做到：

- 解释为什么 AI workload 需要成本感知调度。
- 说清楚 `estimated_duration`、`token_count`、`priority` 分别代表什么成本。
- 手写一个最小 `CostWeights` 和 `calculate_cost_score`。
- 用成本分数排序已到达任务。
- 对比 default、duration_dominant、token_dominant、priority_dominant 四种权重。
- 解释为什么 Cost-aware 没有唯一最优权重。

本章仍然不展开真实 RAG、Kubernetes、多 worker、aging 或 task_type 分组细节。

本章只解决一个问题：

```text
如何把 estimated_duration、token_count、priority 组合成一个可解释的成本分数，并观察权重变化如何改变整体指标？
```

## 8.2 为什么 FIFO / Priority / SJF 还不够

FIFO 的规则非常清楚：

```text
谁先到，谁先执行。
```

但它不关心任务成本。

如果一个很长的任务先到，后面的短任务会被挡住。

Priority 的规则也很清楚：

```text
谁更重要，谁先执行。
```

但它不关心任务是否很短，也不关心 token 成本。

一个低优先级但很短的任务，可能因为 priority 低被长期推迟。

SJF 的规则是：

```text
谁预计耗时短，谁先执行。
```

它能降低平均等待，但不关心 token，也不关心业务优先级。

在 AI / RAG / Agent 场景中，这些字段往往同时存在：

| 字段 | 表示什么 | 工程含义 |
|---|---|---|
| `estimated_duration` | 预计执行时长 | worker 会被占用多久 |
| `token_count` | 预计 token 数 | LLM 调用成本、上下文长度、生成成本 |
| `priority` | 业务优先级 | 用户请求、后台任务、批处理任务的相对重要性 |
| `submit_time` | 到达时间 | 用来保持稳定排序和避免完全无视先来任务 |

Cost-aware 的想法就是：

```text
不要只看一个字段，而是把多个字段合成一个排序信号。
```

## 8.3 Cost-aware 不是“更高级所以更好”

这里要先压住一个常见误解。

Cost-aware 不是天然比 FIFO / Priority / SJF 更好。

它只是给了你一个更灵活的表达方式。

如果权重设计合理，它可以表达：

```text
我既关心执行耗时，也关心 token 成本，还不想完全忽略业务优先级。
```

但如果权重设计不好，它也可能变得更糟。

例如 token 权重过大时，短但高 token 的任务会被推迟很久。

priority 权重过大时，低优先级短任务可能被牺牲。

duration 权重过大时，策略会接近 SJF，长任务可能被推迟。

所以本章要训练的不是“记住一个公式”，而是：

```text
能解释公式代表什么偏好，并用实验观察这个偏好带来的收益和代价。
```

## 8.4 成本分数的最小形式

P01 当前使用的最小成本分数是：

```text
cost_score = duration_weight * estimated_duration
           + token_weight * token_count
           + priority_weight * priority
```

当前约定是：

```text
priority=1 表示最高优先级
priority=2 表示普通优先级
priority=3 表示较低优先级
```

所以 `priority_weight * priority` 的含义是：

```text
priority 数字越大，成本分数越高，越靠后执行。
```

成本分数越低，越先执行。

这和 SJF 很像：

```text
estimated_duration 越短，分数越低。
```

但 Cost-aware 多加了 token 和 priority 两个维度。

## 8.5 先手写 CostWeights

不要一上来写复杂类。

先用一个最小 dataclass 表示权重：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class CostWeights:
    duration: float
    token: float
    priority: float
```

这里 `frozen=True` 的意思是：创建后不随便改。

这不是必须的，但对实验很有帮助。

因为你希望每一组权重是一个明确配置：

```text
default
duration_dominant
token_dominant
priority_dominant
```

如果实验中途到处改权重，结果就很难解释。

## 8.6 手写 calculate_cost_score

最小函数如下：

```python
def calculate_cost_score(task: Task, weights: CostWeights) -> float:
    """Return a documented weighted score using compatible feature scales."""
    raise NotImplementedError
```

先写出自己的公式和单位表，再实现代码。至少回答：priority 数值越小是否越重要、token 与
duration 是否需要归一化、权重为零或负数时系统是否允许，以及分数相同时如何稳定排序。

这个函数只做一件事：

```text
把一个任务映射成一个数字。
```

数字越小，越应该优先执行。

你可以用一个小任务手算：

```text
estimated_duration = 2.0
token_count = 500
priority = 1
weights = duration=1.0, token=0.001, priority=0.5
```

那么：

```text
cost_score = 1.0 * 2.0 + 0.001 * 500 + 0.5 * 1
           = 2.0 + 0.5 + 0.5
           = 3.0
```

另一个任务：

```text
estimated_duration = 1.0
token_count = 12000
priority = 2
```

分数是：

```text
cost_score = 1.0 * 1.0 + 0.001 * 12000 + 0.5 * 2
           = 1.0 + 12.0 + 1.0
           = 14.0
```

虽然第二个任务执行时间更短，但 token 很高，所以总分更高。

这就是 Cost-aware 和 SJF 的区别。

SJF 只会看到：

```text
duration=1.0，比 duration=2.0 更短。
```

Cost-aware 会看到：

```text
它很短，但 token 成本很高。
```

## 8.7 用成本分数排序

排序函数可以这样写：

```python
def sort_by_cost_weights(tasks: list[Task], weights: CostWeights) -> list[Task]:
    return sorted(
        tasks,
        key=lambda task: (
            calculate_cost_score(task, weights),
            task.submit_time,
            task.id,
        ),
    )
```

排序键里有三个部分：

```text
第一层：cost_score
第二层：submit_time
第三层：id
```

为什么要有 `submit_time`？

因为如果两个任务成本分数接近或相同，先到的任务应该更靠前。

为什么要有 `id`？

因为它让排序结果稳定。

如果没有稳定 tie-breaker，同样输入可能因为对象顺序不同产生不稳定结果。

这在实验里很麻烦。

你需要能复现结果，所以排序规则要稳定。

## 8.8 只能从已到达任务里选

这是本章最容易出错的地方。

不要把所有任务一开始全部排序，然后从头执行。

错误做法是：

```python
all_tasks = sort_by_cost_weights(tasks, weights)
```

然后按 `all_tasks` 顺序执行。

这会犯一个问题：

```text
未来还没到达的任务，被提前拿来参与排序。
```

真实调度器不能这样做。

正确做法仍然沿用前面章节的调度循环：

```text
每一轮只看 submit_time <= current_time 的任务。
```

也就是：

```python
available_tasks = [
    task for task in pending
    if task.submit_time <= current_time
]
```

然后只在 `available_tasks` 里选成本分数最低的任务：

```python
next_task = sort_by_cost_weights(available_tasks, weights)[0]
```

这点和 FIFO / Priority / SJF 完全一致。

区别只是选择规则变了。

调度循环不要重写。

## 8.9 四组权重代表四种偏好

P01 当前有四组权重：

| 预设 | duration | token | priority | 偏好 |
|---|---:|---:|---:|---|
| default | 1.0 | 0.001 | 0.5 | 平衡版 |
| duration_dominant | 1.5 | 0.0005 | 0.3 | 更像 SJF，重视短耗时 |
| token_dominant | 0.7 | 0.003 | 0.3 | 更重视 token 成本 |
| priority_dominant | 0.8 | 0.0005 | 2.0 | 更重视业务优先级 |

注意，不要把这些权重理解成“调参答案”。

它们只是四种实验口径。

你要观察的是：

```text
当我更重视 duration，会发生什么？
当我更重视 token，会发生什么？
当我更重视 priority，会发生什么？
```

这比背权重数字重要得多。

## 8.10 构造专门的 Cost-aware 任务流

如果任务流太简单，看不出 Cost-aware 的价值。

所以 P01 使用了一个专门的任务流：

```text
build_cost_sensitivity_tasks()
```

它构造 30 个密集到达任务，包含几类冲突任务：

| task_type | 特征 | 用途 |
|---|---|---|
| `short_high_token` | 执行短，但 token 很高 | 测 token 权重是否会推迟它 |
| `long_low_token` | 执行长，但 token 很低 | 测 duration 权重是否会推迟它 |
| `urgent_medium` | 高优先级，中等耗时 | 测 priority 权重是否会提前它 |
| `low_priority_short` | 低优先级，但很短 | 测 priority 是否牺牲短任务 |
| `batch_heavy` | 低优先级，耗时和 token 都高 | 测高成本任务是否被后置 |
| `cheap_medium` | 中等耗时，token 很低 | 测 token 主导时是否提前 |

这组任务的设计目的不是模拟所有真实情况。

它只服务一个学习目标：

```text
制造 duration、token、priority 之间的冲突，让你看见权重偏好。
```

## 8.11 运行 Cost-aware 权重实验

运行目录：

```text
50_项目产出/P01_Mini_Scheduler/mini_scheduler
```

运行命令：

```bash
python examples/run_cost_weight_experiment.py
```

这个脚本会做两件事。

第一，输出四组权重的总表：

```text
default
duration_dominant
token_dominant
priority_dominant
```

第二，输出部分权重下的 `task_type_breakdown`。

但本章先只读总表。

分组分析会放到第 9 章。

## 8.12 总表结果怎么读

P01 当前总表结果是：

| 权重预设 | 平均等待时间 | 最大等待时间 | P95 | P99 | 最大队列长度 | worker 利用率 |
|---|---:|---:|---:|---:|---:|---:|
| default | 41.97 | 104.40 | 99.60 | 104.40 | 24 | 0.92 |
| duration_dominant | 37.30 | 104.40 | 99.60 | 104.40 | 24 | 0.92 |
| token_dominant | 48.63 | 110.80 | 110.60 | 110.80 | 24 | 0.92 |
| priority_dominant | 46.63 | 104.40 | 99.60 | 104.40 | 27 | 0.92 |

先看 worker utilization：

```text
0.92
```

四组权重几乎相同。

这说明差异不是因为某组权重让 worker 更闲或更忙。

差异来自：

```text
同样资源下，任务执行顺序不同。
```

再看平均等待：

```text
duration_dominant: 37.30
default: 41.97
priority_dominant: 46.63
token_dominant: 48.63
```

在当前任务流里，duration_dominant 平均等待最低。

原因很直观：

```text
它更接近 SJF，倾向于先做短耗时任务。
```

再看 token_dominant：

```text
平均等待 48.63
P95 110.60
P99 110.80
```

它在这组任务里最差。

这说明：

```text
过度强调 token 成本，可能把某些高 token 任务推得太靠后。
```

最后看 priority_dominant：

```text
平均等待 46.63
最大队列长度 27
```

它保护高优先级任务，但可能让队列分布更不均衡。

这和第 4 章讲 Priority 时的结论一致：

```text
业务优先级是取舍，不是免费优化。
```

## 8.13 为什么 Cost-aware 没有唯一最优权重

看到这张表后，不能说：

```text
duration_dominant 最好，所以以后都用它。
```

这只是当前任务流下的结果。

如果任务流改变，结论可能变。

例如：

- 如果高 token 任务真的很贵，token_dominant 可能在成本账上更合理。
- 如果高优先级任务代表在线用户，priority_dominant 可能业务上更合理。
- 如果系统目标是整体吞吐和平均等待，duration_dominant 可能更合适。
- 如果目标是公平性和尾延迟，还需要看 P95/P99、max wait 和分组结果。

所以 Cost-aware 的正确表达不是：

```text
我找到了最优公式。
```

而是：

```text
我能把业务目标转成权重偏好，并用实验观察这个偏好的收益和副作用。
```

这才是工程上有价值的能力。

> **可迁移的原则**：**多目标系统通常没有单一最优权重；权重不是纯技术答案，而是价值选择。** Cost-aware 把延迟、token 成本、优先级放进同一个分数里，看起来像一个公式，其实是在回答“平台更愿意保护谁、节省什么、牺牲什么”。权重一变，系统偏好就变。
>
> 所以你以后设计 P03 的调度策略时，不要把 `duration_weight=0.5` 这种数字写成“标准答案”。更专业的表达是：
>
> - **先声明目标**：例如降低在线 RAG 请求尾延迟，或控制高 token 任务成本。
> - **再选权重**：让权重服务目标，而不是反过来用权重解释目标。
> - **最后用 M08 验证**：看 average、P95/P99、成本、分组等待是否真的符合这个目标。

## 8.14 本章只做总表，不做分组结论

E05-04 里已经有 `task_type_breakdown`。

它能回答：

```text
哪个任务类型被改善？
哪个任务类型被牺牲？
```

但本章先不展开。

原因是学习顺序要稳：

```text
第 8 章：先理解成本分数和权重偏好。
第 9 章：再做分组分析，看谁被牺牲。
第 10 章：最后用 aging / 最大等待保护处理极端等待。
```

如果本章同时讲权重、分组和 aging，会再次变成实验台账。

所以本章只要求你能读懂总表。

## 8.15 和 P01 参考答案对照

本章对应的 P01 文件是：

```text
50_项目产出/P01_Mini_Scheduler/mini_scheduler/scheduler/strategies.py
50_项目产出/P01_Mini_Scheduler/mini_scheduler/scheduler/workloads.py
50_项目产出/P01_Mini_Scheduler/mini_scheduler/examples/run_cost_weight_experiment.py
50_项目产出/P01_Mini_Scheduler/mini_scheduler/artifacts/cost_weight_summary.csv
```

重点看这些函数和对象：

```python
CostWeights
calculate_cost_score
sort_by_cost_weights
COST_WEIGHT_PRESETS
build_cost_sensitivity_tasks
summarize_cost_weights
```

对照时不要只看结果表。

你要检查：

第一，成本分数是否能用一句话解释。

第二，排序是否只在已到达任务里做。

第三，四组权重是否代表四种明确偏好。

第四，结果解释是否同时看 average、P95/P99、max wait 和 utilization。

## 8.16 本章你要做什么

本章任务分六步。

第一步，手写 `CostWeights`：

```python
@dataclass(frozen=True)
class CostWeights:
    duration: float
    token: float
    priority: float
```

第二步，手写 `calculate_cost_score`：

```python
def calculate_cost_score(task: Task, weights: CostWeights) -> float:
    return (
        weights.duration * task.estimated_duration
        + weights.token * task.token_count
        + weights.priority * task.priority
    )
```

第三步，手写 `sort_by_cost_weights`。

第四步，构造 6 类冲突任务，至少包含：

```text
短耗时高 token
长耗时低 token
高优先级中等耗时
低优先级短任务
低优先级高成本批任务
低 token 中等耗时任务
```

第五步，跑四组权重：

```text
default
duration_dominant
token_dominant
priority_dominant
```

第六步，用自己的话解释：

```text
哪组平均等待最低？
哪组尾部等待最差？
worker utilization 是否有变化？
为什么不能说某个权重永远最好？
```

## 8.17 常见错误

第一个错误：公式太复杂。

第一版成本分数越简单越好。

如果你自己都说不清每个权重是什么意思，就没法解释实验结果。

第二个错误：忘记 priority 的方向。

当前约定是：

```text
priority=1 最高，数字越大优先级越低。
```

所以 priority 项是加到成本分数里的。

第三个错误：全局排序所有任务。

调度时只能从已经到达的任务里选。

第四个错误：只看平均等待。

Cost-aware 很容易让平均等待变好，但把某类任务推到尾部。

第五个错误：把本章写成权重调参比赛。

本章目标不是找唯一最优权重，而是理解权重代表的策略偏好。

第六个错误：提前展开 aging。

aging 是第 10 章主题。本章最多提出风险，不展开保护机制。

## 8.18 本章复盘问题

你可以用下面问题检查自己。

1. Cost-aware 想解决 FIFO / Priority / SJF 的什么不足？
2. `estimated_duration`、`token_count`、`priority` 分别代表什么成本信号？
3. 为什么 `priority=1` 最高时，priority 项可以加到成本分数里？
4. 为什么排序时还需要 `submit_time` 和 `id` 作为 tie-breaker？
5. 为什么不能把未来还没到达的任务提前参与排序？
6. duration_dominant 为什么可能降低平均等待？
7. token_dominant 为什么可能让 P95/P99 变差？
8. 为什么 Cost-aware 没有唯一最优权重？
9. 本章为什么暂时不做 task_type 分组分析？
10. 如果要把本章写成项目结论，哪些说法是稳妥的，哪些说法太绝对？

## 8.19 本章检查标准

- 能写出最小 `CostWeights` 和 `calculate_cost_score`。
- 能解释 `estimated_duration`、`token_count`、`priority` 在成本分数里的含义。
- 能说明为什么 cost score 越低越优先，以及 `priority=1` 最高时公式应该怎么处理。
- 能用同一组任务比较 default、duration_dominant、token_dominant、priority_dominant。
- 能解释为什么 Cost-aware 没有唯一最优权重。
- 能说明本章只看总表，不提前展开 task_type 分组和 aging。

## 8.20 本章小结

本章把调度策略从单一字段推进到了多字段成本分数。

你现在应该理解：

```text
Cost-aware 调度不是神奇公式，而是把工程偏好写进排序规则。
```

P01 的当前结果说明：

- duration_dominant 在当前任务流下平均等待最低。
- token_dominant 的 average、P95、P99、max wait 都更差，说明 token 权重过高可能造成副作用。
- priority_dominant 能表达业务保护，但可能让队列更不均衡。
- worker utilization 基本相同，说明差异主要来自执行顺序，而不是资源忙闲。

本章最重要的能力是：

```text
能把权重解释成策略偏好，再用指标验证偏好带来的收益和代价。
```

如果这些内容能说清楚，就可以进入第 9 章：分组分析：谁被牺牲了。

---
