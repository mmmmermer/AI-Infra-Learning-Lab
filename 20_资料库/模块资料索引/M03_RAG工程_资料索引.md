# M03 RAG 工程资料索引

## 当前策略

M03 的资料只服务一个主目标：把 RAG 请求变成 P03 中真实、可记录、可调度、可评估的 AI workload。

第一轮资料使用顺序是：

```text
M03 学习地图
-> M03 适配教材
-> 本资料索引按需查官方资料
-> E03 小实验
-> P03 RAG v1 功能设计
```

资料索引不是阅读台账。每条资料必须转化成教材理解、实验步骤、项目字段或检查标准；不能只收藏链接，也不能把外部资料大段搬进教材。

## 第一轮资料表
| 资料 | 链接 | 类型 | 状态 | 适合阶段 | 在 M03 中怎么用 | 转化出口 |
|---|---|---|---|---|---|---|
| LangChain RAG 官方文档 | https://docs.langchain.com/oss/python/langchain/rag | 官方文档 | 必读 | 最小 RAG 流程 | 对照 indexing、retrieval、generation 的最小链路 | 教材第 1、3、4、5 章；E03-01/E03-02 |
| LlamaIndex RAG 官方文档 | https://developers.llamaindex.ai/python/framework/understanding/rag/ | 官方文档 | 必读 | 概念对照 | 对照 Document、Index、Retriever、Query Engine 的职责边界 | 教材第 2、4、5 章；P03 RAG Worker 边界 |
| Google Cloud RAG reference architectures | https://docs.cloud.google.com/architecture/rag-reference-architectures | 官方文档 | 选读 | 工程架构 | 看企业 RAG 的组件分层、数据流和服务边界 | 教材第 8 章；P03 架构说明 |
| OpenAI Cookbook | https://developers.openai.com/cookbook | 官方示例库 | 查阅 | 代码示例 | 按需查 embedding、file search、RAG 示例；注意部分旧示例可能标注 archived | E03 实验参考；P03 最小实现参考 |
| scikit-learn cosine_similarity | https://scikit-learn.org/stable/modules/generated/sklearn.metrics.pairwise.cosine_similarity.html | 官方 API 文档 | 查阅 | cosine 公式与边界 | 核对归一化点积定义；零向量由教材显式拒绝 | 教材第 4 章；E03-02 |
| Stanford IR Book: vector space model | https://nlp.stanford.edu/IR-book/html/htmledition/the-vector-space-model-for-scoring-1.html | 公开大学教材 | 选读 | 向量检索排序 | 理解 query/document 向量相似度与排序，不替代 embedding 模型评估 | 教材第 4 章；E03-02 |
| LangSmith Evaluate a RAG application | https://docs.langchain.com/langsmith/evaluate-rag-tutorial | 官方文档 | 查阅 | RAG 质量评估 | 学习如何组织问题、参考答案、检索结果和模型回答，不照搬完整平台 | E03-02；P03 planned EvaluationTask |
| Ragas metrics | https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/ | 官方文档 | 查阅 | RAG 指标边界 | 只吸收 faithfulness、context precision、context recall 的思想，转成小样本人评表 | M03 第 6 章；M11 Rubric |
| Ragas Faithfulness | https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/ | 官方文档 | 查阅 | 引用支撑判断 | 帮助理解回答是否被上下文支撑，第一轮用人工核验，不做自动化大评测 | `has_citation_support`；`unsupported_claim_count` |

## 和教材章节的对应关系
| 教材章节 | 优先资料 | 使用方式 |
|---|---|---|
| 第 1 章：RAG 为什么是 workload 起点 | LangChain RAG、Google Cloud RAG 架构 | 只看 RAG 数据流和组件边界 |
| 第 2 章：文档进入系统 | LlamaIndex RAG、LangChain RAG | 对照 Document / metadata 的工程含义 |
| 第 3 章：chunk 策略 | LangChain RAG | 查 splitter 思路，不照搬所有框架模板 |
| 第 4 章：embedding 和向量检索 | scikit-learn cosine、Stanford IR Book、OpenAI Cookbook、LlamaIndex RAG | 先核对 cosine/向量排序，再查 embedding / retrieval 示例和 top-k |
| 第 5 章：回答与引用 | LangChain RAG、OpenAI Cookbook | 学习如何保留 retrieved docs 和 sources |
| 第 6 章：评估与失败处理 | LangSmith RAG eval、Ragas metrics、Google Cloud RAG 架构 | 抽取 faithfulness、context precision、citation support、unsupported claims，不做完整评测平台 |
| 第 7 章：metadata 权限过滤 | OpenAI Cookbook、Google Cloud RAG 架构 | 只转化成最小 permission_group 实验 |
| 第 8 章：接入 P03 | Google Cloud RAG 架构、LangChain RAG | 转化成 RagTask、Worker、metrics、EvaluationTask 设计 |

## 对应实验

- [[40_实验练习/E03_RAG实验/E03_RAG实验_索引|E03 RAG 实验索引]]
- [[E03-01 chunk 大小对检索效果的影响]]：主要对应 LangChain 的 splitting / indexing 思路。
- [[E03-02 top-k 对回答质量和延迟的影响]]：主要对应 retrieval 和固定黄金集评估。
- [[E03-03 metadata 权限过滤实验]]：主要对应 metadata filtering 和企业权限边界。

## 对应项目

- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 AI Workload Platform]]
- [[50_项目产出/P02_RAG_Agent_Service/P02_RAG_Agent_Service 项目主页|P02 RAG Agent Service]]

## 本轮不激活的资料方向

- 不激活复杂 Agent/RAG 混合框架教程。
- 不激活向量数据库横向选型长文。
- 不激活完整企业知识库产品方案。
- 不激活微调 embedding、训练 reranker、复杂自动评测框架。
- 不把 archived 示例当作当前最佳实践，只作为理解流程的参考。

## 资料转化检查

- [ ] 每条必读资料至少对应一个教材章节。
- [ ] 每条必读资料至少能转化为一个 E03 实验观察点。
- [ ] P03 能接收资料转化出的字段、接口或 metrics。
- [ ] 没有把资料索引写成泛泛链接台账。
- [ ] 没有虚构资料来源。
