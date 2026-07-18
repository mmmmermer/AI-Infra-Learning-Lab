# P01 README 草稿

## Mini Scheduler

Mini Scheduler 是一个面向 AI / RAG / Agent workload 的最小任务调度模拟项目。

它的目标不是一开始做完整云平台，而是先把调度系统里最核心的问题做清楚：

```text
任务来了以后，系统如何决定谁先执行、谁等待、分配给哪个 worker，以及如何用指标证明策略差异？
```

## 项目定位

这个项目服务于 AI Infra / 云原生资源调度 / RAG Agent 平台方向的基础训练。

第一阶段只做纯 Python 模拟，重点训练：

- 任务建模
- worker 建模
- 调度策略
- 指标统计
- pytest 测试
- 实验对比
- README 和项目表达

## 当前支持能力
- FIFO / Priority / SJF / Cost-aware 调度策略
- Cost-aware 权重预设：default / duration_dominant / token_dominant / priority_dominant
- Aging / 最大等待保护策略
- 单 worker 执行模拟
- 多 worker 执行模拟
- 低负载与高峰负载任务流
- 权重敏感任务流
- 等待时间、周转时间、P95/P99 尾延迟统计
- 最大队列长度统计
- worker 利用率统计
- 按 `task_type` 分组的等待时间分析
- 无依赖 smoke check
- pytest 测试文件
- 策略对比、高峰负载、Cost-aware、aging、worker 数量实验记录

## 推荐目录结构
```text
mini_scheduler/
├─ scheduler/
│  ├─ __init__.py
│  ├─ models.py
│  ├─ strategies.py
│  ├─ simulator.py
│  ├─ metrics.py
│  ├─ workloads.py
│  └─ experiments.py
├─ tests/
│  ├─ test_strategies.py
│  ├─ test_simulator.py
│  ├─ test_metrics.py
│  └─ test_experiments.py
├─ examples/
│  ├─ run_demo.py
│  ├─ run_high_load_experiment.py
│  ├─ run_cost_weight_experiment.py
│  ├─ run_aging_experiment.py
│  ├─ run_worker_count_experiment.py
│  └─ smoke_check.py
├─ pyproject.toml
└─ README.md
```

## 核心模型

### Task

任务表示一个待执行的 AI workload，例如 RAG 查询、Agent 工具调用、embedding 批处理或模拟推理请求。

核心字段：

| 字段 | 含义 |
|---|---|
| `id` | 任务编号 |
| `task_type` | 任务类型 |
| `priority` | 优先级，当前约定 `1` 最高 |
| `estimated_duration` | 预计执行时间 |
| `submit_time` | 到达时间 |
| `token_count` | 预计 token 数，供 Cost-aware 策略使用 |
| `start_time` | 开始执行时间 |
| `finish_time` | 完成时间 |
| `status` | 任务状态 |

### Worker

worker 表示执行任务的资源。

核心字段：

| 字段 | 含义 |
|---|---|
| `id` | worker 编号 |
| `available_at` | worker 下一次可用时间 |
| `current_task_id` | 当前任务 |
| `total_busy_time` | 累计忙碌时间 |

## 调度策略

### FIFO

按 `submit_time` 排序，先到先执行。

适合作为 baseline，优点是简单，缺点是长任务可能拖慢后续任务。

### Priority

按 `(priority, submit_time)` 排序。

当前约定 `priority=1` 最高，数字越大优先级越低。它适合在线请求或关键任务优先的场景，但可能让低优先级任务等待过久。

### SJF

按 `(estimated_duration, submit_time)` 排序。

它通常能降低平均等待时间，但可能让长任务长期靠后。

### Cost-aware

按 `(cost_score, submit_time)` 排序。

第一版成本分数可以使用：

```text
cost_score = estimated_duration + 0.001 * token_count + priority * 0.5
```

它用于模拟 AI workload 中“耗时、token 成本、业务优先级”共同影响调度决策的情况。

## 指标

| 指标 | 含义 |
|---|---|
| waiting_time | `start_time - submit_time` |
| turnaround_time | `finish_time - submit_time` |
| average_waiting_time | 平均等待时间 |
| max_waiting_time | 最大等待时间 |
| p95_waiting_time | P95 尾延迟 |
| p99_waiting_time | P99 尾延迟 |
| worker_utilization | worker 忙碌时间 / 总模拟时间 |



Cost-aware 权重实验额外输出按任务类型分组的指标：

| 分组指标 | 含义 |
|---|---|
| task_type | 任务类型，例如 `urgent_medium`、`batch_heavy` |
| count | 该类型任务数量 |
| avg_wait | 该类型平均等待时间 |
| max_wait | 该类型最大等待时间 |
| p95 | 该类型 P95 等待时间 |

这个分组表用于回答：

```text
某个策略整体指标变好时，是否牺牲了某一类任务？
```

## 运行方式
进入代码目录：

```bash
cd AI-Infra-Learning-Lab/50_项目产出/P01_Mini_Scheduler/mini_scheduler
```

运行 demo：

```bash
python examples/run_demo.py
```

当前 demo 会输出四种策略：

```text
strategy=fifo
strategy=priority
strategy=sjf
strategy=cost_aware
```

每种策略至少包含：

```text
order=...
average_wait_time=...
average_turnaround_time=...
p95_wait_time=...
p99_wait_time=...
worker_utilization=...
```

如果当前机器还没安装 pytest，可以先运行无依赖检查：

```bash
python examples/smoke_check.py
```

看到下面输出，说明核心导入、排序、模拟和指标链路是通的：

```text
smoke_check=passed
```



运行高峰负载实验：

```bash
python examples/run_high_load_experiment.py
```

这个命令会比较低负载和高峰负载下四种策略的表现：

- FIFO
- Priority
- SJF
- Cost-aware

输出指标包括：

- average_wait_time
- max_wait_time
- p95_wait_time
- p99_wait_time
- max_ready_queue_length
- worker_utilization



运行 Cost-aware 权重实验：

```bash
python examples/run_cost_weight_experiment.py
```

这个命令会比较四组成本权重：

- default
- duration_dominant
- token_dominant
- priority_dominant

用于观察 `estimated_duration`、`token_count`、`priority` 三个因素如何影响平均等待时间和尾延迟。



运行 aging / 最大等待保护实验：

```bash
python examples/run_aging_experiment.py
```

这个命令会比较：

- no_aging
- gentle_aging
- strong_aging

用于观察等待保护是否能降低极端尾延迟，以及它会牺牲哪些任务类型。



运行 worker 数量实验：

```bash
python examples/run_worker_count_experiment.py
```

这个命令会比较：

- worker 数量：1 / 2 / 4 / 8
- 调度策略：FIFO / Priority / SJF / Cost-aware

用于观察增加 worker 是否能降低 P95/P99，以及资源利用率如何变化。



导出实验结果表格：

```bash
python examples/export_results.py
```

生成 SVG 图表：

```bash
python examples/generate_svg_charts.py
```

输出目录：

```text
mini_scheduler/artifacts/
```

当前会生成：

- `experiment_summary_tables.md`
- `prediction_error_summary.csv`
- `worker_count_fifo_p95.svg`
- `worker_count_fifo_utilization.svg`
- `cost_weight_p99.svg`
- 多个 CSV 源数据文件



生成的 SVG 图表包括：

- `mini_scheduler_architecture.svg`
- `worker_count_fifo_p95.svg`
- `worker_count_fifo_utilization.svg`
- `cost_weight_p99.svg`

## 测试方式
完整测试命令：

```bash
python -m pytest
```

当前已经准备了测试文件：

- `tests/test_strategies.py`
- `tests/test_simulator.py`
- `tests/test_metrics.py`
- `tests/test_experiments.py`

覆盖目标：

- FIFO 按到达时间排序
- Priority 按优先级排序
- predicted SJF 按预计耗时排序，oracle SJF 仅作不可部署对照
- Cost-aware 按成本分数排序
- 等待时间和周转时间计算正确
- P95/P99 计算可用
- worker 利用率计算正确
- 单 worker 模拟不会提前执行尚未到达的任务

当前已在项目 Python 3.13 虚拟环境运行：`28 passed`。若另一个终端提示 `No module named pytest`，先确认已经激活项目 `.venv`，不要改用系统 Python 3.8/3.9。

## 实验记录

项目实验记录：[[50_项目产出/P01_Mini_Scheduler/04_实验记录/FIFO_vs_Priority_vs_SJF|FIFO vs Priority vs SJF vs Cost-aware]]

对应实验：

- [[40_实验练习/E05_调度实验/E05-01 实现 FIFO 调度|E05-01 FIFO baseline]]
- [[40_实验练习/E05_调度实验/E05-02 比较 FIFO 和 Priority|E05-02 FIFO vs Priority]]
- [[40_实验练习/E05_调度实验/E05-03 高峰负载下的 P95 延迟实验|E05-03 P95 尾延迟]]
- [[40_实验练习/E05_调度实验/E05-04 成本感知调度模拟|E05-04 Cost-aware]]

## 项目结果与分析

> 以下均为确定性参考 fixture。标准 fixture 中 `estimated_duration == actual_duration`，因此 predicted/oracle SJF 相同；只有 prediction-error counterexample 故意制造估计偏差。不得把这些单次表格写成科研或生产结论。

### 1. 高峰负载会放大调度策略差异

低负载下，FIFO / Priority / SJF / Cost-aware 的表现几乎一致：

```text
average_wait_time = 0.17
P95 = 1.00
worker_utilization = 0.61
```

高峰负载下，worker 利用率接近饱和，策略差异开始显现：

| 策略 | 平均等待时间 | P95 | P99 | 最大队列长度 |
|---|---:|---:|---:|---:|
| FIFO | 48.71 | 97.70 | 101.45 | 30 |
| Priority | 37.02 | 112.95 | 121.45 | 26 |
| predicted SJF | 26.04 | 108.45 | 121.45 | 26 |
| oracle SJF | 26.04 | 108.45 | 121.45 | 26 |
| Cost-aware | 26.51 | 108.45 | 121.45 | 26 |

结论：

```text
在估计完全准确的固定 fixture 中，平均等待时间更低不代表尾延迟更好；predicted/oracle SJF 与 Cost-aware 可能让部分任务承担更高 P99。预测有误时结果可能反转，见 `prediction_error_summary.csv`。
```

### 2. Cost-aware 权重会改变“谁被牺牲”

在权重敏感任务流中，duration/token/priority 三种因素会产生明显冲突：

| 权重预设 | 平均等待时间 | P95 | P99 | 观察 |
|---|---:|---:|---:|---|
| duration_dominant | 37.30 | 99.60 | 104.40 | 平均等待最低，但长任务被推后 |
| token_dominant | 48.63 | 110.60 | 110.80 | 高 token 任务被严重推迟 |
| priority_dominant | 46.63 | 99.60 | 104.40 | 高优先级任务被保护，但低优先级任务被牺牲 |

分组分析显示：

```text
priority_dominant 下 urgent_medium 平均等待从 67.20 降到 6.20，
但 low_priority_short 平均等待从 0.40 升到 35.40。
```

结论：

```text
Cost-aware 调度不能只看总表，必须做 task_type 分组分析，否则会掩盖某类任务被系统性牺牲的问题。
```

### 3. Aging / 最大等待保护能降低极端尾延迟

在 token_dominant 权重下加入最大等待保护：

| 配置 | 平均等待时间 | P95 | P99 |
|---|---:|---:|---:|
| no_aging | 48.63 | 110.60 | 110.80 |
| strong_aging | 42.66 | 100.80 | 104.40 |

`short_high_token` 的平均等待时间从 88.40 降到 52.40，说明最大等待保护能缓解高 token 短任务长期被推迟的问题。

代价是部分原本很快的任务等待增加，例如 `low_priority_short` 从 0.40 上升到 4.00。

结论：

```text
Aging 不是免费优化，而是在平均效率、尾部风险和公平性之间重新分配等待时间。
```

### 4. 增加 worker 能降低 P95，但会降低利用率

以 FIFO 为例：

| worker 数量 | P95 | worker 利用率 |
|---:|---:|---:|
| 1 | 97.70 | 0.97 |
| 2 | 42.80 | 0.86 |
| 4 | 15.70 | 0.61 |
| 8 | 3.50 | 0.30 |

结论：

```text
在当前固定 fixture 中，扩容后尾延迟数值下降，同时资源利用率下降。该单次结果不表示统计显著或真实容量结论；调度系统仍需同时报告延迟和资源成本。
```

## 项目总结

Mini Scheduler 当前已经形成一条完整实验链：

```text
任务建模 -> 调度策略 -> 指标统计 -> 高峰负载 -> 权重敏感性 -> 分组分析 -> aging 保护 -> 多 worker 扩容
```

它不是生产级调度器，也不能给出一般化结论；它可以用来演示以下待研究问题：

- 策略会改变不同任务类型的等待时间分配。
- 平均值、P95/P99、最大等待时间必须同时看。
- 资源扩容能降低延迟，但会带来利用率下降。
- 保护机制能降低极端等待，但会影响其他任务。

## 后续计划
- 将 `artifacts/` 中的 SVG 图表嵌入最终 README。
- 生成项目运行截图，展示 demo / high load / worker count 三个入口。
- 安装或配置 pytest 环境，运行完整测试集。
- 接入 FastAPI：任务创建 API、任务状态查询 API、metrics endpoint。
- 接入 RAG / Agent 模拟请求，让 task_type 从模拟字段逐步接近真实 workload。
- 后续映射到 Kueue / Volcano / Kubernetes 调度概念。

## 学习路线关联

- [[10_学习模块/M01_Python工程能力/M01_Python工程能力_学习地图|M01 Python 工程能力]]
- [[10_学习模块/M02_后端API与服务化/M02_后端API与服务化_学习地图|M02 后端 API 与服务化]]
- [[10_学习模块/M05_任务队列与调度/M05_任务队列与调度_学习地图|M05 任务队列与调度]]
