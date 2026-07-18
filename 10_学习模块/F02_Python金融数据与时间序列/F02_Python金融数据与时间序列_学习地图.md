# F02 Python 金融数据与时间序列学习地图

## 怎么读这个模块

把 F02 当成金融工程支线的第一个工程练习模块。

阅读主线是：从公开数据源拿到价格或指标数据，把日期、频率、缺失值、复权、收益率、rolling window 和基础统计处理清楚，再把结果交给 F03 风险计算、Q01 实验和 P03 task。

第一轮只做清洗、计算、可视化和记录，不做股价预测。

## 在总路线中的位置

F02 是金融工程支线从概念进入代码的入口。

它连接：

```text
F00 金融市场和数据口径
-> F01 概率统计基础
-> F02 Python 金融时间序列处理
-> F03 风险指标和组合计算
-> Q01 金融数据分析与风险指标实验
-> P03 risk_metric_task
```

它和 AI Infra 主线的连接点是：

```text
金融数据处理脚本
-> API 或 task 输入
-> M06 持久化
-> M08 指标记录
-> P03 workload
```

## 要解决的问题

- 金融时间序列为什么不能只当普通表格处理？
- 日期索引、交易日、频率、缺失值为什么重要？
- adjusted close 和普通 close 有什么区别？
- 如何计算简单收益率、对数收益率、rolling volatility 和 drawdown？
- 如何让一个 notebook 或脚本的结果可复现？
- 为什么金融数据要记录 point-in-time、字段版本、复权方式和数据血缘？
- 金融数据任务未来如何变成 P03 的输入？

## 学习目标

- [ ] 能用 pandas 读取并整理带日期的金融数据。
- [ ] 能处理时间索引、频率、缺失值和数据对齐。
- [ ] 能计算收益率、对数收益率、rolling volatility、最大回撤。
- [ ] 能画出价格、收益率、波动率和回撤曲线。
- [ ] 能记录数据来源、字段含义、时间范围和处理步骤。
- [ ] 能记录数据版本、复权方式、缺失比例、字段血缘和是否 point-in-time。
- [ ] 能设计 `risk_metric_task` 的最小输入字段。

## 核心内容

| 内容 | 学到什么程度 | 对应出口 |
|---|---|---|
| pandas 时间索引 | 能使用 DatetimeIndex 和频率处理 | GF02-01 |
| 数据清洗 | 能处理缺失值、重复日期、字段对齐 | Q01 |
| 数据版本和血缘 | 能记录来源、下载时间、字段版本、复权方式 | Q01 / P03 |
| point-in-time 数据 | 理解为什么不能使用未来修订后的数据做历史判断 | F06/F07 |
| 收益率计算 | 能计算 pct_change 和 log return | GF02-02 |
| rolling window | 能计算 rolling mean / volatility | GF02-02 |
| 回撤 | 能计算 peak、drawdown、max drawdown | F03 |
| 可视化和记录 | 能画图并记录数据口径 | Q01 报告 |
| task 输入 | 能把数据处理任务抽象成输入输出 | P03 |

## 对应资料

- [[20_资料库/模块资料索引/F02_Python金融数据与时间序列_资料索引|F02 Python 金融数据与时间序列资料索引]]
- [pandas time series user guide](https://pandas.pydata.org/docs/user_guide/timeseries.html)
- [pandas window operations](https://pandas.pydata.org/docs/user_guide/window.html)
- [statsmodels Time Series Analysis](https://www.statsmodels.org/stable/tsa.html)
- [FRED API](https://fred.stlouisfed.org/docs/api/fred/)
- [Nasdaq Data Link docs](https://docs.data.nasdaq.com/)
- [Alpha Vantage docs](https://www.alphavantage.co/documentation/)

## 对应知识卡片

- [[DatetimeIndex]]
- [[时间序列]]
- [[收益率]]
- [[对数收益率]]
- [[rolling window]]
- [[最大回撤]]
- [[数据复现]]
- [[risk_metric_task]]

## 对应实验

当前 GF02-01 和 GF02-02 已补具体实验页，GF02-03 仍先保留候选：

- [[40_实验练习/GF00_金融工程第一阶段实验/GF00_金融工程第一阶段实验_索引|GF00 金融工程第一阶段实验索引]]
- [[40_实验练习/GF00_金融工程第一阶段实验/GF02-01 金融时间序列清洗|GF02-01 金融时间序列清洗]]
- [[40_实验练习/GF00_金融工程第一阶段实验/GF02-02 rolling volatility 与最大回撤|GF02-02 rolling volatility 与最大回撤]]
- GF02-03 数据质量与时点口径记录。

第一轮实验应避免：

- 使用不可复现数据。
- 只画图不记录字段口径。
- 混用 raw close 和 adjusted close。
- 使用未来修订后的数据却不标注 point-in-time 限制。
- 直接做预测模型。

## 第一轮学习产物

学完 F02 后，至少要能交出一个可复现的小数据处理结果：

1. 一个数据说明块：写清数据来源、字段、时间范围、频率、缺失值处理方式。
2. 一个最小 Python 流程：读取数据、设置日期索引、清洗缺失值、计算收益率、rolling volatility 和 max drawdown。
3. 一张输出表或图：展示 price、return、rolling volatility、drawdown，并说明这些图只用于学习和风险观察。
4. 一个 P03 输入草图：把结果抽象成 `symbol`、`date_range`、`price_series`、`returns`、`metrics`。
5. 一份数据版本记录：包含 `source_url`、`download_time`、`adjusted_or_raw`、`missing_ratio`、`field_version`、`point_in_time_note`。

合格标准不是图画得漂亮，而是别人可以根据记录复现同样的数据处理步骤。

## 对应项目

- Q01 金融数据分析与风险指标实验：未来项目候选，当前不建工作台。
- [[10_学习模块/F00_金融市场与资产基础/F00_金融市场与资产基础_学习地图|F00 金融市场与资产基础]]
- [[10_学习模块/F01_概率统计与数学基础/F01_概率统计与数学基础_学习地图|F01 概率统计与数学基础]]
- [[10_学习模块/F03_投资组合与风险管理/F03_投资组合与风险管理_学习地图|F03 投资组合与风险管理]]
- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]

## 推荐学习顺序

1. 先读 F00，知道数据字段和资产类别。
2. 读 pandas time series user guide，重点看时间索引、频率、resample。
3. 读 pandas window operations，重点看 rolling。
4. 选择一个小型公开或自造测试数据集，计算收益率和 rolling volatility。
5. 记录数据来源、字段、时间范围和处理步骤。
6. 把计算结果整理成 F03 可用的 returns 表。

## 检查标准

- [ ] 能把日期列转成 DatetimeIndex。
- [ ] 能说明数据频率和交易日缺失对结果的影响。
- [ ] 能计算简单收益率和对数收益率。
- [ ] 能计算 rolling volatility 和最大回撤。
- [ ] 能用图表解释价格、收益率、波动和回撤。
- [ ] 能写出数据处理记录，说明数据从哪里来、怎么清洗、输出什么。
- [ ] 能说明 point-in-time 数据和事后修订数据的区别。
- [ ] 能解释为什么字段版本和复权方式会影响后续回测/模型结果。
- [ ] 能设计 `risk_metric_task` 的输入：symbol、date_range、price_series。

## 暂时不深入

- 不做股价预测。
- 不做深度学习时间序列。
- 不做高频 tick 数据。
- 不做复杂回测框架。
- 不直接使用无法说明来源的数据。
- 不把图表走势解释成投资建议。
