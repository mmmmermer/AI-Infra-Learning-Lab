# M04 Agent 工作流资料索引

## 当前策略

Agent 资料只服务于可控工作流，不追求复杂多 Agent。第一轮资料用于理解固定工作流和评测边界；
P03 `AgentTask`、`step_logs`、`approval_status` 是 post-v0.3.1 / vNext planned，不是当前 reference。

## 资料闭环

```text
M04 学习地图
-> M04 适配教材
-> 本资料索引按需查官方资料
-> E04 Agent 实验
-> P03 planned Agent workload
```

## 资料列表
| 资料 | 链接 | 类型 | 状态 | 适合阶段 | 在 M04 中怎么用 | 转化出口 |
|---|---|---|---|---|---|---|
| LangGraph Agentic RAG | https://docs.langchain.com/oss/python/langgraph/agentic-rag | 官方文档 | 必读 | Agentic RAG | 看可控流程和检索决策，不照搬复杂实现 | E04-01 |
| LangGraph Quickstart | https://docs.langchain.com/oss/python/langgraph/quickstart | 官方文档 | 必读 | 状态图入门 | 理解 state、node、edge | 第 3-4 章 |
| LangChain Tool Calling | https://docs.langchain.com/oss/python/langchain/tools | 官方文档 | 必读 | 工具调用 | 查工具定义、参数和调用方式 | 第 2 章 |
| OpenAI Function Calling | https://developers.openai.com/api/docs/guides/function-calling | 官方文档 | 必读 | 工具 schema / 结构化工具调用 | 学习工具定义、参数 schema、函数调用结果回填，不照搬平台细节 | 第 10 章；ToolRegistry |
| OpenAI Agents SDK Running Agents | https://openai.github.io/openai-agents-python/running_agents/ | 官方文档 | 必读 | Agent loop / runner | 对照 agent loop、tool calls、final output、max_turns，转成最小 runtime 伪代码 | 第 10 章；E04 Runtime 实验 |
| OpenAI Agents SDK Sessions | https://openai.github.io/openai-agents-python/sessions/ | 官方文档 | 查阅 | session / conversation state | 学习会话隔离和多轮上下文管理，只吸收 session_id / history 边界 | 第 10 章；P03 session 字段 |
| OpenAI Compaction | https://developers.openai.com/api/docs/guides/compaction | 官方文档 | 查阅 | context 压缩 | 学习长上下文压缩思路，转成基础摘要策略，不做复杂记忆系统 | 第 10 章；context_summary |
| Anthropic Tool Use | https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview | 官方文档 | 查阅 | tool_use / tool_result 循环 | 对照工具调用回合、工具结果回填和错误处理，帮助理解跨厂商共同模式 | 第 10 章；工具调用解析 |
| LangGraph Persistence | https://docs.langchain.com/oss/python/langgraph/persistence | 官方文档 | 查阅 | checkpoint / store | 学习线程级状态、长期存储和故障恢复边界，不直接引入 LangGraph 依赖 | 第 10 章；M06 状态持久化 |
| LangGraph Memory Overview | https://docs.langchain.com/oss/python/langgraph/memory | 官方文档 | 查阅 | short-term / long-term memory | 区分会话内短期记忆和跨会话长期记忆，避免把所有历史都塞进 prompt | 第 10 章；memory 召回 |
| LangGraph Interrupts | https://docs.langchain.com/oss/python/langgraph/interrupts | 官方文档 | 查阅 | human-in-the-loop / resume | 学习暂停、人工确认、恢复执行的工程边界 | 第 6 章；第 10 章 |
| LangChain RAG | https://docs.langchain.com/oss/python/langchain/rag | 官方文档 | 查阅 | RAG 工具化 | 回看 RAG 如何作为 Agent 工具 | M03/M04 连接 |
| OpenAI Evaluate agent workflows | https://developers.openai.com/api/docs/guides/agent-evals | 官方文档 | 查阅 | Agent 评测 | 学习从 trace、tool calls、handoffs 和 guardrails 判断 Agent 过程质量 | P03 planned `step_logs`；planned EvaluationTask |
| OpenAI Agents SDK tracing | https://openai.github.io/openai-agents-python/tracing/ | 官方文档 | 查阅 | 轨迹记录 | 对照 span/trace 的记录思想，作为 P03 planned step log 的设计参考 | E04-02；M08 step duration |
| LangSmith trajectory evaluations | https://docs.langchain.com/langsmith/trajectory-evals | 官方文档 | 查阅 | 工具轨迹评测 | 判断 expected_tool / actual_tool、步骤顺序和工具参数是否合理 | E04-01/E04-02；planned ReviewRecord |
| LangSmith evaluation concepts | https://docs.langchain.com/langsmith/evaluation-concepts | 官方文档 | 查阅 | 评测概念 | 理解 dataset、evaluator、experiment 的边界，只取最小概念 | M11 Rubric；planned EvaluationTask |
| Stanford CS224N | https://web.stanford.edu/class/cs224n/ | 高校课程 | 暂缓 | NLP/QA/LLM 背景 | 后续补理论背景，不作为 M04 第一轮重点 | 进阶学习 |

## 教材章节对应
| 教材章节 | 主要资料 | 使用方式 |
|---|---|---|
| 第 1 章：为什么 Agent 必须可控 | LangGraph Agentic RAG | 理解工作流和状态，不做自动智能体幻想 |
| 第 2 章：工具调用 | LangChain Tool Calling、LangSmith trajectory evaluations | 查工具定义、输入输出和工具选择是否合理 |
| 第 3-4 章：状态和固定工作流 | LangGraph Quickstart、OpenAI Agents SDK tracing | 理解 state、node、edge、trace 和 step log |
| 第 5-6 章：失败和人工确认 | P03 项目需求、OpenAI Evaluate agent workflows | 按工程需求设计 retry、timeout、review_status，不扩展复杂平台 |
| 第 7-8 章：调度和监控 | M05/M08 教材 | 连接队列、指标和日志 |
| 第 9 章：安全边界 | LangChain 工具调用资料 + RAG prompt injection 常识 | 只做第一层工具白名单 |
| 第 10 章：最小 Agent Runtime | OpenAI Running Agents、OpenAI Function Calling、Anthropic Tool Use、LangGraph Persistence/Memory/Interrupts | 抽取 agent loop、tool registry、session/context/memory、async/busy state 和 trace/test，转成 P03 最小实现边界 |

## 对应实验

- [[40_实验练习/E04_Agent实验/E04_Agent实验_索引|E04 Agent 实验索引]]
- [[40_实验练习/E04_Agent实验/E04-01 工具调用最小实验|E04-01 工具调用最小实验]]
- [[40_实验练习/E04_Agent实验/E04-02 多步骤 Agent 状态流转实验|E04-02 多步骤 Agent 状态流转实验]]
- [[40_实验练习/E04_Agent实验/E04-03 人工确认与失败处理实验|E04-03 人工确认与失败处理实验]]
- 二阶段候选：E04-04 最小 Agent Runtime、E04-05 Session 隔离、E04-06 Context/Memory、E04-07 异步工具与 busy state。正式补实验页前不作为已完成实验。

## 对应项目

- [[50_项目产出/P02_RAG_Agent_Service/P02_RAG_Agent_Service 项目主页]]
- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页]]

## 和相关模块的关系

- M03：RAG 检索能力可以成为 Agent 的工具。
- M05：planned AgentTask 后续需要队列、优先级、超时和成本控制。
- M06：planned Agent 状态、step log、approval 后续需要持久化。
- M08：planned Agent step duration、tool error、approval wait 后续需要监控。

## 不做

- 不先做复杂多 Agent 协作。
- 不先追求自动规划系统。
- 不把 Agent 当作主线，主线仍是 workload 和调度。
- 不做 Agent 论文大综述。
- 不做强化学习 Agent。

## 转化检查

- [ ] 每条必读资料能转化成教材章节、E04 实验或 P03 planned AgentTask 字段。
- [ ] M04 没有脱离 M03 RAG 和 P03 workload 主线。
- [ ] 资料没有引导到 AutoGPT、多 Agent 或复杂规划发散。
