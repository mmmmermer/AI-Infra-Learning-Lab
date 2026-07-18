# P02 RAG Agent Service 项目主页

> 状态：`内容 planned / 实现 absent / Reference unverified / 教学 not-assessed / 学习者 not-evaluated`（design-only）。P02 没有独立 reference，也不是当前主项目；现有可执行证据分别位于 E03、E04 和 P03。

## 项目定位

一个企业知识库 RAG + 可控 Agent 工作流服务，用于训练 AI 应用落地、后端 API、权限和文档处理。

## 为什么做

目标是提供真实 AI workload，让后续调度器和监控系统有可执行任务；当前尚未形成 P02 独立实现。

## 功能范围

- 文档上传
- 文档解析
- chunk
- embedding
- 向量检索
- 引用溯源
- Agent 摘要/报告生成
- 任务状态
- server-owned principal、tenant/ACL 检索前过滤和对象授权

## 技术栈

- Python
- FastAPI
- LangChain / LlamaIndex
- LangGraph
- SQLite / PostgreSQL
- Chroma / pgvector
- Redis 可选

## 实验指标

- 检索命中率
- 回答引用覆盖
- 请求延迟
- 失败率
- token 成本

## 当前进度

- [ ] RAG v1
- [ ] Agent v1
- [ ] API 服务化
- [ ] Docker 部署
- [ ] README

## 后续升级

- 接入 P03 调度平台
- 加 RAG 评估集
- 加压测和监控

## 和 M04/P03 的关系

P02 可以作为 RAG + Agent 能力的应用样板，但当前主线以 P03 为准。

M04 第一阶段只要求形成可控 Agent v1：

```text
检索资料
-> 生成草稿
-> 人工确认
-> 生成最终报告
-> 保存 step log / error_type / metrics
```

这些 Agent 请求后续要接入 P03，成为可以排队、调度、记录和监控的 AgentTask。不要在 P02 阶段提前扩展 AutoGPT、多 Agent 协作或复杂自动规划。

## 关联

- [[M03_RAG工程_学习地图]]
- [[M04_Agent工作流_学习地图]]
- [[M04_Agent工作流_适配教材]]
- [[M02_后端API与服务化_学习地图]]
- [[P03_AI_Workload_Platform 项目主页]]
