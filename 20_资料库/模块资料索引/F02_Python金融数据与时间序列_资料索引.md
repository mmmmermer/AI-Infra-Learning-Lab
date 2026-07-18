# F02 Python 金融数据与时间序列资料索引

## 当前策略

F02 的资料只服务一个目标：

```text
用 Python 把金融时间序列处理成可复现、可计算、可记录的实验数据。
```

第一轮只激活 pandas 和少量数据源文档，不做预测模型和复杂回测。

## 资料闭环

```text
F02 学习地图
-> GF02 时间序列清洗和指标计算
-> Q01 金融数据分析实验
-> F03 风险指标
-> P03 risk_metric_task 输入
```

## 资料列表

| 资料 | 链接 | 类型 | 状态 | 适合阶段 | 在 F02 中怎么用 | 转化出口 |
|---|---|---|---|---|---|---|
| pandas time series user guide | https://pandas.pydata.org/docs/user_guide/timeseries.html | 官方文档 | 必读 | 时间索引和频率处理 | 学 DatetimeIndex、频率、resample、日期偏移 | GF02-01 |
| pandas window operations | https://pandas.pydata.org/docs/user_guide/window.html | 官方文档 | 必读 | rolling 指标 | 学 rolling mean、rolling std、窗口统计 | GF02-02 |
| statsmodels Time Series Analysis | https://www.statsmodels.org/stable/tsa.html | 官方文档 | 查阅 | 时间序列统计 | 第一轮只查分解、ACF/PACF 等基础入口 | GF02-03 |
| FRED API | https://fred.stlouisfed.org/docs/api/fred/ | 官方数据源文档 | 查阅 | 宏观和利率数据 | 获取公开宏观或利率时间序列 | Q01 |
| Nasdaq Data Link docs | https://docs.data.nasdaq.com/ | 官方数据源文档 | 候选 | 金融数据 API | 了解数据 API 和 Python 调用方式，注意数据权限 | Q01 |
| Alpha Vantage docs | https://www.alphavantage.co/documentation/ | 官方数据源文档 | 候选 | 股票时间序列 API | 作为小样本股票数据候选，注意 key 和调用限制 | GF02/Q01 |
| SEC EDGAR APIs | https://www.sec.gov/search-filings/edgar-application-programming-interfaces | 官方文档 | 选读 | 财报文档和结构化数据 | 用于和 M12 文档场景交叉，不作为 F02 第一入口 | M12/X01 |

## 暂时不读

- 深度学习时间序列教程。
- 股价预测文章。
- 策略回测框架教程。
- 高频 tick 数据处理。
- 数据来源不明的 CSV。

## 第一轮只读范围

第一轮只看能马上支撑数据清洗和指标计算的内容：

- pandas time series：DatetimeIndex、date offsets、frequency、resample、asfreq。
- pandas window operations：rolling mean、rolling std、expanding 的基本用法。
- statsmodels TSA：只选时间序列分解或基础诊断入口，不做预测模型。
- FRED / Alpha Vantage / Nasdaq Data Link：只看如何获取小样本时间序列，以及 API key、频率限制和数据权限说明。
- SEC EDGAR：只作为 M12 交叉资料，不作为 F02 第一批时间序列数据主入口。

读完要能写一个可复现的数据处理脚本，不要求搭建数据平台。

## 教材和实验转化

| 转化目标 | 使用资料 | 转化方式 |
|---|---|---|
| GF02-01 金融时间序列清洗 | pandas time series | 处理日期、频率、缺失值、字段对齐 |
| GF02-02 rolling volatility 与 drawdown | pandas window operations | 计算滚动波动和最大回撤 |
| GF02-03 简单时间序列分解 | statsmodels TSA | 选做趋势/季节性/残差观察 |
| Q01 数据分析实验 | FRED / Alpha Vantage / Nasdaq Data Link | 提供可复现数据来源 |
| P03 risk_metric_task | pandas / 数据源文档 | 定义输入字段和处理流程 |

## 转化检查

- [ ] 每条资料都能服务清洗、计算、记录或数据来源。
- [ ] 数据源限制已经标注。
- [ ] 不把数据图表解释成投资建议。
- [ ] 不提前做预测模型。
- [ ] 能转成 Q01 的数据处理记录。
