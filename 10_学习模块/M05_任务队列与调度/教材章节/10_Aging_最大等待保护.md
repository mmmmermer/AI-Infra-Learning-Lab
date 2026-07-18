# 第 10 章：Aging / 最大等待保护

## 10.1 本章目标

第 9 章已经回答了一个问题：

```text
不同 Cost-aware 权重到底牺牲了谁？
```

你已经看到：

- token_dominant 会严重推迟 `short_high_token`。
- priority_dominant 会推迟 `low_priority_short`。
- duration_dominant 会推迟 `batch_heavy` 和 `long_low_token`。

本章开始回答下一个问题：

```text
如果某类任务被长期推迟，调度器能不能给它一点保护？
```

这就是 aging / 最大等待保护要解决的问题。

学完本章，你应该能做到：

- 解释什么是 starvation。
- 理解 aging 为什么能缓解长期等待。
- 手写一个最小 `AgingConfig`。
- 手写 `calculate_aging_cost_score`。
- 区分软 aging 和硬最大等待保护。
- 读懂 no_aging、gentle_aging、strong_aging 三组实验结果。
- 说明保护机制为什么也有代价。

本章仍然不进入多 worker、真实 RAG、Kubernetes 或 GPU 调度。

本章只解决一个问题：

```text
如何用 aging / 最大等待保护缓解某些任务长期被推迟的问题，并说明这种保护机制本身也有代价？
```

## 10.2 什么是 starvation

Starvation 通常翻译成饥饿。

在调度系统里，它不是说任务失败了，而是说：

```text
任务一直在队列里，但总是轮不到它执行。
```

例如一个策略总是优先短任务。

如果短任务不断到达，长任务可能一直被推迟。

再例如一个策略总是优先高优先级任务。

如果高优先级任务持续到达，低优先级任务可能长期排不到。

在第 9 章里，token_dominant 下的 `short_high_token` 就是一个很好的例子。

它执行很短，但 token 高。

因为 token 权重过高，它被系统性推迟：

```text
short_high_token no_aging 平均等待 88.40
P95 110.80
```

这就是本章要保护的对象。

## 10.3 Aging 的核心想法

Aging 的直觉很简单：

```text
任务等得越久，就逐渐提高它的调度机会。
```

在 Cost-aware 里，任务的原始分数是：

```text
cost_score = duration_weight * estimated_duration
           + token_weight * token_count
           + priority_weight * priority
```

分数越低，越先执行。

如果一个任务等了很久，我们可以给它一个 aging bonus：

```text
aging_score = cost_score - aging_bonus
```

等得越久，`aging_bonus` 越大。

这样任务的有效分数会慢慢下降。

也就是说：

```text
原本因为成本高被排到后面的任务，会随着等待时间增加逐渐往前移动。
```

## 10.4 AgingConfig 需要哪些字段

P01 当前使用的配置是：

```python
@dataclass(frozen=True)
class AgingConfig:
    wait_weight: float
    max_wait_threshold: float
    max_wait_bonus: float
    enforce_max_wait: bool = False
```

四个字段分别表示：

| 字段 | 含义 |
|---|---|
| `wait_weight` | 每等待 1 个时间单位，成本分数降低多少 |
| `max_wait_threshold` | 等待超过多少时间后认为进入保护区 |
| `max_wait_bonus` | 超过阈值后额外降低多少分 |
| `enforce_max_wait` | 是否启用硬最大等待保护 |

先不要急着调这些值。

本章要先理解它们在表达什么策略：

```text
wait_weight 表示温和补偿。
max_wait_threshold 表示等待红线。
max_wait_bonus 表示超过红线后的额外保护。
enforce_max_wait 表示是否直接把超时任务提到前面。
```

## 10.5 手写 aging score

最小函数如下：

```python
def calculate_aging_cost_score(
    task: Task,
    weights: CostWeights,
    current_time: float,
    aging_config: AgingConfig,
) -> float:
    wait_time = max(0.0, current_time - task.submit_time)
    aging_bonus = wait_time * aging_config.wait_weight

    if wait_time >= aging_config.max_wait_threshold:
        aging_bonus += aging_config.max_wait_bonus

    return calculate_cost_score(task, weights) - aging_bonus
```

这里有几个关键点。

第一，等待时间是：

```text
current_time - task.submit_time
```

第二，等待时间不能是负数。

所以要写：

```python
wait_time = max(0.0, current_time - task.submit_time)
```

第三，aging 是从原始成本分数里减掉 bonus。

因为分数越低越靠前。

第四，如果等待超过阈值，就给额外 bonus。

这相当于告诉调度器：

```text
这个任务已经等太久了，不应该继续被无限推迟。
```

## 10.6 软 aging 和硬最大等待保护

本章要区分两种保护。

第一种是软 aging：

```text
等待越久，分数逐渐下降。
```

但它不保证任务一定马上执行。

如果一个任务原始成本很高，轻微 aging 可能不够。

第二种是硬最大等待保护：

```text
一旦任务等待超过阈值，就把它放进优先保护集合。
```

P01 的逻辑是：

```python
if aging_config.enforce_max_wait:
    overdue_tasks = [
        task for task in tasks
        if current_time - task.submit_time >= aging_config.max_wait_threshold
    ]
    if overdue_tasks:
        protected = sorted(overdue_tasks, key=lambda task: (task.submit_time, task.id))
        ...
        return protected + normal
```

也就是说：

```text
如果有超时任务，先从超时任务里按到达时间选。
```

这比软 aging 更强。

它不是“慢慢加分”，而是直接说：

```text
超过最大等待阈值的任务，必须被保护。
```

## 10.7 三组配置代表三种保护强度

P01 当前有三组配置：

| 配置 | 含义 |
|---|---|
| `no_aging` | 不做等待保护 |
| `gentle_aging` | 等待越久，成本分数略微下降 |
| `strong_aging` | 等待超过阈值后启用硬最大等待保护 |

对应代码：

```python
AGING_CONFIG_PRESETS = {
    "no_aging": AgingConfig(
        wait_weight=0.0,
        max_wait_threshold=999999.0,
        max_wait_bonus=0.0,
    ),
    "gentle_aging": AgingConfig(
        wait_weight=0.15,
        max_wait_threshold=40.0,
        max_wait_bonus=10.0,
    ),
    "strong_aging": AgingConfig(
        wait_weight=0.35,
        max_wait_threshold=25.0,
        max_wait_bonus=25.0,
        enforce_max_wait=True,
    ),
}
```

这里的数字不是最终答案。

它们只是三种实验口径：

```text
不保护
轻微保护
强保护
```

实验目标是观察：

```text
保护强度增加以后，极端等待是否下降？代价落到谁身上？
```

## 10.8 为什么本章使用 token_dominant

P01 的 aging 实验使用的是：

```python
TOKEN_DOMINANT_WEIGHTS
```

原因是第 9 章已经发现：

```text
token_dominant 会严重推迟 short_high_token。
```

也就是说，token_dominant 已经制造了一个清楚的问题。

本章就在这个问题上测试保护机制。

这是一条很好的实验逻辑：

```text
先用分组分析发现谁被牺牲。
再用 aging / 最大等待保护测试能不能缓解。
```

如果你还没发现谁被牺牲，就直接加 aging，实验目标会很模糊。

## 10.9 运行 aging 实验

运行目录：

```text
50_项目产出/P01_Mini_Scheduler/mini_scheduler
```

运行命令：

```bash
python examples/run_aging_experiment.py
```

它会做两件事。

第一，输出总表：

```text
no_aging
gentle_aging
strong_aging
```

第二，输出 no_aging 和 strong_aging 的 task_type 分组对比。

本章两个都要看。

因为 aging 的核心问题就是：

```text
总指标有没有改善？
谁因为保护机制受益？
谁为保护机制付出代价？
```

## 10.10 总表结果怎么读

P01 当前总表结果是：

| 配置 | 平均等待时间 | 最大等待时间 | P95 | P99 | 最大队列长度 | worker 利用率 |
|---|---:|---:|---:|---:|---:|---:|
| no_aging | 48.63 | 110.80 | 110.60 | 110.80 | 24 | 0.92 |
| gentle_aging | 48.63 | 110.80 | 110.60 | 110.80 | 24 | 0.92 |
| strong_aging | 42.66 | 104.40 | 100.80 | 104.40 | 26 | 0.92 |

先看 no_aging 和 gentle_aging。

它们完全一样：

```text
平均等待 48.63
P95 110.60
P99 110.80
```

这说明 gentle_aging 在当前任务流和当前权重下不够强。

换句话说：

```text
轻微等待补偿没有足以改变任务顺序。
```

再看 strong_aging：

```text
平均等待 42.66
最大等待 104.40
P95 100.80
P99 104.40
```

这些指标都比 no_aging 更好。

这说明强保护确实缓解了极端等待。

但注意最大队列长度：

```text
no_aging: 24
strong_aging: 26
```

它略微上升。

这提醒你：

```text
保护机制改变了调度顺序，不是免费消除拥塞。
```

## 10.11 分组结果怎么读

分组对比重点是：

| task_type | no_aging 平均等待 | strong_aging 平均等待 | 变化 |
|---|---:|---:|---|
| short_high_token | 88.40 | 52.40 | 明显改善 |
| batch_heavy | 90.80 | 68.80 | 改善 |
| urgent_medium | 67.20 | 65.20 | 平均略改善，但 P95 变差 |
| low_priority_short | 0.40 | 4.00 | 被轻微牺牲 |

先看 `short_high_token`。

这是第 9 章里 token_dominant 牺牲最明显的一类任务。

strong_aging 后：

```text
88.40 -> 52.40
```

改善很明显。

再看 `batch_heavy`：

```text
90.80 -> 68.80
```

也被改善。

这说明强保护能帮助长期等待的高成本任务。

但 `low_priority_short` 变差了：

```text
0.40 -> 4.00
```

虽然绝对值仍然不高，但方向很重要。

保护机制把一部分执行机会让给了等待太久的任务。

所以原本很快能执行的短任务，会稍微等久一点。

这就是保护机制的代价。

## 10.12 为什么 gentle_aging 没有效果

gentle_aging 的配置是：

```text
wait_weight=0.15
max_wait_threshold=40.0
max_wait_bonus=10.0
```

它没有启用硬最大等待保护。

也就是说，它只是让等待任务的分数慢慢下降。

如果原始成本差距很大，下降幅度可能不够。

例如高 token 任务的原始成本可能比低 token 任务高很多。

轻微 bonus 不能改变排序。

所以 gentle_aging 没有明显改善，不代表 aging 思路错了。

它说明：

```text
保护力度太弱时，可能无法对抗原始成本差异。
```

这也是为什么需要实验，而不是凭感觉调权重。

## 10.13 为什么 strong_aging 有效果

strong_aging 有两个特点。

第一，等待补偿更强：

```text
wait_weight=0.35
```

第二，它启用了硬最大等待保护：

```text
enforce_max_wait=True
max_wait_threshold=25.0
```

这意味着：

```text
等待超过 25 个时间单位的任务会被直接放进保护集合。
```

这能明显降低极端等待。

但它也会改变原本的排序。

例如本来应该很快执行的 `low_priority_short`，可能要给超时任务让路。

所以 strong_aging 的正确结论是：

```text
它降低了极端等待，但重新分配了等待时间。
```

而不是：

```text
strong_aging 永远最好。
```

> **可迁移的原则**：**纯优化会挤压弱势任务，aging 是公平性的最后防线。** 第 4 章 Priority 让“重要的先走”，但如果没有 aging，低优先级、长任务或低收益任务就可能长期被推迟。strong_aging 的价值不是让系统“更聪明”，而是把被优化目标拿走的等待时间补回来。
>
> 这条原则在后续工程里非常实用：
>
> - **M04 Agent**：多步骤 Agent 任务可能慢、贵、不稳定，如果永远让短 RAG 请求插队，Agent 任务会长期卡住。
> - **M06/P03**：任务状态持久化后，等待时间就能被记录，aging 才有数据基础。
> - **M08**：判断 aging 是否有效，不只看平均值，要看最差分组、max wait 和 P95/P99 是否被拉回可接受范围。

## 10.14 本章和第 11 章的边界

本章解决的是：

```text
在固定单 worker 下，如何通过策略保护长期等待任务。
```

第 11 章会解决另一个问题：

```text
如果资源不够，增加 worker 会怎样影响 P95 和利用率？
```

这两个问题不要混在一起。

Aging 是调度策略层面的保护。

多 worker 是资源数量层面的扩容。

它们都可能降低尾延迟，但含义不同：

| 方法 | 改变什么 | 代价 |
|---|---|---|
| aging | 改变任务顺序 | 一些原本快的任务可能变慢 |
| 增加 worker | 增加处理能力 | 资源成本上升，利用率可能下降 |

本章先把策略保护讲清楚。

第 11 章再谈资源数量。

## 10.15 和 P01 参考答案对照

本章对应文件：

```text
50_项目产出/P01_Mini_Scheduler/mini_scheduler/scheduler/strategies.py
50_项目产出/P01_Mini_Scheduler/mini_scheduler/scheduler/experiments.py
50_项目产出/P01_Mini_Scheduler/mini_scheduler/examples/run_aging_experiment.py
50_项目产出/P01_Mini_Scheduler/mini_scheduler/artifacts/aging_summary.csv
50_项目产出/P01_Mini_Scheduler/mini_scheduler/artifacts/aging_task_type_breakdown.csv
```

重点看：

```python
AgingConfig
calculate_aging_cost_score
sort_by_aging_cost
AGING_CONFIG_PRESETS
run_aging_cost
summarize_aging_cost
```

对照时要问：

第一，aging bonus 是如何计算的？

第二，为什么分数是减去 aging bonus？

第三，`enforce_max_wait=True` 时，超时任务如何被保护？

第四，strong_aging 改善了哪些任务？

第五，strong_aging 让哪些任务付出了代价？

## 10.16 本章你要做什么

本章任务分六步。

第一步，手写 `AgingConfig`。

第二步，手写 `calculate_aging_cost_score`。

第三步，先实现软 aging：

```text
cost_score - wait_time * wait_weight
```

第四步，再加入最大等待阈值：

```text
wait_time >= max_wait_threshold
```

第五步，跑：

```bash
python examples/run_aging_experiment.py
```

第六步，写出三条解释：

```text
gentle_aging 为什么没有改善？
strong_aging 改善了哪些指标？
strong_aging 的代价是什么？
```

## 10.17 常见错误

第一个错误：把 aging 理解成提高 priority。

Aging 在这里不是改 `priority` 字段，而是动态改变成本分数。

第二个错误：忘记当前分数越低越先执行。

所以 aging bonus 要从成本分数里减掉。

第三个错误：只看总表，不看分组。

保护机制通常会让某些任务受益，也会让另一些任务付出代价。

第四个错误：看到 gentle_aging 没效果，就说 aging 没用。

更准确的说法是：

```text
当前 gentle_aging 配置不够强，没能改变排序。
```

第五个错误：把 strong_aging 当成免费优化。

它降低了极端等待，但也让部分原本很快的任务等待上升。

第六个错误：提前进入多 worker。

本章先固定资源数量，只研究策略保护。

## 10.18 本章复盘问题

你可以用下面问题检查自己。

1. starvation 在调度系统里是什么意思？
2. aging 为什么能缓解长期等待？
3. 为什么 aging bonus 要从 cost_score 里减掉？
4. gentle_aging 为什么在当前实验里没有明显效果？
5. strong_aging 为什么能降低 P95/P99？
6. strong_aging 改善了哪些 task_type？
7. strong_aging 让哪些 task_type 付出了代价？
8. aging 和增加 worker 有什么区别？
9. 为什么保护机制也需要报告代价？

## 10.19 本章检查标准

- 能解释 starvation、aging、最大等待保护的关系。
- 能写出最小 aging score，并说明为什么等待越久成本分数应越低。
- 能区分 gentle_aging 无明显效果和 aging 机制无效这两种说法。
- 能解释 strong_aging 降低极端等待的同时会让哪些任务付出代价。
- 能同时读总表和分组表，不把保护机制说成免费优化。
- 能说明本章仍然固定 worker 数量，不把 aging 和扩容混为一谈。

## 10.20 本章小结

本章把第 9 章发现的“谁被牺牲了”推进到“如何保护长期等待任务”。

你现在应该能理解：

```text
Aging / 最大等待保护不是让所有任务一起变快，而是限制某些任务被无限推迟。
```

P01 当前结果说明：

- gentle_aging 没有明显改变结果，说明保护力度太弱。
- strong_aging 降低了 average、max wait、P95 和 P99。
- strong_aging 明显改善 `short_high_token` 和 `batch_heavy`。
- strong_aging 也让 `low_priority_short` 等原本很快的任务等待上升。
- 保护机制不是免费午餐，它是在重新分配等待时间。

本章最重要的能力是：

```text
能解释为什么某个保护机制有效，也能说清楚它的代价。
```

如果这些内容能说清楚，就可以进入第 11 章：多 worker 与资源利用率。

---
