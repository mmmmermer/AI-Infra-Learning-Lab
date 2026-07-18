# E05-01 实现 FIFO 调度

## 实验定位

这是 M05 的第一张实操实验。目标不是“写出一个排序函数”，而是先做出调度系统最重要的 baseline：FIFO。

它要回答的问题是：

```text
如果任务只按到达顺序执行，等待时间、完成时间和尾延迟会是什么样？
```

## 前置阅读
- [[10_学习模块/M05_任务队列与调度/教材章节/03_FIFO_baseline|M05 章节教材第 3 章：FIFO baseline]]
- [[10_学习模块/M05_任务队列与调度/M05_任务队列与调度_复现推进表|M05 复现推进表]]
- [[10_学习模块/M05_任务队列与调度/M05_任务队列与调度_学习地图|M05 任务队列与调度学习地图]]
- Python `deque` 基础
- 任务到达时间、等待时间、完成时间的定义

## baseline

- FIFO

## 实验目标

- 实现最小 FIFO 调度器。
- 记录每个任务的等待时间和完成时间。
- 用 pytest 验证 FIFO 顺序正确。
- 为后续 Priority / SJF 提供统一 baseline。

## 输入模型
建议先用最小字段，并和 P01 代码保持一致：

| 字段 | 含义 |
|---|---|
| `id` | 任务编号 |
| `submit_time` | 到达系统的时间 |
| `estimated_duration` | 预计执行时间 |
| `priority` | 先留着，后续实验要用；当前约定 `1` 最高 |
| `status` | `pending` / `queued` / `running` / `succeeded` / `failed` |

## 推荐实现方式
先写接口和不变量，不从 P01 复制排序键：

```python
def sort_by_fifo(tasks: list[Task]) -> list[Task]:
    """Return a deterministic FIFO order without mutating tasks."""
    raise NotImplementedError

def run_fifo_single_worker(tasks: list[Task], worker: Worker) -> list[TaskResult]:
    """Run each arrived task once and record start/finish times."""
    raise NotImplementedError
```

实现必须满足：先到先服务、同到达时间有稳定 tie-breaker、未来任务不会提前运行、输入对象
不会被另一轮实验污染。可以使用 `deque`，但需要解释排序发生在入队前还是每轮候选选择时。

## 实验步骤
1. 定义 `Task` 和 `Worker` 的最小结构。
2. 准备 5-10 个到达时间不同的任务。
3. 按 `submit_time` 将任务放入队列。
4. 用 FIFO 逐个出队并分配给 worker。
5. 计算每个任务的等待时间：`start_time - submit_time`。
6. 计算周转时间：`finish_time - submit_time`。
7. 汇总平均等待时间、最大等待时间、P95 等待时间。
8. 写至少 1 个 pytest，确认 FIFO 顺序没有错。

当前 P01 已经有最小代码入口：

```bash
cd AI-Infra-Learning-Lab/50_项目产出/P01_Mini_Scheduler/mini_scheduler
python examples/smoke_check.py
python -m pytest -q
```

## 记录模板
### 输入任务

```text
id | submit_time | estimated_duration | priority
```

### 输出结果

```text
id | start_time | finish_time | waiting_time | turnaround_time
```

### 结论

- FIFO 在这组数据里是否稳定？
- 有没有长任务拖慢后续任务？
- 平均值和 P95 的差距大不大？

## 验收标准

- [ ] FIFO 顺序正确。
- [ ] 等待时间计算正确。
- [ ] 完成时间计算正确。
- [ ] 至少有 1 个 pytest 覆盖核心规则。
- [ ] 记录里写出了观察结论，而不是只贴结果。

## 常见错误

- 把“按 id 排序”误当成 FIFO。
- 忘了算等待时间和完成时间的差。
- 任务到达时间和执行顺序不一致。
- 只看平均值，不看最大值和 P95。

## 关联

- [[50_项目产出/P01_Mini_Scheduler/P01_Mini_Scheduler 项目主页|P01 Mini Scheduler 项目主页]]
- [[50_项目产出/P01_Mini_Scheduler/04_实验记录/FIFO_vs_Priority_vs_SJF|FIFO vs Priority vs SJF]]
- [[20_资料库/模块资料索引/M05_任务队列与调度_资料索引|M05 任务队列与调度资料索引]]
