# P01 Mini Scheduler 项目主页

## 项目定位

一个面向 AI 推理/RAG/Agent 任务的最小调度器，用于训练 Python 工程能力、任务队列、worker 资源、调度策略、测试、指标统计和实验记录能力。

它不是一开始就做完整云平台，而是先把 AI workload 调度里最核心的问题抽出来：任务来了以后，系统如何决定谁先执行、谁等待、资源如何被使用、结果如何用数据说明。



## 当前定位提醒
当前 P01 已经包含较完整的 AI 辅助示范代码、实验结果和展示素材，但它现在的正确定位是：

```text
M05 教材配套参考答案 / 实验样板 / 后续亲手复现的对照材料
```

不要直接把它当作已经亲手完成的项目成果。后续需要按照 [[10_学习模块/M05_任务队列与调度/M05_任务队列与调度_章节教材|M05 章节教材]] 和 [[10_学习模块/M05_任务队列与调度/M05_任务队列与调度_复现推进表|M05 复现推进表]]，把核心代码和实验逐章亲手复现。

旧版教材化改造计划只保留为历史归档参考，不再作为正式学习入口。

## P01 状态分级

| 层级 | 当前状态 | 能否当作本人完成 | 正确使用方式 |
|---|---|---|---|
| AI 辅助参考答案 | 已生成示范代码、实验结果、图表、README 和表达草稿 | 不能 | 用作学习参照、复现对照和检查标准 |
| 本人亲手复现 | 待从 `task_sorter` 和 M05 R0/R1 开始逐步完成 | 暂未完成 | 按 M00/M01/M05 顺序手写、运行、测试、记录 |
| 可写入简历成果 | 需要完成复现、测试、实验记录和自我解释后才成立 | 暂不可用 | 只能在真实复现并能讲清楚后使用 |

判断原则：凡是由 AI 直接生成、尚未亲手运行和解释过的代码、图表、实验结论，都只能算“参考答案”。真正进入个人成果的部分，必须有你自己的实现记录、测试记录、失败记录和复盘说明。

## Python 版本兼容提醒

P01 统一在 Python 3.13 项目虚拟环境中运行。默认 `python` 仍可能指向系统 Python 3.8.6，因此创建环境时必须显式使用 `py -3.13`，激活后再运行测试和示例。

旧代码中的 `from __future__ import annotations` 可以保留，但 P01 不再声明兼容 Python 3.8/3.9。

## 当前学习阶段

当前处于 P01 v0.1：纯 Python 调度器核心。

本阶段先不接 FastAPI、数据库、Docker、RAG、Kubernetes。先完成可以运行、可以测试、可以解释结果的调度器内核。

主执行入口：[[50_项目产出/P01_Mini_Scheduler/08_阶段执行说明_v0.1|P01 v0.1 阶段执行说明]]

## 为什么做这个项目

这个项目是进入 AI Infra / RAG Agent 平台 / AI Workload 调度方向的最小作品。

它比直接学习 Kubernetes、Ray、vLLM 更适合当前阶段，因为它把复杂系统拆成了可控的基础问题：

- 任务如何建模
- worker 如何表示
- 调度策略如何设计
- 指标如何计算
- 测试如何保护规则
- 实验如何比较策略优劣

## 功能范围

### v0.1：纯 Python 调度核心

- Task 模型
- Worker 模型
- FIFO 策略
- Priority 策略
- SJF 策略
- 单 worker 执行模拟
- 等待时间
- 完成时间
- worker 利用率
- pytest
- 命令行 demo

### v0.2：多 worker 与基础实验
- 多 worker 分配
- worker `available_at`
- 队列长度
- FIFO / Priority / SJF / Cost-aware 对比实验
- P95 等待时间

### v0.3：服务化准备

- FastAPI 接口
- 任务创建 API
- 任务状态查询
- metrics endpoint

## 技术栈

- Python
- dataclass
- pytest
- logging
- 可选：Typer / argparse

后续升级：

- FastAPI
- SQLite / PostgreSQL
- Redis Streams；RQ / Celery 仅作队列框架对比
- Docker
- Prometheus / Grafana
- Locust 或 k6

## 参考答案材料状态（AI 辅助生成）

下面的勾选项只表示学习库里已经具备一套较完整的示范材料和对照答案，不表示这些内容已经由本人亲手完成。学习时应把它当作“标准答案旁边的样例工程”，而不是直接当作简历成果。

- [x] 完成 P01 v0.1 项目骨架
- [x] 建立 `mini_scheduler/scheduler/` 核心包
- [x] 完成 Task 和 Worker 模型
- [x] 完成 FIFO / Priority / SJF / Cost-aware 策略函数
- [x] 完成单 worker 调度模拟
- [x] 完成多 worker 调度模拟
- [x] 完成等待时间、周转时间、P95/P99、worker 利用率指标函数
- [x] 完成命令行 demo：`python examples/run_demo.py`
- [x] 完成无依赖检查：`python examples/smoke_check.py`
- [x] 完成低负载任务流：`build_low_load_tasks()`
- [x] 完成高峰负载任务流：`build_peak_load_tasks()`
- [x] 完成高峰实验入口：`python examples/run_high_load_experiment.py`
- [x] 完成 Cost-aware 权重预设：default / duration / token / priority
- [x] 完成权重敏感任务流：`build_cost_sensitivity_tasks()`
- [x] 完成 Cost-aware 权重实验入口：`python examples/run_cost_weight_experiment.py`
- [x] 完成按 task_type 分组指标：`summarize_by_task_type()`
- [x] 完成 aging / 最大等待保护策略
- [x] 完成 aging 实验入口：`python examples/run_aging_experiment.py`
- [x] 完成 worker 数量实验入口：`python examples/run_worker_count_experiment.py`
- [x] 完成实验结果 CSV 导出：`python examples/export_results.py`
- [x] 完成 SVG 图表生成：`python examples/generate_svg_charts.py`
- [x] 完成 P01 架构图：`mini_scheduler_architecture.svg`
- [x] 补充 E05-03 高峰负载实验结果
- [x] 补充 E05-04 Cost-aware 权重实验、分组分析和 aging 保护实验
- [x] 补充 Worker 数量对 P95 延迟的影响实验
- [x] 补充项目实验记录第一轮样例结果、高峰结果、权重结果、分组结论、保护策略结论和 worker 数量结论
- [x] 写入 README 项目结果与分析
- [x] 写入简历表达和面试讲法
- [x] 整理项目展示 CSV / Markdown 表格 / SVG 图表
- [x] 增加显式 `actual_duration` 和 prediction-error counterexample
- [x] 区分 artifact 中的 `predicted_sjf` 与 `oracle_sjf`
- [x] 在 Python 3.13 干净虚拟环境运行完整测试（28 passed，参考实现验证）
- [ ] 生成项目运行截图
- [ ] 接入 FastAPI / metrics endpoint

## 本人复现进度

这一部分才用于记录你从零到一亲手推进的进度。第一次学习不要直接改动参考答案工程，先用一个更小的 `task_sorter` 练手，再回到 P01 v0.1。

- [ ] 建立 `task_sorter` 最小 Python 项目
- [ ] 手写按 `created_at` 排序的 FIFO 逻辑
- [ ] 手写按 `priority` 排序的优先级逻辑
- [ ] 手写按 `duration` 排序的 SJF 雏形
- [ ] 为三种排序逻辑各写 1 个 pytest
- [ ] 记录一次运行结果和一次错误排查过程
- [ ] 对照 P01 参考答案，说明自己的实现差在哪里
- [ ] 再进入 M05 R0/R1 最小调度模型复现

> 参考实现新增了 `actual_duration`，执行时不再把 `estimated_duration` 自动当作真实耗时；同时提供 `predicted_sjf` 和 `oracle_sjf` 两个明确入口。本人复现和实验记录必须说明使用了哪一种策略。

## 项目工作台

- [[50_项目产出/P01_Mini_Scheduler/00_项目目标与范围|00 项目目标与范围]]
- [[50_项目产出/P01_Mini_Scheduler/01_需求与任务拆解|01 需求与任务拆解]]
- [[50_项目产出/P01_Mini_Scheduler/02_技术方案|02 技术方案]]
- [[50_项目产出/P01_Mini_Scheduler/03_代码结构与接口|03 代码结构与接口]]
- [[50_项目产出/P01_Mini_Scheduler/08_阶段执行说明_v0.1|08 阶段执行说明 v0.1]]
- [[50_项目产出/P01_Mini_Scheduler/04_实验记录/00_实验索引|04 实验记录索引]]
- [[50_项目产出/P01_Mini_Scheduler/05_问题与失败记录|05 问题与失败记录]]
- [[50_项目产出/P01_Mini_Scheduler/06_README草稿|06 README 草稿]]
- [[50_项目产出/P01_Mini_Scheduler/07_简历表达|07 简历表达]]

## 当前实验入口
### Python 基础阶段

- [[40_实验练习/E01_Python基础练习/E01-01 任务排序脚本|E01-01 任务排序脚本]]
- [[40_实验练习/E01_Python基础练习/E01-02 Python 类实现 Task 和 Worker|E01-02 Python 类实现 Task 和 Worker]]
- [[40_实验练习/E01_Python基础练习/E01-03 pytest 测试调度器|E01-03 pytest 测试调度器]]

### 调度核心阶段
- [[10_学习模块/M05_任务队列与调度/M05_任务队列与调度_章节教材|M05 任务队列与调度章节教材]]
- [[10_学习模块/M05_任务队列与调度/M05_任务队列与调度_复现推进表|M05 任务队列与调度复现推进表]]
- [[40_实验练习/E05_调度实验/E05-R0-R1 学习边界与最小模型复现|E05-R0-R1 学习边界与最小模型复现]]
- [[40_实验练习/E05_调度实验/E05-01 实现 FIFO 调度|E05-01 实现 FIFO 调度]]
- [[40_实验练习/E05_调度实验/E05-02 比较 FIFO 和 Priority|E05-02 比较 FIFO 和 Priority]]
- [[40_实验练习/E05_调度实验/E05-03 高峰负载下的 P95 延迟实验|E05-03 高峰负载下的 P95 延迟实验]]
- [[40_实验练习/E05_调度实验/E05-04 成本感知调度模拟|E05-04 成本感知调度模拟]]

## 实验指标

v0.1 先关注：

- 平均等待时间
- 平均完成时间
- worker 利用率

v0.2 再加入：

- P95 等待时间
- P99 等待时间
- 吞吐
- 队列长度变化

## 后续升级
- 接 FastAPI
- 接 RAG 请求
- 接监控指标
- 接 Docker
- 做 FIFO / Priority / SJF / Cost-aware 对比图
- 把实验记录整理成 README 和简历表达

## 和 M08 的关系

P01 是 M05 调度指标的参考答案和实验样板，M08 会把这些指标迁移到 P03 的真实服务监控中。

对应关系：

| P01/M05 指标 | M08/P03 指标 |
|---|---|
| average waiting time | average_queue_wait_seconds |
| P95/P99 waiting time | p95/p99_queue_wait_seconds |
| worker utilization | worker_utilization |
| queue length | queue_length |
| strategy comparison | 按 scheduler_strategy 分组的压测报告 |

P01 不需要在当前阶段直接改造成完整监控系统。它的作用是帮助理解指标定义、策略对比和实验解释。

## 关联模块

- [[10_学习模块/M00_工具链与计算机基础/M00_工具链与计算机基础_学习地图]]
- [[10_学习模块/M01_Python工程能力/M01_Python工程能力_学习地图]]
- [[10_学习模块/M05_任务队列与调度/M05_任务队列与调度_学习地图]]
- [[10_学习模块/M08_监控压测与可观测性/M08_监控压测与可观测性_学习地图]]
- [[10_学习模块/M08_监控压测与可观测性/M08_监控压测与可观测性_适配教材]]
