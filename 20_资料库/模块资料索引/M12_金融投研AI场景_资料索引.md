# M12 金融投研 AI 场景资料索引

## 当前策略

M12 的资料只服务一个目标：

```text
把金融投研文档场景转成 M03 RAG、M04 Agent 和 P03 AI Workload Platform 的应用 workload。
```

资料不是为了系统学习金融学，也不是为了收集投资观点。第一轮只激活能帮助文档获取、RAG 架构、Agent 工作流、引用评估和项目展示的资料。

## 资料闭环

```text
M12 学习地图
-> M12 适配教材
-> M03 RAG
-> M04 Agent
-> P03 AI Workload Platform
-> 80_就业市场与简历
```

## 资料列表
| 资料 | 链接 | 类型 | 状态 | 适合阶段 | 在 M12 中怎么用 | 转化出口 |
|---|---|---|---|---|---|---|
| SEC EDGAR APIs | https://www.sec.gov/search-filings/edgar-application-programming-interfaces | 官方文档 | 查阅 | 金融公开文档来源 | 理解 filings / companyfacts / submissions 等公开数据入口 | 金融文档 metadata |
| SEC EDGAR fair access | https://www.sec.gov/os/accessing-edgar-data | 官方规范 | 必读 | 数据访问边界 | 理解访问频率、User-Agent 和合理使用边界 | 数据来源规范 |
| SEC Beginner's Guide to Financial Statements | https://www.sec.gov/about/reports-publications/investorpubsbegfinstmtguide | 官方投资者教育 | 必读 | 三大报表基础 | 只用来理解 balance sheet、income statement、cash flow 的基本口径 | 金融事实核验 Rubric |
| CFA Institute Financial Statement Analysis | https://www.cfainstitute.org/ | 权威机构资料 | 选读 | 财报术语边界 | 只作为术语和分析框架参考，不写投资结论 | M12 术语表；风险边界 |
| LangChain RAG | https://docs.langchain.com/oss/python/langchain/rag | 官方文档 | 查阅 | 金融 RAG | 复用 document -> chunk -> retrieval -> answer with sources 思路 | E03 / P03 RAG |
| LangGraph Quickstart | https://docs.langchain.com/oss/python/langgraph/quickstart | 官方文档 | 查阅 | 投研 Agent | 参考状态图和可控 workflow 思路 | E04 / P03 Agent |
| LangGraph Agentic RAG | https://docs.langchain.com/oss/python/langgraph/agentic-rag | 官方文档 | 选读 | Agent + RAG | 后续理解 Agent 如何调用检索工具 | 投研 Agent 工作流 |
| Google Cloud RAG reference architectures | https://docs.cloud.google.com/architecture/rag-reference-architectures | 官方架构文档 | 选读 | 企业 RAG 架构 | 参考企业 RAG 的组件拆分和工程边界 | P03 架构表达 |
| Ragas Docs | https://docs.ragas.io/en/stable/ | 官方文档 | 暂缓 | RAG 评估 | 后续评估金融问答 faithfulness / context relevance | E03 / M08 评估扩展 |
| OpenAI Cookbook | https://cookbook.openai.com/ | 官方示例 | 查阅 | embedding / RAG / eval 示例 | 查具体 API、embedding/RAG 或 eval 示例 | 实验实现参考 |

## 教材章节对应
| 教材章节 | 主要资料 | 使用方式 |
|---|---|---|
| 第 1 章：场景边界 | SEC fair access、P03 | 明确公开数据、风险边界和项目定位 |
| 第 2 章：金融文档 RAG | SEC EDGAR APIs、LangChain RAG | 设计 document/chunk/metadata/citation |
| 第 3 章：问答、抽取、风险提示 | SEC Beginner's Guide、Ragas、M03 | 设计 answer + retrieved_sources + risk_note，并检查时间、单位、口径和来源 |
| 第 4 章：投研 Agent | LangGraph Quickstart、Agentic RAG、M04 | 设计固定步骤投研 workflow |
| 第 5 章：P03 workload | P03、M05、M08 | 定义 task_type、metrics、调度意义和 ReviewRecord |
| 第 6 章：展示表达 | 就业市场总览、CFA 术语边界 | 写项目展示和简历表达，不写投资建议或虚构成果 |

## 对应模块

- [[10_学习模块/M12_金融投研AI场景/M12_金融投研AI场景_学习地图|M12 金融投研 AI 场景学习地图]]
- [[10_学习模块/M12_金融投研AI场景/M12_金融投研AI场景_适配教材|M12 金融投研 AI 场景适配教材]]
- [[10_学习模块/M03_RAG工程/M03_RAG工程_适配教材|M03 RAG 工程适配教材]]
- [[10_学习模块/M04_Agent工作流/M04_Agent工作流_适配教材|M04 Agent 工作流适配教材]]
- [[10_学习模块/M08_监控压测与可观测性/M08_监控压测与可观测性_适配教材|M08 监控压测与可观测性适配教材]]

## 对应项目

- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]
- [[80_就业市场与简历/就业市场总览|就业市场总览]]
- [[80_就业市场与简历/简历项目表达/00_索引|简历项目表达索引]]

## 不做

- 不先做金融学系统课。
- 不先读大量投研报告。
- 不先做量化策略、因子、回测平台。
- 不做投资建议。
- 不虚构财报、公告、研报数据。
- 不把模型生成内容包装成事实结论。

## 转化检查

- [ ] 每条资料都能服务 M12 / M03 / M04 / P03。
- [ ] 资料有真实链接。
- [ ] 没有脱离当前路线做资料收藏。
- [ ] 没有把金融观点当作项目成果。
- [ ] 能转成文档 metadata、RAG 实验、Agent 工作流或简历表达。
