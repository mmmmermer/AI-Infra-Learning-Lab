# E01-02 Python 类实现 Task 和 Worker

## 实验定位

E01-01 用 dict 表示任务，适合快速验证排序规则。但 P01 要继续发展成小型工程时，任务和 worker 的字段会越来越多。继续用 dict 容易出现拼写错误、字段含义不清、函数参数混乱等问题。

这个实验的目标是把任务和 worker 从“临时字典”升级成“工程模型”。

## 前置阅读

建议先读：

- [[10_学习模块/M01_Python工程能力/M01_Python工程能力_适配教材]] 第 2 章：从业务需求到数据模型
- [[10_学习模块/M01_Python工程能力/M01_Python工程能力_适配教材]] 第 4 章：类型标注
- [[10_学习模块/M01_Python工程能力/M01_Python工程能力_适配教材]] 第 8 章：面向对象不是为了复杂，而是为了表达关系
- [[50_项目产出/P01_Mini_Scheduler/03_代码结构与接口]]

## 实验目标

用 `dataclass` 定义：

- `Task`
- `Worker`

并完成一个最小任务执行过程。

## 为什么不用普通 class 起步

普通 class 当然可以，但当前阶段 `dataclass` 更适合你：

- 写法短
- 字段清楚
- 自动生成初始化方法
- 适合表达数据模型
- 和后续 Pydantic / API schema 的思路接近

## 推荐代码位置

```text
mini_scheduler/
└─ scheduler/
   ├─ __init__.py
   └─ models.py
```

## 第 1 步：定义 Task

> 环境要求：本实验以 Python 3.13 验收。旧代码中的 `from __future__ import annotations` 可以保留，但不得用它绕过错误解释器。

```python
from dataclasses import dataclass


@dataclass
class Task:
    id: str
    task_type: str
    priority: int
    estimated_duration: float
    submit_time: float
    start_time: float | None = None
    finish_time: float | None = None
    status: str = "pending"
```

字段解释：

| 字段 | 为什么需要 |
|---|---|
| `id` | 识别任务 |
| `task_type` | 区分 RAG、embedding、agent tool 等任务 |
| `priority` | 支持优先级调度 |
| `estimated_duration` | 支持 SJF 和成本估计 |
| `submit_time` | 支持 FIFO 和等待时间计算 |
| `start_time` | 用来计算等待时间 |
| `finish_time` | 用来计算完成时间 |
| `status` | 表示任务生命周期 |

## 第 2 步：定义 Worker

```python
@dataclass
class Worker:
    id: str
    available_at: float = 0.0
    current_task_id: str | None = None
    total_busy_time: float = 0.0
```

字段解释：

| 字段 | 为什么需要 |
|---|---|
| `id` | 识别 worker |
| `available_at` | 判断 worker 什么时候空闲 |
| `current_task_id` | 观察当前执行任务 |
| `total_busy_time` | 计算 worker 利用率 |

## 第 3 步：创建对象

```python
task = Task(
    id="task-001",
    task_type="rag_query",
    priority=1,
    estimated_duration=3.0,
    submit_time=0.0,
)

worker = Worker(id="worker-1")
```

你可以打印对象，观察 dataclass 的默认展示：

```python
print(task)
print(worker)
```

## 第 4 步：模拟 worker 执行 task

先写一个最小函数，不要急着写复杂调度器。

```python
def run_task(task: Task, worker: Worker) -> Task:
    start_time = max(worker.available_at, task.submit_time)
    finish_time = start_time + task.estimated_duration

    task.start_time = start_time
    task.finish_time = finish_time
    task.status = "succeeded"

    worker.available_at = finish_time
    worker.total_busy_time += task.estimated_duration
    worker.current_task_id = None

    return task
```

这里最重要的是时间线：

```text
submit_time ---- wait ---- start_time ---- run ---- finish_time
```

等待时间：`start_time - submit_time`

完成时间：`finish_time - submit_time`

## 第 5 步：解释状态变化

任务状态可以先用字符串：

- `pending`：等待执行
- `running`：执行中
- `succeeded`：成功完成
- `failed`：失败

当前实验只需要 `pending -> succeeded`，但你要理解后续服务化时为什么需要状态。因为 API 里经常会出现：任务已经提交，但还没有完成。

## 验收标准

- [ ] 能定义 `Task`
- [ ] 能定义 `Worker`
- [ ] 能创建 2-3 个 Task 对象
- [ ] 能创建 1 个 Worker 对象
- [ ] 能模拟 worker 执行 task
- [ ] 能解释 `available_at`
- [ ] 能解释 `start_time` 和 `finish_time`
- [ ] 能说明 `pending -> succeeded` 和后续 P03 任务状态的关系

## 常见错误

### 把所有字段都写成字符串

`priority`、`estimated_duration`、`submit_time` 这些应该是数字。否则排序和指标计算会出问题。

### 类里放太多方法

当前阶段先让 `Task` 和 `Worker` 主要表达数据。调度策略和指标计算放到单独函数里更清楚。

### 忘记更新 worker 的 `available_at`

如果 worker 执行完任务后没有更新 `available_at`，后续任务会错误地从旧时间开始执行。

## 和 P01 的关系

这个实验是 P01 从脚本走向工程项目的关键一步。后续 FIFO/Priority/SJF 都会操作 `Task` 对象，模拟器会操作 `Worker` 对象。

## 记录

| 项目 | 记录 |
|---|---|
| `Task` 字段 |  |
| `Worker` 字段 |  |
| 输入任务数量 |  |
| worker 初始 `available_at` |  |
| 第一个任务 `start_time` / `finish_time` |  |
| 最终任务状态 |  |
| 手算等待时间 |  |
| 代码输出是否和手算一致 |  |
| 遇到的问题 |  |
| 结论 |  |

记录时要特别写清：状态为什么用 `succeeded`，而不是随手写 `done`。这是为了和后续 API、数据库和 P03 任务契约保持一致。


## 关联

- [[50_项目产出/P01_Mini_Scheduler/08_阶段执行说明_v0.1]]
- [[50_项目产出/P01_Mini_Scheduler/00_项目目标与范围]]
- [[50_项目产出/P01_Mini_Scheduler/03_代码结构与接口]]
