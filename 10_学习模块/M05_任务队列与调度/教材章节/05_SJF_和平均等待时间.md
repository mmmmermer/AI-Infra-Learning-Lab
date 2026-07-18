# 第 5 章：SJF 和平均等待时间

> 2026-07-10 校订：本章基础排序使用 `estimated_duration`，准确名称是 predicted SJF。只有按任务真实 `actual_duration` 排序时才是 oracle SJF。教学样例可以让估计值等于真实值来观察机制，但科研实验必须加入预测误差，并分别报告 predicted SJF 与 oracle SJF。oracle SJF 只能作为理想上界或诊断基线，不能包装成可部署策略。

## 5.1 本章目标

第 3 章的 FIFO 尊重到达顺序。

第 4 章的 Priority 尊重业务重要性。

本章的 SJF 尊重另一个目标：平均等待时间。

SJF 的全称是 Shortest Job First，意思是短任务优先。

学完本章，你要能做到：

- 解释 SJF 为什么可能降低平均等待时间。
- 手写 `sort_by_sjf`。
- 复用前面同一个单 worker 调度循环。
- 用同一组任务比较 FIFO / Priority / SJF。
- 说明 SJF 改善了谁、牺牲了谁。
- 理解为什么 `estimated_duration` 在真实系统里不一定准确。
- 理解为什么 SJF 不能选择未来才到达的短任务。

这一章只解决 SJF 一个问题，不进入高峰负载、Cost-aware 或多 worker。

## 5.2 SJF 想解决什么问题

FIFO 的问题是：长任务如果排在前面，会拖慢后面所有任务。

Priority 的问题是：它保护高优先级任务，但可能让低优先级短任务被推迟。

SJF 换了一个思路：

```text
如果一个任务很快就能完成，先把它做掉，可能会减少总体等待。
```

看一个简单例子。

假设当前有三个任务都已经到达：

| 任务 | estimated_duration |
|---|---:|
| A | 10 |
| B | 1 |
| C | 1 |

如果按 FIFO 顺序 A -> B -> C：

```text
A 等待 0
B 等待 10
C 等待 11
平均等待 = (0 + 10 + 11) / 3 = 7
```

如果按 SJF 顺序 B -> C -> A：

```text
B 等待 0
C 等待 1
A 等待 2
平均等待 = (0 + 1 + 2) / 3 = 1
```

这就是 SJF 的直觉：先处理短任务，很多任务可以更快完成，平均等待时间可能明显下降。

但它也有代价：长任务 A 被推迟了。

所以 SJF 不是“更公平”，而是“更偏向短任务”。

## 5.3 SJF 的策略目标和 Priority 不一样

Priority 的目标是业务重要性。

SJF 的目标是平均效率。

可以这样对比：

| 策略 | 优先考虑什么 | 可能牺牲什么 |
|---|---|---|
| FIFO | 到达顺序 | 短任务体验、紧急任务 |
| Priority | 业务重要性 | 低优先级任务 |
| SJF | 预计耗时短的任务 | 长任务 |

这三个策略不是线性升级关系。

不是说：

```text
FIFO < Priority < SJF
```

更准确地说，它们分别代表不同取舍：

```text
FIFO：我按先来后到处理。
Priority：我先照顾更重要的任务。
SJF：我先处理更快能完成的任务。
```

所以学习 SJF 时，不要问“它是不是最好”，而要问：

```text
它把等待时间重新分配给了谁？
```

## 5.4 SJF 只能从已经到达的任务里选

这一点和 Priority 一样重要。

SJF 的规则不是：

```text
从所有任务里选最短的。
```

而是：

```text
从当前已经到达的任务里选预计耗时最短的。
```

如果当前时间是 0，一个耗时 1 秒的短任务要到时间 10 才到达，那么它不能在时间 0 被执行。

调度器不能预知未来，也不能为了等未来短任务而让 worker 空转。

所以 SJF 依然必须遵守前面章节的调度循环：

```text
先过滤 available_tasks
再在 available_tasks 里选择 estimated_duration 最短的任务
```

这就是为什么你不能简单地写：

```python
sorted(tasks, key=lambda task: task.estimated_duration)
```

然后直接按这个全局顺序执行。

正确位置是在调度循环内部：

```python
available_tasks = [
    task for task in pending
    if task.submit_time <= current_time
]

next_task = sort_by_sjf(available_tasks)[0]
```

## 5.5 SJF 排序规则

最小实现如下：

```python
def sort_by_sjf(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (task.estimated_duration, task.submit_time, task.id))
```

排序键有三层。

第一层：`estimated_duration`

预计耗时越短，越早执行。

第二层：`submit_time`

如果两个任务预计耗时一样，就先到先执行。

第三层：`id`

如果耗时和到达时间都一样，用 id 保证稳定顺序。

P01 参考答案里也是这样写的：

```python
def sort_by_sjf(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (task.estimated_duration, task.submit_time, task.id))
```

## 5.6 继续复用同一个调度循环

到这里，你应该已经看出模式了。

FIFO：

```python
next_task = sort_by_fifo(available_tasks)[0]
```

Priority：

```python
next_task = sort_by_priority(available_tasks)[0]
```

SJF：

```python
next_task = sort_by_sjf(available_tasks)[0]
```

调度循环不用变。

变的只有 sorter。

所以你可以继续使用第 4 章的函数：

```python
sjf_result = run_single_worker_with_sorter(
    tasks,
    Worker(id="worker-sjf"),
    sort_by_sjf,
)
```

这就是策略抽象的价值：同一个调度流程，可以比较多个策略。

## 5.7 用第 2 章任务比较 FIFO / Priority / SJF

继续使用同一组任务：

| id | task_type | priority | estimated_duration | submit_time |
|---|---|---:|---:|---:|
| task-001 | rag_query | 2 | 5.0 | 0.0 |
| task-002 | agent_tool | 1 | 2.0 | 1.0 |
| task-003 | embedding | 3 | 1.0 | 2.0 |
| task-004 | long_context | 2 | 8.0 | 3.0 |

FIFO 顺序：

```text
task-001 -> task-002 -> task-003 -> task-004
```

Priority 顺序：

```text
task-001 -> task-002 -> task-004 -> task-003
```

SJF 顺序：

```text
task-001 -> task-003 -> task-002 -> task-004
```

为什么 SJF 不是 `task-003` 第一个？

因为时间 0 时只有 `task-001` 已经到达。`task-003` 虽然最短，但它时间 2 才到达，不能提前执行。

为什么 `task-003` 会排在 `task-002` 前面？

因为 `task-001` 执行完后，当前时间到了 5。此时 `task-002`、`task-003`、`task-004` 都已经到达。SJF 会看预计耗时：

```text
task-003: 1.0
task-002: 2.0
task-004: 8.0
```

所以 `task-003` 先执行。

## 5.8 指标如何变化

P01 小样例里，三种策略的指标是：

| 策略 | 平均等待时间 | 平均周转时间 | P95 | P99 | worker 利用率 |
|---|---:|---:|---:|---:|---:|
| FIFO | 3.50 | 7.50 | 5.00 | 5.00 | 1.00 |
| Priority | 5.25 | 9.25 | 13.00 | 13.00 | 1.00 |
| SJF | 3.25 | 7.25 | 5.00 | 5.00 | 1.00 |

在这组小任务里，SJF 的平均等待时间最低。

原因是它让很短的 `task-003` 提前执行，减少了短任务的等待。

但注意：这个结论只对这组小样例成立。

不能直接说：

```text
SJF 永远最好。
```

更准确的说法是：

```text
在这组任务里，SJF 通过提前执行短任务，略微降低了平均等待时间。
```

这才是工程上严谨的表达。

## 5.9 SJF 改善了谁

SJF 通常改善短任务。

在这组任务中，`task-003` 是短任务：

```text
estimated_duration = 1.0
```

FIFO 中它排在 `task-002` 后面。

SJF 中它排在 `task-002` 前面。

这会降低它的等待时间。

所以你在分析 SJF 时，要重点看：

- 短任务是否更快开始。
- 平均等待时间是否下降。
- 长任务是否被推迟。

## 5.10 SJF 牺牲了谁

SJF 可能牺牲长任务。

如果短任务不断到来，长任务可能一直被往后推。

这和 Priority 的低优先级饥饿类似，只不过 SJF 里被牺牲的是“长任务”。

例如：

```text
当前有一个 30 秒长任务等待执行。
每隔 1 秒又来一个 1 秒短任务。
```

如果系统总是优先短任务，长任务可能等很久。

所以 SJF 需要和保护机制配合：

- 最大等待时间。
- aging。
- 长任务配额。
- 分组公平性。

这些不是本章要实现的内容，但你要先知道问题存在。

## 5.11 estimated_duration 不一定准确

SJF 依赖 `estimated_duration`。

在教材模拟里，`estimated_duration` 是我们手动给的数字，所以看起来很确定。

但真实 AI workload 里，耗时经常只能估计。

例如 RAG 请求的耗时可能取决于：

- query 难度。
- 检索返回文档数量。
- rerank 是否开启。
- prompt 长度。
- 生成 token 数。
- 模型当前负载。

Agent 任务更复杂，因为它可能调用工具，也可能循环多轮。

所以 `estimated_duration=2.0` 并不一定真的执行 2 秒。

这会带来一个问题：

```text
如果估计错了，SJF 的排序也会错。
```

例如某个任务看起来很短，但实际执行很久，它就会变成新的队头阻塞。

因此真实系统里的 SJF 往往需要：

- 历史耗时统计。
- 任务类型估计。
- 超时控制。
- 动态调整。
- 保护机制。

第一轮我们不做这些复杂内容，但必须理解 SJF 的前提是假设耗时估计有一定参考价值。

> **SJF 给"识别取舍"贡献了两条独特的认识，都很值钱。**
>
> **第一条：优化目标决定了你牺牲谁——而且方向是"对称"的。** 对比着看就一目了然：Priority 优化"重要任务"，饿死的是"不重要的任务"；SJF 优化"平均等待"（让最多的任务尽早完成），饿死的是"长任务"。**同一套调度机制，你把优化目标从"重要性"换成"短"，被牺牲的群体就从"低优"变成"长任务"。** 这说明：被牺牲的是谁，不是偶然，而是你选的优化目标**直接决定**的。所以选策略前先问清楚：我最不能接受谁被拖垮？这决定了你该选什么、又必须给谁加保护。
>
> **第二条：依赖"预测"的策略，精度上限就是预测的精度。** SJF 有个前两章没有的脆弱点——它要"先知道任务多短"才能把短的提前。可现实里 `estimated_duration` 往往只是估计（尤其 AI workload：RAG/Agent 的耗时高度不确定）。**估计错了，SJF 的排序就错了**，一个被误判为"短"的长任务插到队头，反而造成它本想避免的阻塞。
>
> **可迁移的原则**：**任何依赖预测/估计来做决策的系统，它的效果上限就是预测的准确度；预测越不可靠，就越要给"估错了"准备兜底（超时、重估、保护机制）。** 这条会一路迁移：M08 你会发现"按预估耗时调度"必须配合真实耗时的历史统计；P03 给 RAG/Agent 任务估 `estimated_duration` 时，要永远假设它可能估错、并设超时。**一句话：别盲信你的预测，给它留出错的余地。**

## 5.12 手写 sort_by_sjf

本章代码任务很小，但理解要到位。

你先写：

```python
def sort_by_sjf(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (task.estimated_duration, task.submit_time, task.id))
```

然后继续使用第 4 章的通用调度器：

```python
sjf_result = run_single_worker_with_sorter(
    tasks,
    Worker(id="worker-sjf"),
    sort_by_sjf,
)
```

打印结果：

```python
for task in sjf_result:
    waiting_time = task.start_time - task.submit_time
    print(task.id, task.estimated_duration, task.start_time, task.finish_time, waiting_time)
```

你要观察：

```text
短任务是否提前？
长任务是否推迟？
平均等待是否降低？
```

## 5.13 同一组任务跑三种策略

现在把 FIFO、Priority、SJF 放在一起跑。

建议用这样的结构：

```python
strategies = {
    "fifo": sort_by_fifo,
    "priority": sort_by_priority,
    "sjf": sort_by_sjf,
}

for name, sorter in strategies.items():
    fresh_tasks = build_demo_tasks()  # Must return new objects on every iteration.
    # TODO: run the shared scheduler with this sorter.
    # TODO: calculate task-level waits without mutating another strategy's input.
    # TODO: record order and average wait in a structured result row.
    raise NotImplementedError(name)
```

这里用了 `build_demo_tasks()`，它的作用是每次重新构造任务，避免前一个策略修改任务状态后污染下一个策略。

你可以自己写一个简单版本：

```python
def build_demo_tasks() -> list[Task]:
    return [
        Task("task-001", "rag_query", 2, 5.0, 0.0, 1200),
        Task("task-002", "agent_tool", 1, 2.0, 1.0, 500),
        Task("task-003", "embedding", 3, 1.0, 2.0, 3000),
        Task("task-004", "long_context", 2, 8.0, 3.0, 8000),
    ]
```

注意：如果你的 `Task` 初始化参数顺序和这里不同，就用关键字参数写，避免错位。

## 5.14 和 P01 参考答案对照

SJF 参考代码位置：

```text
50_项目产出/P01_Mini_Scheduler/mini_scheduler/scheduler/strategies.py
```

关键实现：

```python
def sort_by_sjf(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (task.estimated_duration, task.submit_time, task.id))
```

demo 入口：

```text
50_项目产出/P01_Mini_Scheduler/mini_scheduler/examples/run_demo.py
```

实验记录：

```text
50_项目产出/P01_Mini_Scheduler/04_实验记录/FIFO_vs_Priority_vs_SJF.md
```

对照时看三个点：

第一，P01 是否用同一组任务跑三种策略。

第二，P01 是否用同一套指标比较结果。

第三，P01 的结论是否同时讲收益和风险，而不是只说 SJF 更好。

## 5.15 常见错误

第一个错误：全局按耗时排序。

SJF 只能从当前已经到达的任务里选，不能提前选未来短任务。

第二个错误：把 SJF 当成最优策略。

SJF 可能降低平均等待，但可能牺牲长任务。

第三个错误：忘记 estimated_duration 是估计值。

真实系统里估计可能错，SJF 的效果依赖估计质量。

第四个错误：和 FIFO / Priority 对比时换了任务集。

策略对比必须保持输入一致。

第五个错误：只看平均等待，不看长任务等待。

SJF 的副作用通常体现在长任务上。

## 5.16 本章你要做什么

本章任务分六步。

第一步，写 `sort_by_sjf`。

第二步，复用第 4 章的可切换调度器。

第三步，用同一组任务分别跑 FIFO、Priority、SJF。

第四步，输出每种策略的执行顺序和平均等待时间。

第五步，单独观察长任务 `task-004` 的等待时间。

第六步，写复盘：

```text
SJF 为什么能降低平均等待？
SJF 改善了哪些任务？
SJF 可能牺牲哪些任务？
estimated_duration 不准时会发生什么？
```

## 5.17 本章复盘问题

你可以用下面问题检查自己。

1. SJF 的目标是什么？
2. SJF 和 Priority 的优化目标有什么区别？
3. `sort_by_sjf` 为什么用 `(estimated_duration, submit_time, id)`？
4. 为什么 SJF 不能选择未来才到达的短任务？
5. 为什么 SJF 可能降低平均等待时间？
6. 为什么 SJF 可能牺牲长任务？
7. 真实 AI workload 里 `estimated_duration` 为什么不一定可靠？

## 5.18 本章检查标准

- 能手写 `sort_by_sjf`。
- 能说明 SJF 和 Priority 的优化目标不同。
- 能用同一组任务比较 FIFO / Priority / SJF。
- 能解释 SJF 为什么可能降低平均等待。
- 能说明 SJF 为什么可能牺牲长任务。
- 能说清 `estimated_duration` 不准确时 SJF 的风险。

如果这些问题能说清楚，就可以进入第 6 章：指标：average / P95 / P99 / utilization。

---
