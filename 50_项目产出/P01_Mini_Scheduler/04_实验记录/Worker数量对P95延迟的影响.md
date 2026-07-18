# Worker 数量对 P95 延迟的影响

## 实验定位

这个实验用于回答一个工程里很常见的问题：

```text
增加 worker 数量是否一定能解决高峰负载下的尾延迟？
```

直觉上，worker 越多，排队越少；但真实系统还要同时看利用率。如果 worker 数量过多，P95 会下降，但资源可能大量空闲。

## 实验入口

代码入口：

```text
mini_scheduler/examples/run_worker_count_experiment.py
mini_scheduler/scheduler/simulator.py
mini_scheduler/scheduler/experiments.py
```

运行命令：

```bash
cd AI-Infra-Learning-Lab/50_项目产出/P01_Mini_Scheduler/mini_scheduler
python examples/run_worker_count_experiment.py
```

## 实验设置

任务流：`build_peak_load_tasks()`

策略：

- FIFO
- Priority
- SJF
- Cost-aware

worker 数量：

```text
1 / 2 / 4 / 8
```

指标：

- 平均等待时间
- 最大等待时间
- P95 等待时间
- P99 等待时间
- 最大队列长度
- worker 利用率

## 实验结果

| 策略 | workers | 平均等待 | 最大等待 | P95 | P99 | 最大队列 | 利用率 |
|---|---:|---:|---:|---:|---:|---:|---:|
| FIFO | 1 | 48.71 | 101.45 | 97.70 | 101.45 | 31 | 0.97 |
| FIFO | 2 | 19.74 | 44.40 | 42.80 | 44.40 | 29 | 0.86 |
| FIFO | 4 | 5.31 | 17.20 | 15.70 | 17.20 | 22 | 0.61 |
| FIFO | 8 | 0.88 | 3.70 | 3.50 | 3.70 | 11 | 0.30 |
| Priority | 1 | 37.02 | 121.45 | 112.95 | 121.45 | 27 | 0.97 |
| Priority | 2 | 14.00 | 55.85 | 50.60 | 55.85 | 24 | 0.83 |
| Priority | 4 | 4.22 | 19.20 | 17.70 | 19.20 | 20 | 0.61 |
| Priority | 8 | 0.79 | 4.75 | 4.00 | 4.75 | 11 | 0.30 |
| SJF | 1 | 26.04 | 121.45 | 108.45 | 121.45 | 27 | 0.97 |
| SJF | 2 | 9.75 | 54.10 | 49.10 | 54.10 | 21 | 0.85 |
| SJF | 4 | 3.25 | 19.15 | 15.40 | 19.15 | 17 | 0.61 |
| SJF | 8 | 0.67 | 4.95 | 3.50 | 4.95 | 10 | 0.30 |
| Cost-aware | 1 | 26.51 | 121.45 | 108.45 | 121.45 | 27 | 0.97 |
| Cost-aware | 2 | 9.75 | 54.10 | 49.10 | 54.10 | 21 | 0.85 |
| Cost-aware | 4 | 3.25 | 19.15 | 15.40 | 19.15 | 17 | 0.61 |
| Cost-aware | 8 | 0.67 | 4.95 | 3.50 | 4.95 | 10 | 0.30 |

## 结论

### 1. 在本固定 fixture 中，增加 worker 后 P95 数值下降

以 FIFO 为例：

```text
workers=1: P95 = 97.70
workers=2: P95 = 42.80
workers=4: P95 = 15.70
workers=8: P95 = 3.50
```

这说明高峰负载下，worker 数量确实是尾延迟的重要因素。

### 2. 但 worker 越多，利用率越低

仍以 FIFO 为例：

```text
workers=1: utilization = 0.97
workers=4: utilization = 0.61
workers=8: utilization = 0.30
```

这说明资源扩容不是免费午餐。8 个 worker 能把 P95 压低，但大部分时间资源并不满。

### 3. 策略差异在资源紧张时更明显

单 worker 时，SJF / Cost-aware 的平均等待时间比 FIFO 更低，但最大等待和 P99 可能更差。worker 增加后，策略差异逐渐缩小，因为排队压力被资源缓解。

### 4. 工程解释

这个实验说明：

```text
尾延迟优化不能只靠调度策略，也不能只靠加资源。合理做法是同时看策略、worker 数量、P95/P99 和利用率。
```

## 下一步

- 加入多 worker 下的 Cost-aware 权重实验。
- 加入多 worker 下的 aging / 最大等待保护实验。
- 把 worker 数量作为 README 和简历表达里的关键实验变量。
