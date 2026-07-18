# 金融工程 AI/计算机高结合领域与岗位能力地图

## 本文定位

本文用于回答一个问题：

```text
金融工程里哪些方向最值得和 AI、机器学习、计算机工程结合学习？
```

它不是简历成果，也不是岗位承诺。它用于重构 F 系列第二主线，让金融工程学习不变成金融概念台账，而是能落到数据、代码、模型、实验、系统和 P03 workload。

## 依据来源

路线参考来自金融工程顶级项目与真实岗位要求：

| 来源 | 链接 | 使用方式 |
|---|---|---|
| Carnegie Mellon MSCF | https://www.cmu.edu/mscf/academics/curriculum/index.html | 校准金融工程对 finance、math、statistics、computer science 的交叉要求 |
| Columbia MS Financial Engineering | https://ieor.columbia.edu/msfe-curriculum | 校准 optimization、stochastic models、AI in finance、programming、risk 的模块边界 |
| NYU Tandon MS Financial Engineering | https://engineering.nyu.edu/academics/programs/financial-engineering-ms | 校准金融工程核心课、实验、capstone 和职业方向 |
| MIT 18.642 Mathematics with Applications in Finance | https://ocw.mit.edu/courses/18-642-topics-in-mathematics-with-applications-in-finance-fall-2024/ | 校准数学、概率、数值方法与金融应用连接 |
| Jane Street Quantitative Researcher | https://www.janestreet.com/join-jane-street/position/6302325002/ | 校准概率、编程、研究表达和问题解决能力 |
| Two Sigma Quantitative Researcher: Machine Learning | https://careers.twosigma.com/careers/JobDetail/New-York-Ny-United-States-Quantitative-Researcher-Machine-Learning/13766 | 校准 ML、统计建模、数据分析和研究能力 |
| Citadel Machine Learning Researcher | https://www.citadelsecurities.com/careers/details/machine-learning-researcher-phd-graduate-us/ | 校准 ML research、金融市场、工程实现要求 |

## 高结合领域排序

### 1. 金融数据工程与时间序列

为什么重要：

```text
金融任务首先是数据任务。
没有时间索引、字段口径、缺失值、复权、频率和数据来源记录，
后续风险、回测、ML、RAG 都会失真。
```

对应模块：

- F00 金融市场与资产基础。
- F02 Python 金融数据与时间序列。
- M01 Python 工程能力。
- M06 数据库缓存与异步任务。

岗位能力：

- Python / pandas。
- SQL 和数据清洗。
- 时间序列处理。
- 数据质量检查。
- 数据来源和口径说明。

项目出口：

- Q01 金融数据分析与风险指标实验。
- P03 `risk_metric_task` 输入准备。

### 2. 风险指标与投资组合计算

为什么重要：

```text
风险指标是金融工程最容易工程化、可解释、可验证的入口。
它比直接做预测模型更适合基础薄弱阶段。
```

对应模块：

- F01 概率统计与数学基础。
- F03 投资组合与风险管理。
- F08 金融工程任务与 AI Workload 接口。

岗位能力：

- 概率统计。
- covariance / correlation。
- volatility / drawdown / VaR。
- optimization。
- 指标解释和报告。

项目出口：

- Q01 风险指标实验。
- Q02 投资组合与风险管理实验。
- P03 `portfolio_task`。

### 3. 量化研究与回测工程

为什么重要：

```text
回测工程把金融分析变成可复现实验。
它和软件工程、实验设计、数据泄漏检查高度相关。
```

对应模块：

- F02 Python 金融数据与时间序列。
- F06 量化研究与回测工程。
- M11 科研方法与实验设计。
- M08 监控压测与可观测性。

岗位能力：

- signal / position / return。
- train/test split。
- transaction cost。
- look-ahead bias。
- 实验记录。

项目出口：

- Q04 最小回测框架。
- P03 `backtest_task`。

### 4. 金融机器学习与模型风险

为什么重要：

```text
金融 ML 的核心不是模型越复杂越好，
而是标签、特征、时间切分、baseline、泄漏检查和失败分析。
```

对应模块：

- F07 金融机器学习与模型风险。
- M11 科研方法与实验设计。
- M08 指标和评测。

岗位能力：

- machine learning。
- statistics。
- baseline。
- model evaluation。
- model risk。
- error analysis。

项目出口：

- Q04 模型验证部分。
- P03 `model_risk_task` / `evaluation_task`。

### 5. 衍生品定价与数值计算

为什么重要：

```text
定价任务天然是计算任务：
公式、参数、模拟次数、随机种子、误差和运行时间都可以记录。
```

对应模块：

- F04 衍生品定价与随机过程导论。
- F05 固定收益与利率基础。
- M05 调度。
- M08 指标。

岗位能力：

- numerical methods。
- Monte Carlo。
- model assumptions。
- Python / C++ 基础。
- 性能和误差分析。

项目出口：

- Q03 期权定价与 Monte Carlo 实验。
- P03 `pricing_task`。

### 6. 金融 AI 文档理解与事实核验

为什么重要：

```text
这是 F 系列和 M12/M03/M04 的交叉点。
金融文档 AI 不是只问答，还要核对来源、时间、单位、口径和风险提示。
```

对应模块：

- M03 RAG 工程。
- M04 Agent 工作流。
- M12 金融投研 AI 场景。
- F00/F03/F07。

岗位能力：

- RAG。
- citation。
- financial statement understanding。
- AI output evaluation。
- rubric / human review。

项目出口：

- X01 金融文档 RAG 与事实核验。
- P03 `finance_rag_query` / `evaluation_task`。

## 对 F 系列的重构结论

F 系列应该作为第二主线建设，但顺序不能平均用力。

推荐强度：

| 模块 | 强度 | 原因 |
|---|---|---|
| F00 | 基础必修 | 提供金融语言和数据口径 |
| F01 | 基础必修 | 提供统计、矩阵、优化语言 |
| F02 | 强工程必修 | 和 Python/数据工程/P03 高度连接 |
| F03 | 强项目必修 | 风险指标和组合实验最适合落地 |
| F04 | 进阶重要 | 定价与数值计算，适合后续 Q03 |
| F05 | 进阶重要 | 利率和固定收益补金融完整性 |
| F06 | 强工程必修 | 回测工程和实验设计高度相关 |
| F07 | 强 AI 交叉 | 金融 ML 和模型风险是岗位高频能力 |
| F08 | 交叉接口必修 | 连接 F 系列和 P03 |

## 当前执行建议

现在可以补齐 F04-F08 学习地图和资料索引，因为这是第二主线骨架。

但真正学习顺序仍建议：

```text
M00/M01/P01/M05 起步
-> F00/F01/F02/F03 第一轮金融基础
-> F06/F07 金融工程与 AI/ML 交叉
-> F04/F05 定价与利率进阶
-> F08 接入 P03
```

这样金融工程不会变成空中楼阁，也不会抢走当前最需要补的 Python 工程地基。

## 表达边界

当前可表达：

```text
正在建设金融工程与 AI/计算机交叉学习路线，重点覆盖金融时间序列、风险指标、回测工程、金融机器学习、模型风险和 workload 化。
```

不能表达：

- 已掌握量化研究。
- 已完成金融 ML 项目。
- 已完成回测平台。
- 已具备投资策略能力。

只有亲手完成实验和项目后，才可以写成成果。
