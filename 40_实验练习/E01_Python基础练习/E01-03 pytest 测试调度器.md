# E01-03 pytest 测试调度器

## 实验定位

调度器最容易出错的地方，不一定是语法，而是规则。比如 priority 方向写反、SJF 没有按耗时排序、相同优先级时顺序不稳定。pytest 的作用就是把这些规则固定下来。

这个实验的目标是：用测试证明你的调度策略符合预期。

## 前置阅读

建议先读：

- [[10_学习模块/M00_工具链与计算机基础/M00_工具链与计算机基础_适配教材]] 第 6 章：pytest 和最小质量保障
- [[10_学习模块/M01_Python工程能力/M01_Python工程能力_适配教材]] 第 9 章：pytest 在 M01 中要学到什么程度
- [[50_项目产出/P01_Mini_Scheduler/03_代码结构与接口]]

## 实验目标

至少写 5 个测试：

- FIFO 顺序
- Priority 顺序
- SJF 顺序
- 空任务列表
- 相同 priority 时按提交时间排序

## 推荐测试文件

```text
mini_scheduler/
└─ tests/
   └─ test_strategies.py
```

## 测试数据

建议在测试文件里写一个小的 helper。

> 环境要求：本实验以 Python 3.13 验收。使用虚拟环境中的 `python -m pytest`，不要直接调用可能属于其他解释器的 `pytest` 命令。

```python
from scheduler.models import Task


def build_tasks() -> list[Task]:
    return [
        Task("task-001", "rag_query", priority=2, estimated_duration=5.0, submit_time=0.0),
        Task("task-002", "agent_tool", priority=1, estimated_duration=2.0, submit_time=1.0),
        Task("task-003", "embedding", priority=3, estimated_duration=1.0, submit_time=2.0),
    ]
```

## 第 1 个测试：FIFO

```python
from scheduler.strategies import sort_by_fifo


def test_sort_by_fifo_orders_by_submit_time():
    sorted_tasks = sort_by_fifo(build_tasks())

    assert [task.id for task in sorted_tasks] == ["task-001", "task-002", "task-003"]
```

这个测试固定了 FIFO 的业务含义：谁先提交，谁先执行。

## 第 2 个测试：Priority

```python
from scheduler.strategies import sort_by_priority


def test_sort_by_priority_orders_by_smaller_number_first():
    sorted_tasks = sort_by_priority(build_tasks())

    assert [task.id for task in sorted_tasks] == ["task-002", "task-001", "task-003"]
```

这个测试固定了 priority 的方向：数字越小越优先。

## 第 3 个测试：SJF

```python
from scheduler.strategies import sort_by_sjf


def test_sort_by_sjf_orders_by_shorter_duration_first():
    sorted_tasks = sort_by_sjf(build_tasks())

    assert [task.id for task in sorted_tasks] == ["task-003", "task-002", "task-001"]
```

这个测试固定了 SJF 的业务含义：预计耗时短的任务先执行。

## 第 4 个测试：空任务列表

```python
def test_sort_empty_task_list():
    assert sort_by_fifo([]) == []
    assert sort_by_priority([]) == []
    assert sort_by_sjf([]) == []
```

空列表是非常重要的边界情况。真实服务里没有任务时，调度器不能崩。

## 第 5 个测试：相同 priority 的 tie-breaker

```python
def test_sort_by_priority_uses_submit_time_as_tie_breaker():
    tasks = [
        Task("late", "rag_query", priority=1, estimated_duration=1.0, submit_time=10.0),
        Task("early", "rag_query", priority=1, estimated_duration=1.0, submit_time=1.0),
    ]

    sorted_tasks = sort_by_priority(tasks)

    assert [task.id for task in sorted_tasks] == ["early", "late"]
```

这个测试避免同优先级任务顺序变得不可解释。

## 故意制造一次失败

为了真正理解 pytest，建议你故意把 priority 排序写反：

```python
return sorted(tasks, key=lambda task: task.priority, reverse=True)
```

然后运行：

```bash
pytest
```

观察失败输出。你要能看懂：

- 哪个测试失败
- 实际输出是什么
- 期望输出是什么
- 错误来自策略函数还是测试本身

## 验收标准

- [ ] 至少 5 个测试通过
- [ ] 故意改错时测试会失败
- [ ] 能解释每个测试对应的业务规则
- [ ] 测试文件不依赖 print 输出
- [ ] 测试数据足够小，可以手算验证

## 常见错误

### 只测试正常情况

只测试一个顺序是不够的。至少要测空列表、相同 priority 这样的边界情况。

### 测试 print 输出

不要通过看终端输出判断对错。测试应该直接断言函数返回值。

### 测试和实现写在同一个文件

测试应该在 `tests/` 目录，业务代码应该在 `scheduler/` 目录。

### 测试数据太复杂

测试数据越小越好。一个测试最好只验证一条规则。

## 和 P01 的关系

这个实验是 P01 的质量保障起点。后面做指标、FastAPI、RAG 接入、压测时，都需要用测试保护核心规则。

## 记录

### 测试列表


### 失败案例


### 修复过程


### 结论


## 关联

- [[50_项目产出/P01_Mini_Scheduler/08_阶段执行说明_v0.1]]
- [[50_项目产出/P01_Mini_Scheduler/P01_Mini_Scheduler 项目主页]]
- [[40_实验练习/E05_调度实验/E05-01 实现 FIFO 调度]]
