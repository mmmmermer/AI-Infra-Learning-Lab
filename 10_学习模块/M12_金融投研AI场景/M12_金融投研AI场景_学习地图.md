# M12 金融投研 AI 场景学习地图

## 怎么读这个模块

把 M12 当成“给 P03 找一个有差异化的文档场景”，不要当成金融学课程。

阅读主线是：公开金融/合规文档进入系统，形成 metadata 和 chunk，RAG 返回带来源的回答，Agent 执行固定投研工作流，P03 记录任务状态、指标和质量评测结果。

第一轮只学文档、证据、引用、风险提示和 workload 建模；不做投资建议，不写虚构投研结论。

## 在总路线中的位置

M12 是当前路线的场景化差异模块。

它不负责系统学习金融学，也不负责生成投资建议。它的职责是把金融投研中的文档密集型任务，转成 P03 AI Workload Platform 可以承接的 RAG / Agent 请求。

主线是：

```text
公告 / 研报 / 财报 / 会议纪要
-> 文档解析、chunk、metadata、检索、引用
-> 金融问答 / 信息抽取 / 风险提示 / 报告生成
-> Agent 多步骤投研工作流
-> P03 队列、调度、worker、metrics
-> 项目展示和简历差异化
```

## 要解决的问题

- 金融投研场景为什么适合做 RAG / Agent？
- 公告、研报、财报这类长文档如何进入 RAG 链路？
- 金融回答为什么必须强调证据引用和风险提示？
- 金融回答里的数字、单位、时间口径和来源如何核验？
- Agent 如何执行多步骤投研工作流，而不是一次性生成报告？
- 金融请求如何作为真实 AI workload 接入 P03？
- 如何把“金融背景 + AI Infra 项目”写成有差异的项目表达？

## 学习目标

- [ ] 能说明金融投研 AI 场景和普通知识库问答的区别。
- [ ] 能把一份公告、财报或研报抽象成 document / chunk / metadata。
- [ ] 能设计金融 RAG 的检索、引用和风险提示边界。
- [ ] 能设计一个可控的投研 Agent 工作流。
- [ ] 能把金融 RAG / Agent 请求建模成 P03 的 workload。
- [ ] 能说明为什么不做投资建议、不虚构数据、不生成无证据结论。
- [ ] 能写出项目展示和简历表达中的场景化亮点。

## 核心内容

| 内容 | 学到什么程度 | 对应出口 |
|---|---|---|
| 金融文档类型 | 理解公告、财报、研报、新闻、会议纪要的结构差异 | 文档 metadata 设计 |
| 金融文档 RAG | 会设计 chunk、检索、引用、权限和来源字段 | M03 / P03 RAG v1 |
| 信息抽取 | 会抽取公司、指标、期间、风险因素、事件 | 项目功能 |
| 投研问答 | 能回答“基于哪些材料得出什么结论” | RAG answer + retrieved_sources |
| 风险提示 | 能区分事实、模型生成、待核验内容 | 输出安全边界 |
| 金融事实核验 | 能检查时间、单位、币种、期间、来源是否一致 | ReviewRecord / Rubric |
| Agent 工作流 | 能拆成检索、抽取、汇总、核验、生成报告 | M04 / P03 planned Agent v1 |
| workload 建模 | 能记录 task_type、document_type、latency、token、citation | P03 调度和监控 |
| 简历表达 | 能体现 AI 工程能力和金融场景理解 | 80_就业市场与简历 |

## 对应资料

- [[20_资料库/模块资料索引/M12_金融投研AI场景_资料索引|M12 金融投研 AI 场景资料索引]]
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC EDGAR fair access](https://www.sec.gov/os/accessing-edgar-data)
- [SEC Beginner's Guide to Financial Statements](https://www.sec.gov/investor/pubs/begfinstmtguide.htm)
- [LangChain RAG](https://docs.langchain.com/oss/python/langchain/rag)
- [LangGraph Quickstart](https://docs.langchain.com/oss/python/langgraph/quickstart)
- [Google Cloud RAG reference architectures](https://docs.cloud.google.com/architecture/rag-reference-architectures)
- [Ragas Docs](https://docs.ragas.io/en/stable/)

## 对应知识卡片

- [[金融文档RAG]]
- [[证据引用]]
- [[财报解析]]
- [[公告解析]]
- [[投研Agent]]
- [[风险提示]]
- [[金融数据权限]]
- [[AI workload]]

## 对应实验

第一版不新增正式 E12 实验目录，先复用已有实验主线：

- [[40_实验练习/E03_RAG实验/E03_RAG实验_索引|E03 RAG 实验索引]]
- [[40_实验练习/E04_Agent实验/E04_Agent实验_索引|E04 Agent 实验索引]]
- [[40_实验练习/E08_监控压测实验/E08_监控压测实验_索引|E08 监控压测实验索引]]

建议后续在 E03/E04/P03 中加入金融样例任务：

- 金融公告 chunk 与 citation 实验
- 财报指标抽取与问答实验
- 投研报告生成 Agent 工作流实验
- 金融 RAG 请求压测与指标记录

## 对应项目

- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]
- [[10_学习模块/M03_RAG工程/M03_RAG工程_学习地图|M03 RAG 工程]]
- [[10_学习模块/M04_Agent工作流/M04_Agent工作流_学习地图|M04 Agent 工作流]]
- [[10_学习模块/M08_监控压测与可观测性/M08_监控压测与可观测性_学习地图|M08 监控压测与可观测性]]
- [[80_就业市场与简历/就业市场总览|就业市场总览]]
- [[80_就业市场与简历/简历项目表达/00_索引|简历项目表达索引]]

## 推荐学习顺序

1. 先读 [[M12_金融投研AI场景_适配教材|M12 适配教材]] 第 1 章，理解场景边界。
2. 读第 2 章，学习金融文档如何进入 RAG。
3. 读第 3 章，学习金融问答、引用和风险提示。
4. 读第 4 章，学习投研 Agent 工作流。
5. 读第 5 章，把金融请求接到 P03 workload。
6. 读第 6 章，形成项目展示和简历表达。

## 检查标准

- [ ] 能解释金融投研 AI 场景不是投资建议系统。
- [ ] 能设计金融文档的 chunk 和 metadata。
- [ ] 能说明 answer 必须带 sources、date、document_type、risk_note。
- [ ] 能用 Rubric 检查金融回答中的来源、时间、单位、口径和 unsupported claims。
- [ ] 能画出一个投研 Agent 工作流。
- [ ] 能把金融 RAG / Agent 请求接到 P03 的 Queue / Worker / Metrics。
- [ ] 能说清当前数据和输出的限制。
- [ ] 能写出一段不夸大的简历项目表达。

## 暂时不深入

- 不系统学习金融学教材。
- 不做量化交易策略。
- 不做投资建议。
- 不虚构财报、研报、公告数据。
- 不声称模型输出可以替代投研判断。
- 不做复杂合规系统。
- 不做完整金融终端或商业投研平台。
