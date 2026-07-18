# 第 3 章：FIFO baseline

## 3.1 本章目标

第 2 章已经把 `Task`、`Worker` 和 `Queue` 的最小模型讲清楚了。本章开始写第一个真正的调度策略：FIFO。

FIFO 的全称是 First In, First Out，也就是先到先服务。

学完本章，你要能做到：

- 解释为什么 FIFO 适合作为 baseline。
- 手写 `sort_by_fifo`。
- 写出单 worker 调度循环。
- 计算每个任务的 `start_time`、`finish_time`、`waiting_time`。
- 理解为什么调度循环需要处理“当前没有任务可执行”的情况。
- 对照 P01 的 `strategies.py` 和 `simulator.py`，看参考答案如何组织代码。

这一章很关键，因为后面的 Priority、SJF、Cost-aware 都不是从零开始，而是在 FIFO 的调度循环上替换“选择下一个任务”的规则。

## 3.2 为什么 FIFO 是第一个 baseline

学习调度时，一定要先有 baseline。

baseline 不是最强策略，而是最基础、最容易解释、最适合对比的策略。

FIFO 适合做 baseline，因为它有三个优点。

第一，它规则简单。

```text
谁先到，谁先执行。
```

第二，它容易验证。

只要任务按 `submit_time` 排列，执行顺序就应该稳定。如果两个任务同时到达，可以用 `id` 做稳定的次级排序。

第三，它能暴露后续策略到底改进了什么。

如果后面 SJF 平均等待时间更低，你要能说出它相对于 FIFO 改善在哪里。如果 Priority 的高优先级任务更快，你也要能说出它牺牲了谁。

没有 FIFO，后面的“更好”就没有参照物。

## 3.3 FIFO 的工程含义

FIFO 在真实工程里不是幼稚策略，它经常作为第一版队列规则。

例如：

- 普通任务队列按提交顺序处理。
- 日志处理任务按写入顺序消费。
- 离线批处理任务按进入队列的时间执行。
- 简单客服工单按创建时间处理。

FIFO 的价值是可解释性强。

如果用户问“为什么我的任务还没执行”，FIFO 的回答很直接：

```text
因为你前面还有更早提交的任务。
```

但 FIFO 也有明显缺点：它不关心任务长短，也不关心任务重要性。

如果队头是一个很长的任务，后面的短任务也要等。这就是经典的 convoy effect。

可以这样理解：

```text
一辆很慢的大车排在单车道最前面，后面所有车都会被拖慢。
```

在调度里，长任务就是那辆慢车。

## 3.4 FIFO 排序规则

FIFO 的核心排序键是 `submit_time`。

最小实现是：

```python
def sort_by_fifo(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: task.submit_time)
```

但实际项目里建议加上 `task.id`：

```python
def sort_by_fifo(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (task.submit_time, task.id))
```

为什么要加 `task.id`？

因为可能有多个任务的 `submit_time` 完全相同。如果只按 `submit_time` 排，Python 的排序虽然是稳定的，但你的输入顺序可能来自不同来源。加上 `id` 可以让结果更可预测，也更方便测试。

P01 参考答案里就是这样写的：

```python
def sort_by_fifo(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (task.submit_time, task.id))
```

注意，这里只是排序函数，还不是完整调度器。

完整调度器还要处理：

- 当前时间。
- worker 是否空闲。
- 哪些任务已经到达。
- 任务执行后如何更新状态。
- 指标如何计算。

## 3.5 先写一个最小 FIFO 排序练习

继续使用第 2 章的 4 个任务。

```python
fifo_order = sorted(tasks, key=lambda task: (task.submit_time, task.id))
print([task.id for task in fifo_order])
```

你应该得到：

```text
['task-001', 'task-002', 'task-003', 'task-004']
```

这一步只是确认 FIFO 顺序。

你现在要回答：

```text
FIFO 为什么是这个顺序？
如果 task-002 的 priority=1，它能不能插到 task-001 前面？
```

答案是：不能。

因为 FIFO 不看 priority，只看到达时间。

这就是策略的边界。一个策略看见什么字段，就会被什么字段影响；它看不见的字段，对它来说就不存在。

## 3.6 从排序进入调度循环

现在进入真正的调度。

调度循环要做的是：只要还有任务没完成，就不断选择一个任务执行。

最小逻辑如下：

```text
pending = 所有任务
completed = 空列表
current_time = worker.available_at

while pending 里还有任务：
    找出当前时间已经到达的任务 available_tasks
    如果 available_tasks 为空：
        把 current_time 推进到下一个任务的 submit_time
    按 FIFO 从 available_tasks 里选一个任务
    计算 start_time 和 finish_time
    更新任务状态
    更新 worker 状态
    把任务从 pending 移到 completed
```

这里最容易忽略的是：

```text
如果当前没有任务可执行，要推进 current_time。
```

为什么？

假设 worker 在时间 0 空闲，但第一个任务在时间 10 才到达。系统不能凭空执行任务，只能等到 10。

所以代码里要有这一步：

```python
if not available_tasks:
    current_time = min(task.submit_time for task in pending)
```

这不是细节，这是让调度器处理“空闲等待”的关键。

## 3.7 手写单 worker FIFO 调度器

现在写一个最小版本。

先准备函数：

```python
def sort_by_fifo(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (task.submit_time, task.id))
```

然后先写单 worker 调度函数的接口。完整循环留给 E05-01；教材只给出必须维护的状态：

```python
def run_fifo_single_worker(tasks: list[Task], worker: Worker) -> list[Task]:
    """Schedule each task once without running a task before submit_time."""
    raise NotImplementedError
```

实现时需要自己补齐下面的状态转换：

```text
维护 pending 和 completed
只从 available_tasks 选择 next_task
没有任务可运行时，把时间推进到下一次提交
写入 start/finish/status
更新 worker.available_at 和 busy time
从 pending 移除任务，保证每个任务只运行一次
```

## 3.8 逐行解释这个调度器

### pending = tasks[:]

这行创建任务列表的浅拷贝。

目的是避免直接修改原来的 `tasks` 列表。

第一轮学习时这样写够用。P01 参考答案里用的是 `replace(task)`，它会复制每个 dataclass 对象，避免运行时污染原始任务对象。这个差异后面会解释。

### current_time = worker.available_at

当前时间从 worker 的可用时间开始。

如果 worker 一开始就是空闲的，通常是 0.0。

如果 worker 前面已经执行过任务，可能不是 0.0。

### available_tasks

这一段过滤当前已经到达的任务：

```python
available_tasks = [
    task for task in pending
    if task.submit_time <= current_time
]
```

这一步把“未来任务”排除掉。

### if not available_tasks

如果当前没有任务可执行，就把时间推进到下一个任务到达：

```python
current_time = min(task.submit_time for task in pending)
```

这表示 worker 空等到下一次任务到来。

### `next_task = sort_by_fifo(available_tasks)[0]`

在当前可执行任务里，选择最早到达的任务。

注意，是在 `available_tasks` 里选，不是在全部 pending 里选。

### start_time 和 finish_time

```python
start_time = max(current_time, next_task.submit_time)
finish_time = start_time + next_task.estimated_duration
```

这里复用了第 2 章的时间公式。

任务开始必须同时满足：

- 任务已经到达。
- worker 已经可用。

### 更新任务状态

```python
next_task.start_time = start_time
next_task.finish_time = finish_time
next_task.status = "succeeded"
```

调度器执行完任务后，要把结果写回任务对象。

### 更新 worker 状态

```python
worker.available_at = finish_time
worker.total_busy_time += next_task.estimated_duration
current_time = finish_time
```

worker 执行完任务后，下次可用时间就是这次任务的完成时间。

`current_time` 也推进到完成时间。

### pending.remove(next_task)

任务完成后，从 pending 移除。

否则 while 循环会一直重复选择同一个任务。

## 3.9 跑一个小样例

使用第 2 章的 4 个任务，运行：

```python
worker = Worker(id="worker-1")
completed = run_fifo_single_worker(tasks, worker)

for task in completed:
    waiting_time = task.start_time - task.submit_time
    turnaround_time = task.finish_time - task.submit_time
    print(
        task.id,
        "start=", task.start_time,
        "finish=", task.finish_time,
        "wait=", waiting_time,
        "turnaround=", turnaround_time,
    )
```

你应该得到类似结果：

```text
task-001 start=0.0 finish=5.0 wait=0.0 turnaround=5.0
task-002 start=5.0 finish=7.0 wait=4.0 turnaround=6.0
task-003 start=7.0 finish=8.0 wait=5.0 turnaround=6.0
task-004 start=8.0 finish=16.0 wait=5.0 turnaround=13.0
```

先不要只看输出，要解释它。

task-001 最早到达，worker 也空闲，所以等待时间是 0。

task-002 在时间 1 到达，但 worker 要到时间 5 才空闲，所以等待 4。

task-003 在时间 2 到达，等到时间 7 才开始，所以等待 5。

task-004 在时间 3 到达，等到时间 8 才开始，所以等待 5。

这就是 FIFO 的基本行为。

## 3.10 FIFO 暴露出的第一个问题：长任务拖慢后续任务

现在改一个任务。

把 `task-001` 的耗时从 5.0 改成 20.0。

```python
tasks[0].estimated_duration = 20.0
```

重新运行 FIFO。

你会看到后面的任务等待时间都会变长。

这就是 FIFO 的核心弱点：队头长任务会拖慢后续任务。

工程上这意味着：

- 一个长上下文任务可能拖慢后面的短 RAG 请求。
- 一个大批量 embedding 任务可能阻塞后面的在线请求。
- 一个慢任务排在前面，后面所有任务都被动等待。

这也是为什么后面要学习 SJF 和 Priority。

但注意：FIFO 虽然慢，却不容易出现某一类任务长期被插队。它至少保证先来的任务先得到服务。

> **回到第 1 章那条核心原则——FIFO 是它的第一个例子。** 用那组"识别取舍"的问题套一下：
> - FIFO 优化**什么**？答：公平和可预测性。先来先得，谁都不会被插队，每个任务的等待时间只取决于"它前面排了谁"，这非常好解释、也让用户觉得公平。
> - 它**牺牲**什么？答：整体效率。一个队头长任务能拖垮它后面所有短任务（convoy effect，"车队效应"——一辆慢车堵住整条路）。
>
> 所以 FIFO 不是"最笨的策略",而是"把公平排在效率之前"的策略。**关键洞见是：公平本身就是一个有价值的优化目标,不是没本事才用 FIFO。** 在很多场景里,可预测、不被插队比"平均快几秒"更重要——比如计费任务、审计任务、或者你就是不希望任何用户被无限期推后。
>
> **可迁移的原则**：**当"可预测、不被插队"比"整体吞吐最优"更重要时，FIFO（先来先服务）就是对的选择——简单不等于差。** 这也是为什么 FIFO 几乎总是被选作 baseline：它行为最好懂，是衡量其他更复杂策略"到底换来了什么、又牺牲了什么"的那把尺子。你在 P03 给任务队列定默认策略、在 M08 设压测基准时，都会先用它打底。

## 3.11 计算平均等待时间

现在写一个最小平均等待时间函数：

```python
def calculate_wait_time(task: Task) -> float:
    if task.start_time is None:
        raise ValueError(f"{task.id} has not started")
    return task.start_time - task.submit_time


def average(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
```

然后计算：

```python
wait_times = [calculate_wait_time(task) for task in completed]
print("average_wait=", average(wait_times))
print("max_wait=", max(wait_times))
```

在原始 4 个任务里，等待时间是：

```text
0.0, 4.0, 5.0, 5.0
```

平均等待时间：

```text
(0 + 4 + 5 + 5) / 4 = 3.5
```

这和 P01 demo 里的 FIFO 平均等待时间一致。

## 3.12 什么时候需要 P95/P99

4 个任务太少时，P95/P99 的意义不明显。

但你还是要先理解：平均等待时间只能代表总体平均，不能代表尾部体验。

如果任务很多，可能出现这种情况：

```text
90 个任务等待 1 秒
10 个任务等待 100 秒
```

平均值会被拉高，但还不够直观。P95/P99 能更直接暴露尾部等待。

所以本章先看 average 和 max wait。到第 6 章会系统讲 P95/P99。

## 3.13 和 P01 参考答案对照

完成手写版本后，再看 P01 参考答案。

FIFO 策略在：

```text
50_项目产出/P01_Mini_Scheduler/mini_scheduler/scheduler/strategies.py
```

关键代码：

```python
def sort_by_fifo(tasks: list[Task]) -> list[Task]:
    """Order by submit_time and use id only as a deterministic tie-breaker."""
    raise NotImplementedError
```

单 worker 调度循环在：

```text
50_项目产出/P01_Mini_Scheduler/mini_scheduler/scheduler/simulator.py
```

你会看到 P01 参考答案比本章手写版本多了几处工程化处理。

第一，它用 `replace(task)` 复制任务对象：

```python
pending = [replace(task) for task in tasks]
```

这是为了避免调度运行时修改原始输入任务。实验经常要让同一组任务分别跑 FIFO、Priority、SJF，如果第一个策略把原始任务状态改掉了，后面的策略就不干净了。

第二，它把选择下一个任务抽成了 `_choose_next_task`：

```python
next_task = _choose_next_task(available_tasks, strategy_name)
```

这样后面切换 Priority、SJF 时，不用重写整个调度循环。

第三，它保留了 `selector` 参数：

```python
selector: Optional[TaskSelector] = None
```

这是给后面的 aging / cost-aware 动态选择留扩展口。

第一轮你不需要全部照写，但要理解这些设计为什么存在。

## 3.14 本章对应实验 E05-01

本章对应实验：

```text
40_实验练习/E05_调度实验/E05-01 实现 FIFO 调度.md
```

你可以把 E05-01 当作本章练习页。

建议完成顺序是：

1. 先按本章手写 `Task` / `Worker` / `sort_by_fifo` / `run_fifo_single_worker`。
2. 用 4 个任务跑出顺序和等待时间。
3. 再读 E05-01，补齐实验记录。
4. 最后对照 P01 的 `strategies.py` 和 `simulator.py`。

不要一开始就跑 P01 的完整 demo。先写自己的最小版本，才知道参考答案在帮你处理什么。

## 3.15 常见错误

第一个错误：把 FIFO 写成按 `id` 排序。

FIFO 看的是到达时间，不是任务编号。`id` 只能作为同一到达时间下的次级排序。

第二个错误：在全部 pending 里直接选最早任务。

你必须先过滤 `available_tasks`。否则可能会选择未来才到达的任务。

第三个错误：忘记推进 `current_time`。

如果当前没有可执行任务，系统应该等到下一个任务到达。

第四个错误：忘记从 pending 移除已完成任务。

这会导致死循环。

第五个错误：直接修改原始任务对象后，又用同一组任务跑另一个策略。

这会污染实验。P01 用 `replace(task)` 就是为了避免这个问题。

## 3.16 本章你要做什么

本章任务分五步。

第一步，写 `sort_by_fifo`：

```python
def sort_by_fifo(tasks: list[Task]) -> list[Task]:
    return sorted(tasks, key=lambda task: (task.submit_time, task.id))
```

第二步，写 `run_fifo_single_worker`。

第三步，用第 2 章的 4 个任务运行，打印：

```text
id
start_time
finish_time
waiting_time
turnaround_time
```

第四步，把 `task-001` 改成长任务，再观察后续任务等待时间如何变化。

第五步，写一段复盘：

```text
我观察到 FIFO 改善了：
我观察到 FIFO 牺牲了：
排序函数之外，调度循环还必须维护：
这个结论依赖的 workload 条件是：
```

## 3.17 本章复盘问题

你可以用下面问题检查自己。

1. 为什么 FIFO 是 baseline？
2. `sort_by_fifo` 为什么用 `(submit_time, id)`？
3. 为什么不能直接从全部 pending 里选择任务？
4. `current_time` 在什么情况下需要跳到下一个 `submit_time`？
5. 为什么 `start_time = max(current_time, submit_time)`？
6. 为什么 P01 要复制任务对象，而不是直接修改输入任务？
7. FIFO 的主要优点和主要缺点分别是什么？

## 3.18 本章检查标准

- 能手写 `sort_by_fifo`。
- 能写出单 worker FIFO 调度循环。
- 能解释 `current_time`、`available_tasks`、`worker.available_at` 的作用。
- 能输出每个任务的 start、finish、waiting、turnaround。
- 能说明 FIFO 为什么适合作为 baseline。
- 能解释长任务为什么会拖慢后续任务。

如果这些都能说清楚，你就可以进入第 4 章：Priority 和业务优先级。

---
