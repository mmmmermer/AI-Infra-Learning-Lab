# F08 金融工程任务与 AI Workload 接口资料索引

## 当前策略

F08 不收新的金融理论资料，主要使用本库已有 AI Infra 模块、P03 项目工作台，以及这些模块背后的官方/权威文档，把金融任务工程化。

```text
金融计算任务
-> task_type
-> input/output
-> status
-> metrics
-> review record
```

## 资料闭环

```text
F08 学习地图
-> GF08 task 建模实验
-> P03 API 与数据契约
-> M05/M06/M08 执行和监控
-> M11 实验报告
```

## 资料列表

| 资料 | 链接 | 类型 | 状态 | 在 F08 中怎么用 | 转化出口 |
|---|---|---|---|---|---|
| P03 项目主页 | [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页]] | 本库项目 | 必读 | 承接金融 workload 的主项目入口 | X02/P03 |
| P03 API 与数据契约 | [[50_项目产出/P03_AI_Workload_Platform/03_API与数据契约]] | 本库项目 | 必读 | 对齐 task、status、result、metrics 字段 | GF08 |
| M05 任务队列与调度 | [[10_学习模块/M05_任务队列与调度/M05_任务队列与调度_学习地图]] | 本库模块 | 必读 | 理解金融 task 为什么要排队和调度 | GF08-02 |
| M06 数据库缓存与异步任务 | [[10_学习模块/M06_数据库缓存与异步任务/M06_数据库缓存与异步任务_学习地图]] | 本库模块 | 必读 | 理解任务状态持久化和 worker 回写 | GF08 |
| M08 监控压测与可观测性 | [[10_学习模块/M08_监控压测与可观测性/M08_监控压测与可观测性_学习地图]] | 本库模块 | 必读 | 记录 latency、runtime、queue_wait、error_rate | GF08 |
| M11 科研方法与实验设计 | [[10_学习模块/M11_科研方法与实验设计/M11_科研方法与实验设计_学习地图]] | 本库模块 | 选读 | 设计 baseline、变量、指标和报告 | Q/X |
| AI 输出质量评测能力线 | [[00_路线总控/AI输出质量评测能力线_系统重构方案]] | 本库路线 | 选读 | 连接 Rubric、ReviewRecord 和质量评测 | EvaluationTask |

## 第一轮只读范围

- P03 task/status/result/metrics。
- M05 队列、worker、调度。
- M06 状态持久化。
- M08 performance metrics。
- M11 记录结构。

## 暂时不读

- 生产级交易系统。
- 完整标注平台。
- 企业级权限合规。
- 商业金融数据接入。

## 转化检查

- [ ] 每个金融 task 都能写出 input/output/metrics。
- [ ] 能连接 P03 状态字段。
- [ ] 能区分性能指标、金融结果指标和质量评测指标。
- [ ] 不把候选 task 写成已完成项目。
