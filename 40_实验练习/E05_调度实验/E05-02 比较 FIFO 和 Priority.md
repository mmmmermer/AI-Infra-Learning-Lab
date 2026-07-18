# E05-02 比较 FIFO、Priority 和 SJF

## 实验定位

这一步不是为了“再写一个调度器”，而是为了回答一个更重要的问题：

```text
Priority 和 SJF 分别改善了谁，又牺牲了谁？
```

FIFO 是 baseline，Priority 按业务重要性选择，SJF 按预计耗时选择。三种策略必须使用同一份
不可变 workload，分别回答公平、业务优先级和平均等待时间之间的取舍。

## 前置阅读
- [[10_学习模块/M05_任务队列与调度/教材章节/04_Priority_和业务优先级|M05 章节教材第 4 章：Priority 和业务优先级]]
- [[10_学习模块/M05_任务队列与调度/教材章节/05_SJF_和平均等待时间|M05 章节教材第 5 章：SJF 和平均等待时间]]
- [[40_实验练习/E05_调度实验/E05-01 实现 FIFO 调度|E05-01 实现 FIFO 调度]]
- [[10_学习模块/M05_任务队列与调度/M05_任务队列与调度_复现推进表|M05 复现推进表]]
- `heapq` 的最小堆规则
- Priority 的键约定

## baseline

- FIFO
- Priority
- SJF

## 关键约定

先统一一件事：**数值越小表示优先级越高**，或者反过来用负数转换，但整组实验必须保持一致。

建议先用更直观的方式：

- `1` 表示最高优先级
- `2` 表示次高优先级
- 数字越大，优先级越低

## 实验变量

- 高优先级任务比例
- 任务到达顺序
- 任务是否混有长任务
- `estimated_duration` 是否等于真实耗时
- worker 数量

## 推荐数据集

至少准备三类任务：

1. 少量高优先级短任务
2. 少量低优先级长任务
3. 优先级与耗时发生冲突的任务

这样更容易看出 Priority 的效果和副作用。

## 推荐实现方式
第一版可以使用 `sorted()`，但任务页不提供完整排序键。先填写策略契约：

```python
def sort_by_priority(tasks: list[Task]) -> list[Task]:
    """Order by business priority with deterministic tie-breakers."""
    raise NotImplementedError


def sort_by_sjf(tasks: list[Task]) -> list[Task]:
    """Order by estimated duration with deterministic tie-breakers."""
    raise NotImplementedError
```

当前任务采用：

```text
priority=1 最高，数字越大优先级越低
```

还有一个容易忽略的点：调度器不应该为了等待未来的高优先级任务而让 worker 空转。当前 P01 的模拟规则是：每次只从 `submit_time <= current_time` 的已到达任务里选择下一个任务。

## 实验步骤

1. 复用 E05-01 的任务模型。
2. 构造一组混合优先级任务。
3. 用 FIFO 跑一次，记录结果。
4. 用 Priority 跑一次，记录结果。
5. 用 SJF 跑一次，记录结果。
6. 对比平均等待时间、最大等待时间、P95 等待时间和分组等待时间。
7. 单独观察低优先级任务和长任务是否被明显延后。
8. 把一部分 `estimated_duration` 改错，再观察 SJF 对预测误差的敏感性。
9. 写出每种策略的“收益、代价、成立条件”。

## 结果观察

你应该重点看五件事：

- 高优先级任务是不是更快了
- 低优先级任务是不是更慢了
- 整体的尾部表现有没有变差
- 短任务是不是更快、长任务是不是更慢
- 估时错误后 SJF 的优势是否保持

## 记录模板

### 实验数据

```text
任务集合、优先级分布、到达顺序、worker 数量
```

### 对比结果

```text
FIFO: 平均等待时间 / P95 / 最大等待时间
Priority: 平均等待时间 / P95 / 最大等待时间
SJF: 平均等待时间 / P95 / 最大等待时间
```

### 结论

- Priority 改善了哪些任务？
- Priority 让哪些任务更慢了？
- SJF 改善和伤害了哪些任务？
- 结论对估时误差是否敏感？
- 这种取舍是否符合你的场景？

## 验收标准

- [ ] 能解释 Priority 改善了谁。
- [ ] 能解释 Priority 伤害了谁。
- [ ] 能解释 SJF 优化平均等待时可能伤害长任务。
- [ ] 能展示至少一组估时误差反例。
- [ ] 能写出一条清楚的结论，不只是“结果更好/更差”。
- [ ] 能说明优先级键的约定没有混乱。

## 常见错误

- 先做了 Priority，却没保留 FIFO baseline。
- 优先级方向前后不一致。
- 只看平均等待时间，不看低优先级任务的尾部。
- 用真实耗时排序后声称是 predicted SJF。
- 三种策略复用已被修改的 Task 对象，导致结果互相污染。
- 忘了记录任务到达顺序，导致对比失真。

## 关联

- [[50_项目产出/P01_Mini_Scheduler/P01_Mini_Scheduler 项目主页|P01 Mini Scheduler 项目主页]]
- [[50_项目产出/P01_Mini_Scheduler/04_实验记录/FIFO_vs_Priority_vs_SJF|FIFO vs Priority vs SJF]]
- [[20_资料库/模块资料索引/M05_任务队列与调度_资料索引|M05 任务队列与调度资料索引]]
- [[60_科研训练/研究项目/RQ01_RAG_Agent请求调度尾延迟/00_研究问题|RQ01 研究问题]]
