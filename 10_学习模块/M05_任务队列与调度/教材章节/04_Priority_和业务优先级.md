# 第 4 章：Priority 和业务优先级

## 4.1 本章目标

第 3 章里，你已经写出了 FIFO baseline。FIFO 的规则很简单：谁先到，谁先执行。

但真实系统里，任务并不总是完全平等。

在线请求可能比离线批处理更急。

人工触发任务可能比后台清洗任务更重要。

付费用户请求可能有更高服务等级。

这就是 Priority 调度要解决的问题。

学完本章，你要能做到：

- 解释 Priority 调度为什么存在。
- 统一 `priority=1` 最高、数字越大优先级越低的口径。
- 手写 `sort_by_priority`。
- 复用第 3 章的单 worker 调度循环，不重新造一套调度器。
- 用同一组任务比较 FIFO 和 Priority。
- 说明 Priority 改善了谁、牺牲了谁。
- 理解为什么 Priority 后续需要 aging 或最大等待保护。

这一章的重点不是“Priority 一定更好”，而是学会识别它的收益和代价。

## 4.2 为什么需要业务优先级

FIFO 只尊重到达顺序。

这很公平，但不一定符合业务目标。

假设当前队列里有两个任务：

| 任务 | 类型 | submit_time | estimated_duration | priority |
|---|---|---:|---:|---:|
| task-A | 离线 embedding 批处理 | 0.0 | 20.0 | 3 |
| task-B | 在线 RAG 查询 | 1.0 | 2.0 | 1 |

如果用 FIFO，task-A 先到，所以先执行。task-B 虽然是在线请求，也只能等 task-A 跑完。

这在业务上可能不合理。

用户正在等待 RAG 查询结果，而 embedding 批处理可以晚一点做。此时系统应该有办法表达：

```text
task-B 比 task-A 更重要。
```

Priority 就是把这种业务重要性放进调度决策里。

## 4.3 Priority 不是“更聪明的 FIFO”，而是另一种取舍

Priority 的规则是：

```text
在当前已经到达的任务里，优先级高的任务先执行。
```

这句话里有两个重点。

第一，只能从当前已经到达的任务里选。

Priority 不应该让 worker 为了等待未来可能出现的高优先级任务而空转。比如当前时间是 0，只有一个低优先级任务已经到达，高优先级任务要到时间 10 才到。当前 worker 不应该空等到 10，而应该先处理已经到达的任务。

第二，Priority 会改变等待时间分配。

高优先级任务可能更快，但低优先级任务可能更慢。Priority 不是免费优化，它是在重新分配等待时间。

这就是本章最重要的结论：

```text
Priority 优化的是业务重要任务的响应，不一定优化所有任务的平均体验。
```

## 4.4 优先级口径必须统一

当前 P01 统一约定：

```text
priority=1 表示最高优先级。
priority=2 表示普通优先级。
priority=3 表示低优先级。
数字越大，优先级越低。
```

这个约定很重要。

如果一个文件里写“数字越小越重要”，另一个文件里写“数字越大越重要”，实验结果就会完全混乱。

所以本模块所有章节都按这个口径：

```text
越小越急。
```

对应 Python 排序键就是：

```python
(task.priority, task.submit_time, task.id)
```

因为 Python 默认升序排序，数字小的会排前面。

## 4.5 Priority 排序规则

最小实现如下：

```python
def sort_by_priority(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (task.priority, task.submit_time, task.id))
```

这个排序键有三层。

第一层：`task.priority`

优先级数字越小，越早执行。

第二层：`task.submit_time`

如果两个任务优先级一样，就先到先执行。

第三层：`task.id`

如果优先级和到达时间都一样，用 id 保证顺序稳定，方便测试。

P01 参考答案也是这样写的：

```python
def sort_by_priority(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (task.priority, task.submit_time, task.id))
```

## 4.6 不要重写调度循环，只替换选择规则

这是本章最重要的工程思想。

第 3 章已经写过单 worker 调度循环。那个循环负责：

- 维护 pending。
- 过滤 available_tasks。
- 推进 current_time。
- 更新任务 start_time / finish_time。
- 更新 worker.available_at。
- 把任务移到 completed。

这些逻辑和 FIFO、Priority、SJF 都有关，但它们不应该重复写三遍。

策略真正不同的地方只有一处：

```text
从 available_tasks 里选谁。
```

FIFO 选择：

```python
next_task = sort_by_fifo(available_tasks)[0]
```

Priority 选择：

```python
next_task = sort_by_priority(available_tasks)[0]
```

其他时间推进逻辑完全一样。

这就是为什么 P01 里会有 `STRATEGY_SORTERS`：

```python
STRATEGY_SORTERS = {
    "fifo": sort_by_fifo,
    "priority": sort_by_priority,
    "sjf": sort_by_sjf,
    "cost_aware": sort_by_cost_aware,
}
```

它把“策略选择”从“调度流程”里拆出来。

这一步非常工程化：流程复用，策略替换。

## 4.7 手写一个可切换策略的调度器

在第 3 章里，你可能写的是：

```python
next_task = sort_by_fifo(available_tasks)[0]
```

现在把接口改成可传入 sorter。完整循环仍由学习者在 E05-02 中从 FIFO 版本重构：

```python
def run_single_worker_with_sorter(
    tasks: list[Task],
    worker: Worker,
    sorter,
) -> list[Task]:
    """Reuse one scheduling loop while delegating only candidate ordering."""
    raise NotImplementedError
```

重构边界只有一个：`sorter` 决定已经到达的候选顺序；时间推进、任务状态和 worker 状态
仍由调度循环负责。不要让 sorter 读取未来任务或修改执行时间。

现在你可以这样运行 FIFO：

```python
fifo_result = run_single_worker_with_sorter(
    tasks,
    Worker(id="worker-fifo"),
    sort_by_fifo,
)
```

也可以这样运行 Priority：

```python
priority_result = run_single_worker_with_sorter(
    tasks,
    Worker(id="worker-priority"),
    sort_by_priority,
)
```

注意：这里为了简单用了 `tasks[:]`，但如果你连续跑 FIFO 和 Priority，任务对象会被修改。更稳的做法是复制每个任务对象。P01 使用 `replace(task)` 就是为了解决这个问题。

第一轮练习时，你可以先重新构造一遍 tasks，或者下一步学习 `replace(task)`。

## 4.8 用第 2 章任务比较 FIFO 和 Priority

继续使用这组任务：

| id | task_type | priority | estimated_duration | submit_time |
|---|---|---:|---:|---:|
| task-001 | rag_query | 2 | 5.0 | 0.0 |
| task-002 | agent_tool | 1 | 2.0 | 1.0 |
| task-003 | embedding | 3 | 1.0 | 2.0 |
| task-004 | long_context | 2 | 8.0 | 3.0 |

FIFO 顺序会是：

```text
task-001 -> task-002 -> task-003 -> task-004
```

Priority 顺序在单 worker 动态调度中会是：

```text
task-001 -> task-002 -> task-004 -> task-003
```

为什么不是 `task-002` 第一个？

因为当前时间 0 时，只有 `task-001` 到达。`task-002` 虽然优先级最高，但它时间 1 才到达，不能在时间 0 被提前执行。

这点非常重要：Priority 不是预知未来。

为什么 `task-004` 会排在 `task-003` 前面？

因为当 `task-001` 和 `task-002` 执行完以后，`task-003` 和 `task-004` 都已经到达。此时 Priority 会比较优先级：

```text
task-004 priority=2
task-003 priority=3
```

数字越小越重要，所以 `task-004` 先执行。

这就造成了一个副作用：`task-003` 虽然很短，但因为优先级低，被推迟到最后。

## 4.9 指标如何变化

P01 的小样例结果里，FIFO 和 Priority 的指标是：

| 策略 | 平均等待时间 | 平均周转时间 | P95 | P99 | worker 利用率 |
|---|---:|---:|---:|---:|---:|
| FIFO | 3.50 | 7.50 | 5.00 | 5.00 | 1.00 |
| Priority | 5.25 | 9.25 | 13.00 | 13.00 | 1.00 |

这组结果很有教学价值。

Priority 不是变好了，而是变差了。

为什么？

因为这个任务集里，低优先级的 `task-003` 虽然很短，但被 `task-004` 这个更长的普通优先级任务推迟了。它等待到最后，拉高了尾部等待。

这说明一件很重要的事：

```text
Priority 会保护高优先级任务，但可能伤害低优先级短任务。
```

所以不能只说“Priority 更高级”。你必须看它改善了谁，又牺牲了谁。

## 4.10 单独观察任务级结果

比较策略时，不要只看总表。

你还应该打印每个任务的结果：

```python
for task in priority_result:
    waiting_time = task.start_time - task.submit_time
    print(task.id, task.priority, task.start_time, task.finish_time, waiting_time)
```

你要重点观察：

- 高优先级任务 `task-002` 是否更快。
- 低优先级任务 `task-003` 是否被推迟。
- 长任务 `task-004` 是否压过了短任务。

如果只看平均值，你会知道结果变差了，但不知道是谁变差。

真正的实验分析要能回答：

```text
变差的是哪类任务？
为什么是它？
这个代价是否可以接受？
```

## 4.11 Priority 适合什么场景

Priority 适合这些场景：

- 在线请求必须优先于离线任务。
- 高价值用户请求需要更低延迟。
- 关键业务任务不能排在普通任务后面太久。
- 系统希望把资源优先给更重要的 workload。

例如在 AI 平台里：

```text
priority=1：在线 RAG / Agent 请求
priority=2：普通交互任务
priority=3：离线 embedding / batch eval
```

这样做的好处是业务目标更清楚。

但这也意味着离线任务可能更慢。

所以 Priority 的正确使用方式不是“永远让高优先级先走”，而是：

```text
高优先级优先，但低优先级也要有最大等待保护。
```

这个保护机制就是后面第 10 章要讲的 aging / max wait。

## 4.12 Priority 的常见副作用

### 低优先级饥饿

如果高优先级任务不断到来，低优先级任务可能一直等不到执行机会。

这叫 starvation。

### 短任务被牺牲

如果一个短任务优先级低，而一个长任务优先级更高，Priority 会先执行长任务。

这会拉高短任务等待时间。

### 平均值未必更好

Priority 的目标不是降低平均等待时间，而是保护重要任务。

所以平均等待时间变差并不一定说明 Priority 没价值。关键要看它是否符合业务目标。

### 尾部延迟可能恶化

低优先级任务被不断推迟时，P95/P99 会变差。

这就是为什么 Priority 实验一定要看尾部指标和分组结果。

> **Priority 给"识别取舍"加了一个关键的新认识：贪心地优化局部，会伤害全局。** 它优化的是"重要任务的体验"——每次都把最重要的挑出来先做，这在单步看永远是"最优选择"。但把这些局部最优叠起来，整体（平均等待、尾部延迟）反而可能比 FIFO 更差，而且低优先级任务会被**饿死**（starvation）。
>
> 为什么会这样？因为 Priority **只看任务的重要性，完全不看它已经等了多久**。一个低优任务等了 10 分钟，在 Priority 眼里和刚到的低优任务没区别——只要还有高优任务在，它就永远轮不上。这就是"贪心策略"的通病：每一步都对，合起来却失控。
>
> **可迁移的原则**：**纯粹按"重要性"贪心调度会导致低优先级饥饿；任何 Priority 系统都必须配一个"等待越久、越该被照顾"的兜底机制。** 这个兜底就是第 10 章的 aging——它给等待时间也算进分数，让被推迟太久的任务自动"涨价"。你在 M04 给 Agent 任务设优先级、在 P03 做多租户调度时，只要用了优先级，就必须同时想"低优的怎么不被饿死"。**记住这对组合：Priority 负责"重要的先走"，aging 负责"等久的别饿死",两者缺一不可。**

## 4.13 和 FIFO 对比时要保持口径一致

比较 FIFO 和 Priority 时，必须保持这些东西不变：

- 同一组任务。
- 同一组 `submit_time`。
- 同一组 `estimated_duration`。
- 同一个 worker 数量。
- 同一套等待时间计算方式。
- 同一套 P95/P99 计算方式。

唯一变化应该是：

```text
选择下一个任务的策略。
```

如果任务集变了，worker 数量也变了，那你就无法判断差异到底来自 Priority，还是来自输入变化。

这就是实验口径。

## 4.14 本章对应实验 E05-02

本章对应实验：

```text
40_实验练习/E05_调度实验/E05-02 比较 FIFO 和 Priority.md
```

建议学习顺序：

1. 先按本章写 `sort_by_priority`。
2. 把第 3 章的调度器改成可传入 sorter。
3. 用同一组任务分别跑 FIFO 和 Priority。
4. 输出总指标。
5. 输出每个任务的等待时间。
6. 写出“改善了谁，牺牲了谁”的结论。
7. 再对照 P01 的 `strategies.py` 和实验记录。

## 4.15 和 P01 参考答案对照

Priority 参考代码位置：

```text
50_项目产出/P01_Mini_Scheduler/mini_scheduler/scheduler/strategies.py
```

关键实现：

```python
def sort_by_priority(tasks: list[Task]) -> list[Task]:
    """Use priority first, then stable arrival and id tie-breakers."""
    raise NotImplementedError
```

调度循环仍然在：

```text
50_项目产出/P01_Mini_Scheduler/mini_scheduler/scheduler/simulator.py
```

你要看的是：P01 没有为 Priority 复制一份完整调度循环，而是通过策略表切换排序函数。

这说明它已经把“调度流程”和“策略规则”拆开了。

这是你后续写 SJF、Cost-aware 时要延续的设计。

## 4.16 常见错误

第一个错误：优先级方向搞反。

当前口径是 `priority=1` 最高。不要写成数字越大越重要。

第二个错误：为了等待未来高优先级任务，让 worker 空转。

当前模型只从已经到达的任务里选。未来任务不能被提前执行，也不应该让 worker 空等它。

第三个错误：只看平均等待时间。

Priority 的重点是改善高优先级任务，而不是必然改善平均值。你要看分组和任务级结果。

第四个错误：没保留 FIFO baseline。

如果没有 FIFO 对比，你就不知道 Priority 到底改了什么。

第五个错误：把 Priority 当成最终方案。

Priority 只是第一步。后面还需要 aging、quota、最大等待保护等机制来缓解低优先级任务长期等待。

## 4.17 本章你要做什么

本章任务分六步。

第一步，写：

```python
def sort_by_priority(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (task.priority, task.submit_time, task.id))
```

第二步，把调度器改成可传入 sorter。

第三步，用同一组任务跑 FIFO 和 Priority。

第四步，输出任务级结果：

```text
id
priority
start_time
finish_time
waiting_time
```

第五步，输出总指标：

```text
average_wait
max_wait
```

第六步，写复盘：

```text
Priority 在这组任务中改善了谁？
Priority 牺牲了谁？
这个结果是否符合业务目标？
如果低优先级任务被长期推迟，后续应该用什么机制保护？
```

## 4.18 本章复盘问题

你可以用下面问题检查自己。

1. Priority 和 FIFO 的区别是什么？
2. 为什么当前约定 `priority=1` 最高？
3. `sort_by_priority` 为什么用 `(priority, submit_time, id)`？
4. 为什么 Priority 不能选择未来才到达的任务？
5. 为什么 Priority 可能让平均等待时间变差？
6. 怎样判断 Priority 改善了谁、牺牲了谁？
7. 为什么后续需要 aging / 最大等待保护？

## 4.19 本章检查标准

- 能手写 `sort_by_priority`。
- 能保持 `priority=1` 最高、数字越大优先级越低的统一口径。
- 能复用同一个调度循环，只替换任务选择规则。
- 能用同一组任务比较 FIFO 和 Priority。
- 能解释 Priority 改善了哪些任务、牺牲了哪些任务。
- 能说明 Priority 为什么需要 aging / 最大等待保护等后续机制配合。

如果这些问题能说清楚，就可以进入第 5 章：SJF 和平均等待时间。

---
