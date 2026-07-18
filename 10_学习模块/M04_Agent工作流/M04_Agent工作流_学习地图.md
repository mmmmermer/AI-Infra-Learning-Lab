# M04 Agent 工作流学习地图

## 怎么读这个模块

把 M04 当成“多步骤 AI 任务如何变得可控”的教程，不要当成 Agent 热词合集。

第一轮只关注固定工作流：调用工具、记录状态、处理失败、等待人工确认、写 step_logs，并能判断每一步工具调用是否合理。只要能把一个 Agent 请求变成 `AgentTask` 并进入 P03 队列，就达到了本模块的第一阶段目标。

第二阶段再进入最小 Agent Runtime：理解 agent loop、tool registry、LLM 输出解析、session 隔离、context/memory、异步工具和 busy state。它是进阶内容，不替代第一阶段的可控工作流。

开放式规划、多 Agent 协作、论文综述先放下；它们不是当前主线。

## 在总路线中的位置

M04 负责把普通 RAG 请求升级成更复杂但仍然可控的 Agent workload。

它服务 P03 的 Agent v1：让 Agent 请求具备工具调用、状态记录、失败处理、人工确认和日志记录，并能进入 M05 的队列、优先级、超时和成本控制。

主线是：

```text
M03 RAG 能力
-> M04 可控 Agent 工作流
-> AgentTask
-> M05 调度
-> M06 状态持久化
-> M08 监控压测
-> P03 planned Agent workload
```

## 要解决的问题

- 如何让 AI 调用工具完成任务？
- 如何记录状态、失败和人工确认？
- 如何让 Agent 适合企业系统，而不是一次性 demo？
- Agent 和普通 RAG 请求有什么区别？
- Agent 为什么更需要队列、超时、优先级和成本控制？

## 学习目标

- [ ] 能解释 Agent 和普通 RAG 的区别。
- [ ] 能设计受控工具调用，而不是开放式自动执行。
- [ ] 能设计 AgentState、AgentStep 和 AgentTask。
- [ ] 能画出固定工作流：检索 -> 草稿 -> 人工确认 -> 最终报告。
- [ ] 能处理工具失败、超时、重试、权限拒绝和人工拒绝。
- [ ] 能说明 AgentTask 如何进入 M05 队列和 P03 worker。
- [ ] 能记录每一步日志，为 M08 监控提供数据。

## 核心内容

| 内容 | 学到什么程度 | 对应出口 |
|---|---|---|
| tool calling | 会定义工具输入、输出、错误类型 | E04-01 |
| state | 会记录 current_step、status、artifacts | E04-03 |
| fixed workflow | 会设计固定步骤，不做无限自动规划 | E04-02 |
| human-in-the-loop | 会设计 approve/reject 节点 | P03 planned Agent v1 |
| failure handling | 会处理 timeout、empty_result、permission_denied | E04-03 |
| logs/metrics | 会记录 step log 和 tool error | M08 |
| trajectory review | 会判断工具调用顺序和每步选择是否合理 | P03 planned EvaluationTask |
| scheduling fields | 会设计 priority、max_steps、estimated_cost | M05 |
| prompt injection 基础 | 会设置工具白名单和权限边界 | P03 |
| Agent Runtime 二阶段 | 会解释 agent loop、session、context、memory、async tool、busy state | P03 post-v0.3.1 / vNext planned（当前未实现 AgentTask、step_logs 或 Runtime） |

## 对应资料

- [[20_资料库/模块资料索引/M04_Agent工作流_资料索引|M04 Agent 工作流资料索引]]
- [LangGraph Agentic RAG](https://docs.langchain.com/oss/python/langgraph/agentic-rag)
- [LangGraph Quickstart](https://docs.langchain.com/oss/python/langgraph/quickstart)
- [LangChain Tool Calling](https://docs.langchain.com/oss/python/langchain/tools)
- [OpenAI Evaluate agent workflows](https://developers.openai.com/api/docs/guides/agent-evals)
- [OpenAI Agents SDK tracing](https://openai.github.io/openai-agents-python/tracing/)
- [OpenAI Function Calling](https://developers.openai.com/api/docs/guides/function-calling)
- [OpenAI Agents SDK Running Agents](https://openai.github.io/openai-agents-python/running_agents/)
- [Anthropic Tool Use](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangGraph Memory](https://docs.langchain.com/oss/python/langgraph/memory)
- [LangSmith trajectory evaluations](https://docs.langchain.com/langsmith/trajectory-evals)
- [LangSmith evaluation concepts](https://docs.langchain.com/langsmith/evaluation-concepts)

## 对应知识卡片（后续候选）

以下是后续可补的概念卡片候选，不表示当前已经全部创建完成。

- `Agent`
- `tool calling`
- `状态机`
- `human-in-the-loop`
- `prompt injection`
- `AgentTask`

## 对应实验

- [[40_实验练习/E04_Agent实验/E04_Agent实验_索引|E04 Agent 实验索引]]
- [[40_实验练习/E04_Agent实验/E04-01 工具调用最小实验|E04-01 工具调用最小实验]]
- [[40_实验练习/E04_Agent实验/E04-02 多步骤 Agent 状态流转实验|E04-02 多步骤 Agent 状态流转实验]]
- [[40_实验练习/E04_Agent实验/E04-03 人工确认与失败处理实验|E04-03 人工确认与失败处理实验]]
- [[40_实验练习/E04_Agent实验/E04-04 最小 Agent Runtime 实现|E04-04 最小 Agent Runtime 实现]]
- [[40_实验练习/E04_Agent实验/E04-05 Session 隔离与多轮追问|E04-05 Session 隔离与多轮追问]]
- [[40_实验练习/E04_Agent实验/E04-06 Context 压缩与 memory 召回|E04-06 Context 压缩与 memory 召回]]
- [[40_实验练习/E04_Agent实验/E04-07 异步工具与 busy state|E04-07 异步工具与 busy state]]

E04-04 到 E04-07 是二阶段 Runtime 初版实验页，用于承接第 10 章，不代表已经亲手完成。

## 对应项目

- [[50_项目产出/P02_RAG_Agent_Service/P02_RAG_Agent_Service 项目主页|P02 RAG Agent Service 项目主页]]
- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform 项目主页]]

## 推荐学习顺序

1. 读 [[10_学习模块/M04_Agent工作流/M04_Agent工作流_适配教材|M04 适配教材]] 第 1 章，明确 Agent 和 RAG 的区别以及防发散边界。
2. 读第 2-4 章，完成工具调用、状态模型和固定工作流。
3. 读第 5-6 章，补失败处理、重试、超时和人工确认。
4. 读第 7-8 章，理解未来如何把 planned AgentTask 接到 M05 调度和 M08 监控。
5. 读第 9 章，建立工具白名单和 prompt injection 基础边界。
6. 完成 E04-01/E04-02/E04-03，并把 Agent v1 接到 P03。
7. 二阶段再读第 10 章，按 E04-04/E04-05/E04-06/E04-07 准备最小 Runtime、session、context/memory、异步工具实验；这些是 P03 post-v0.3.1 / vNext 的 planned 字段，不属于当前 reference。

## 检查标准

- [ ] 能做一个固定流程 Agent。
- [ ] 能解释为什么 Agent 需要状态。
- [ ] 能记录每一步执行结果。
- [ ] 能判断 `expected_tool` 和 `actual_tool` 是否一致。
- [ ] 能记录 `tool_call_error`、`step_review_note` 和 `review_status`。
- [ ] 能设计人工确认节点。
- [ ] 能说明 AgentTask 如何接入 M05/P03。
- [ ] 二阶段能解释最小 Agent Runtime 的 loop、tool registry、session、context、memory 和 busy state。

## 暂时不深入

- 不做 AutoGPT 式无限循环。
- 不做复杂多 Agent 协作。
- 不做强化学习 Agent。
- 不做复杂规划算法。
- 不做 Agent 论文大综述。
- 不把 LangGraph/LangChain 全量功能都学一遍。
- 不把 Agent Runtime 二阶段写成完整框架源码课。
