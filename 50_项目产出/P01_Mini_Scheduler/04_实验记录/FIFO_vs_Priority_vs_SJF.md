# FIFO vs Priority vs SJF vs Cost-aware

> 2026-07-10 审计说明：本页是历史教学实验记录，文中的 `SJF` 按当前代码应理解为 `predicted_sjf`。标准 fixture 中估计值等于真实值，所以它也与 `oracle_sjf` 重合；这不是预测误差或科研有效性证据。最新机器生成表见 `mini_scheduler/artifacts/experiment_summary_tables.md`。

## 实验定位
这份记录不是单个练习页，而是 P01 Mini Scheduler 的第一份项目型实验记录。它把 E05-01、E05-02、E05-03、E05-04 的结果汇总起来，用同一套任务、同一套指标和同一套口径比较 FIFO、Priority、SJF、Cost-aware 四种调度策略。

目标是形成可以写进 README、简历和科研问题里的项目结论。

## 对应实验

- [[40_实验练习/E05_调度实验/E05-01 实现 FIFO 调度|E05-01 实现 FIFO 调度]]
- [[40_实验练习/E05_调度实验/E05-02 比较 FIFO 和 Priority|E05-02 比较 FIFO 和 Priority]]
- [[40_实验练习/E05_调度实验/E05-03 高峰负载下的 P95 延迟实验|E05-03 高峰负载下的 P95 延迟实验]]
- [[40_实验练习/E05_调度实验/E05-04 成本感知调度模拟|E05-04 成本感知调度模拟]]

## 实验问题

这组实验要回答：

```text
在 AI / RAG / Agent 任务混合到达时，FIFO、Priority、SJF 各自更适合什么场景，它们在平均等待时间、P95 尾延迟和公平性上有什么取舍？
```

## baseline
- FIFO
- Priority
- SJF
- Cost-aware

## 统一实验口径

### 优先级约定

- `priority=1` 表示最高优先级。
- 数字越大，优先级越低。
- Priority 排序键使用 `(priority, submit_time)`。

### 时间字段约定

| 字段 | 含义 |
|---|---|
| `submit_time` | 任务到达系统的时间 |
| `start_time` | worker 开始执行任务的时间 |
| `finish_time` | worker 执行完成的时间 |
| `waiting_time` | `start_time - submit_time` |
| `turnaround_time` | `finish_time - submit_time` |

### 指标约定

| 指标 | 含义 |
|---|---|
| 平均等待时间 | 所有任务 waiting_time 的平均值 |
| 最大等待时间 | 最慢开始执行的任务等待了多久 |
| P95 等待时间 | 95% 任务以内的等待时间边界 |
| P99 等待时间 | 更极端的尾部等待时间 |
| worker 利用率 | worker 忙碌时间 / 总模拟时间 |

## 输入任务分布
这一页先使用 `mini_scheduler/examples/run_demo.py` 里的固定样例任务。它不是最终实验数据集，而是第一版可复现口径，用来确认策略、指标和输出链路都能跑通。

### 基础任务集

| id | task_type | priority | estimated_duration | submit_time | token_count | 场景解释 |
|---|---|---:|---:|---:|---:|---|
| task-001 | rag_query | 2 | 5.0 | 0.0 | 1200 | 普通 RAG 查询，最早到达，耗时中等 |
| task-002 | agent_tool | 1 | 2.0 | 1.0 | 500 | 高优先级 Agent 工具调用，较短 |
| task-003 | embedding | 3 | 1.0 | 2.0 | 3000 | 低优先级 embedding 小任务，执行短但 token 多 |
| task-004 | long_context | 2 | 8.0 | 3.0 | 8000 | 长上下文任务，耗时和 token 都高 |

### 为什么这组任务适合第一轮

这组任务刻意混合了四种特征：

- 最早到达但不是最高优先级的任务：`task-001`
- 后到达但优先级最高的短任务：`task-002`
- 很短但低优先级、token 较多的任务：`task-003`
- 长耗时、高 token 的任务：`task-004`

它能帮助你观察：

- FIFO 是否稳定但可能不够聪明。
- Priority 是否会让低优先级短任务被推迟。
- SJF 是否会让短任务更快。
- Cost-aware 是否会把耗时、token 和优先级揉成一个更综合的排序信号。

### 高峰任务集
高峰任务集已经在 E05-03 中落地，代码入口：

```text
mini_scheduler/scheduler/workloads.py
mini_scheduler/examples/run_high_load_experiment.py
```

任务分布：

```text
总任务数：52
warmup：8 个平稳任务
burst：36 个密集任务，submit_time 从 20.0 开始，每 0.25 到达一个
cooldown：8 个恢复期任务
短任务：1.0-2.0
长任务：6.0-8.0
优先级：1/2/3 混合
worker 数量：当前为单 worker
```

这组任务专门用于观察：

- 高峰时队列是否堆积。
- 平均等待时间和 P95/P99 是否分化。
- SJF / Cost-aware 是否降低平均等待，但推迟长任务。
- Priority 是否改善关键任务，但放大低优先级任务尾部等待。

## 策略设置

### FIFO

按 `submit_time` 排序，先到先执行。

### Priority

按 `(priority, submit_time)` 排序，优先级相同再按到达时间。

### SJF

按 `(estimated_duration, submit_time)` 排序，预计耗时短的任务先执行。


### Cost-aware

按 `(cost_score, submit_time)` 排序。第一版成本分数可以由预计耗时、token 数和优先级组合得到，用于模拟 AI workload 中的资源消耗差异。

## 实验结果记录
下面结果来自当前代码骨架的第一轮 demo：

```bash
python examples/run_demo.py
```

运行目录：`mini_scheduler/`

注意：这是小样例验证结果，作用是确认策略链路和指标链路能跑通。后续做 E05-03 时，需要用更大的高峰任务集重新生成结果。

### 顺序对比
| 策略 | 执行顺序 | 观察 |
|---|---|---|
| FIFO | task-001, task-002, task-003, task-004 | 完全按到达时间执行，稳定、容易解释 |
| Priority | task-001, task-002, task-004, task-003 | 只在任务已到达后按优先级选；低优先级 `task-003` 被推迟到最后 |
| SJF | task-001, task-003, task-002, task-004 | 在可选任务里优先短任务，短任务等待降低 |
| Cost-aware | task-001, task-002, task-003, task-004 | 当前公式下结果接近 FIFO，因为 `task-004` 成本明显更高 |

### 指标对比
| 策略 | 平均等待时间 | 平均周转时间 | P95 | P99 | worker 利用率 |
|---|---:|---:|---:|---:|---:|
| FIFO | 3.50 | 7.50 | 5.00 | 5.00 | 1.00 |
| Priority | 5.25 | 9.25 | 13.00 | 13.00 | 1.00 |
| SJF | 3.25 | 7.25 | 5.00 | 5.00 | 1.00 |
| Cost-aware | 3.50 | 7.50 | 5.00 | 5.00 | 1.00 |

### 这组结果应该怎么读

第一眼看，Priority 的平均等待时间和 P95/P99 反而更差。这不是代码错误，而是这组小任务里 `task-003` 虽然很短，但优先级低；Priority 在 `task-002` 执行后选择了同优先级但成本很高的 `task-004`，导致 `task-003` 等到最后，尾部等待时间被拉高。

SJF 在这组样例里略好，因为它更照顾短任务。但这不代表 SJF 永远最好：如果长任务持续被短任务插队，长任务可能出现饥饿风险。

Cost-aware 当前接近 FIFO，是因为公式把 `estimated_duration`、`token_count`、`priority` 都纳入后，`task-004` 的成本明显偏高，而 `task-002/task-003` 的成本排序没有造成严重尾部副作用。后续需要调权重，观察公式敏感性。



### E05-03 高峰负载实验结果

命令：

```bash
python examples/run_high_load_experiment.py
```

低负载下四种策略几乎相同：

| 策略 | 平均等待时间 | 最大等待时间 | P95 | P99 | 最大队列长度 | worker 利用率 |
|---|---:|---:|---:|---:|---:|---:|
| FIFO | 0.17 | 1.00 | 1.00 | 1.00 | 1 | 0.61 |
| Priority | 0.17 | 1.00 | 1.00 | 1.00 | 1 | 0.61 |
| SJF | 0.17 | 1.00 | 1.00 | 1.00 | 1 | 0.61 |
| Cost-aware | 0.17 | 1.00 | 1.00 | 1.00 | 1 | 0.61 |

高峰负载下策略差异明显：

| 策略 | 平均等待时间 | 最大等待时间 | P95 | P99 | 最大队列长度 | worker 利用率 |
|---|---:|---:|---:|---:|---:|---:|
| FIFO | 48.71 | 101.45 | 97.70 | 101.45 | 30 | 0.97 |
| Priority | 37.02 | 121.45 | 112.95 | 121.45 | 26 | 0.97 |
| predicted SJF | 26.04 | 121.45 | 108.45 | 121.45 | 26 | 0.97 |
| oracle SJF | 26.04 | 121.45 | 108.45 | 121.45 | 26 | 0.97 |
| Cost-aware | 26.51 | 121.45 | 108.45 | 121.45 | 26 | 0.97 |

项目级观察：

- 低负载下，调度策略不是主要矛盾；任务到达速度低，队列几乎不积压。
- 高峰负载下，worker 利用率接近 1.00，说明系统进入饱和状态。
- 在估计完全准确的固定 fixture 中，predicted/oracle SJF 与 Cost-aware 降低平均等待，但最大等待和 P99 更高；prediction-error counterexample 进一步表明估计错误时 predicted SJF 可能比 FIFO 更差。
- FIFO 平均等待更高，但尾部最大等待反而较低，说明它更“钝”，但不容易极端饿死某一类任务。
- 这正好说明项目不能只报平均值，必须同时报告 P95/P99、max wait 和队列长度。



### E05-04 Cost-aware 权重实验结果

命令：

```bash
python examples/run_cost_weight_experiment.py
```

任务流：`build_cost_sensitivity_tasks()`，共 30 个密集到达任务，用来制造 duration、token、priority 三者冲突。

| 权重预设 | 平均等待时间 | 最大等待时间 | P95 | P99 | 最大队列长度 | worker 利用率 |
|---|---:|---:|---:|---:|---:|---:|
| default | 41.97 | 104.40 | 99.60 | 104.40 | 23 | 0.92 |
| duration_dominant | 37.30 | 104.40 | 99.60 | 104.40 | 23 | 0.92 |
| token_dominant | 48.63 | 110.80 | 110.60 | 110.80 | 23 | 0.92 |
| priority_dominant | 46.63 | 104.40 | 99.60 | 104.40 | 26 | 0.92 |

项目级观察：

- duration_dominant 平均等待最低，说明当前任务流里“优先处理短耗时任务”更有效。
- token_dominant 的 P95/P99 最差，说明过度强调 token 成本可能制造更严重的尾部等待。
- priority_dominant 最大队列长度最高，说明强优先级可能让排队更不均衡。
- worker 利用率相同，说明差异来自调度顺序，而不是资源空闲。



### E05-04 按 task_type 分组结果

`run_cost_weight_experiment.py` 现在会额外输出 `task_type_breakdown`，用于解释不同权重到底牺牲了哪类任务。

关键观察：

| 权重 | 被明显改善的任务 | 被明显牺牲的任务 | 说明 |
|---|---|---|---|
| duration_dominant | low_priority_short、cheap_medium | batch_heavy、long_low_token | 偏向短任务，平均等待更低，但长任务等待高 |
| token_dominant | cheap_medium、long_low_token | short_high_token、urgent_medium | 偏向低 token 任务，高 token 短任务也会被推迟 |
| priority_dominant | urgent_medium | low_priority_short、short_high_token | 保护高优先级任务，但会牺牲低优先级任务 |

项目级结论：

```text
只看整体平均等待时间是不够的。Cost-aware 权重改变的不是“系统整体快慢”这么简单，而是改变不同任务类型之间的等待时间分配。项目报告里必须同时给出总表和分组表。
```



### Aging / 最大等待保护实验结果

命令：

```bash
python examples/run_aging_experiment.py
```

实验目的：在 token_dominant 权重下，测试 aging / 最大等待保护能否缓解某些任务被长期推迟的问题。

| 配置 | 平均等待时间 | 最大等待时间 | P95 | P99 | 最大队列长度 | worker 利用率 |
|---|---:|---:|---:|---:|---:|---:|
| no_aging | 48.63 | 110.80 | 110.60 | 110.80 | 23 | 0.92 |
| gentle_aging | 48.63 | 110.80 | 110.60 | 110.80 | 23 | 0.92 |
| strong_aging | 42.66 | 104.40 | 100.80 | 104.40 | 25 | 0.92 |

项目级观察：

- gentle_aging 没有明显改善，说明软等待奖励不足以对抗 token 成本差异。
- strong_aging 引入硬最大等待保护后，平均等待、最大等待、P95、P99 都下降。
- `short_high_token` 的平均等待从 88.40 降到 52.40，说明被 token 成本压制的任务得到了保护。
- 代价是部分原本很快的任务等待上升，例如 `low_priority_short` 从 0.40 上升到 4.00。

结论：

```text
最大等待保护能降低极端尾延迟，但会重新分配等待时间。调度策略不是单纯追求平均最优，而是在平均效率、尾部风险和任务公平性之间做权衡。
```



### Worker 数量对 P95 延迟的影响

命令：

```bash
python examples/run_worker_count_experiment.py
```

任务流：`build_peak_load_tasks()`

关键结果：

| 策略 | workers=1 P95 | workers=2 P95 | workers=4 P95 | workers=8 P95 |
|---|---:|---:|---:|---:|
| FIFO | 97.70 | 42.80 | 15.70 | 3.50 |
| Priority | 112.95 | 50.60 | 17.70 | 4.00 |
| SJF | 108.45 | 49.10 | 15.40 | 3.50 |
| Cost-aware | 108.45 | 49.10 | 15.40 | 3.50 |

利用率变化也很明显。以 FIFO 为例：

```text
workers=1 utilization=0.97
workers=4 utilization=0.61
workers=8 utilization=0.30
```

项目级结论：

```text
在本固定 fixture 中，增加 worker 数量后 P95/P99 数值下降，同时资源利用率下降。这个单次确定性结果不构成统计显著性或容量外推；调度优化仍需同时报告延迟和资源成本。
```

## 结果分析模板
### FIFO

FIFO 的好处是非常清楚：只按到达顺序执行，调试成本低，也最适合作为 baseline。当前样例里它的 P95/P99 都是 5.00，说明尾部没有被特别拉爆。

但 FIFO 的问题也明显：它不区分任务重要性，也不照顾短任务。如果最前面来了一个很长的任务，后面所有任务都要等。这就是经典的 convoy effect，后续高峰实验要重点观察。

适合场景：

- 第一版 baseline
- 任务差异不大
- 需要最简单、最可解释的队列规则

### Priority

Priority 的目标是照顾高优先级任务。当前约定 `priority=1` 最高，数字越大优先级越低。

当前样例里，Priority 的平均等待时间和 P95/P99 变差，核心原因是：低优先级短任务 `task-003` 被同优先级但更长的 `task-004` 挤到了后面。这说明 Priority 不能只看“重要性”，否则可能伤害低优先级任务的尾部体验。

适合场景：

- 在线请求必须优先于离线批任务
- 关键任务延迟比整体平均值更重要
- 后续能加入 aging、quota 或最大等待时间保护

### SJF

SJF 优先预计耗时短的任务。当前样例里它的平均等待时间最低，因为 `task-003` 很短，提前执行能减少整体等待。

但 SJF 的风险是它依赖 `estimated_duration`。真实 AI workload 中，任务耗时经常只能估计：prompt 长度、检索命中文档数、工具调用次数都会影响耗时。如果估计错误，SJF 的效果会下降。

适合场景：

- 任务耗时比较容易估计
- 目标是降低平均等待时间
- 可以接受长任务等待更久，或者另有长任务保护机制

### Cost-aware

Cost-aware 不是为了追求一个“神奇公式”，而是为了把 AI workload 的多维成本放到同一个调度键里。

当前公式是：

```text
cost_score = estimated_duration + 0.001 * token_count + priority * 0.5
```

这个公式的含义是：耗时是主因素，token 数是成本补充，priority 让低优先级任务分数更高。当前样例里，Cost-aware 的结果接近 FIFO，说明这组任务还不够大，公式差异没有充分展开。

适合场景：

- RAG / Agent / LLM 请求成本差异明显
- 希望避免高成本任务长期阻塞队列
- 后续需要做权重敏感性实验，而不是只跑一次

## 教学观察
基于当前小样例，只能形成实现层观察：

```text
在这组估计完全准确的固定模拟任务中，predicted/oracle SJF 的平均等待时间最低，而 Priority 的 P95/P99 更高。该结果只说明实现能展示策略权衡；它没有多 seed、置信区间、预测误差分布或真实 RAG/Agent workload，不能外推。
```

这个结论不能直接当最终项目结论，只能作为 v0.1 的第一轮观察。最终结论至少还需要：

- 更大的任务集。
- 低负载和高峰负载对比。
- 不同 worker 数量对比。
- Cost-aware 权重敏感性对比。
- 单独统计高优先级任务、低优先级任务、长任务、短任务的等待时间。

## 局限

- 当前是模拟任务，不是真实 RAG / Agent 请求。
- 第一版可能是单 worker，不能完全代表多 worker 平台。
- estimated_duration 默认已知，真实系统里通常只能估计。
- 暂未考虑任务失败、重试和资源异构。

## 下一步
1. 激活项目 Python 3.13 虚拟环境并运行：

```bash
python -m pytest
```

2026-07-10 参考实现已得到 `22 passed`。无依赖检查仍可用于最小环境诊断：

```bash
python examples/smoke_check.py
```

2. 把 `run_demo.py` 的固定任务集扩展到 20-30 个任务，观察小样例结论是否还成立。

3. 增加按任务类型分组的指标：

| 分组 | 要看的指标 |
|---|---|
| 高优先级任务 | 平均等待时间、P95 |
| 低优先级任务 | 最大等待时间、P95 |
| 短任务 | 平均等待时间 |
| 长任务 | 最大等待时间、是否被长期推迟 |

4. 做 E05-03 高峰负载实验：生成突发任务流，记录 P95/P99 和最大队列长度。

5. 做 E05-04 Cost-aware 权重实验：至少比较三组权重。

```text
版本 A：duration 主导
版本 B：token 主导
版本 C：priority 主导
```

6. 最后把稳定结论写回：

- [[50_项目产出/P01_Mini_Scheduler/06_README草稿|P01 README 草稿]]
- [[50_项目产出/P01_Mini_Scheduler/07_简历表达|P01 简历表达]]
- [[60_科研训练/研究项目/RQ01_RAG_Agent请求调度尾延迟/03_实验记录|RQ01 实验记录]]
