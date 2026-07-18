# E03 RAG Reference

这是一个 Python 3.13、无网络、确定性的 RAG 教学 reference。它把三个容易被“看起来能跑”
掩盖的工程边界做成可执行证据：检索对比、文档生命周期、安全控制流。

## 能验证什么

| 闭环 | 可执行证据 | 边界 |
|---|---|---|
| lexical / vector / hybrid | 同一黄金集、BM25、固定语义特征 cosine 向量、RRF hybrid、Recall@k/MRR/nDCG、逐 query 分类、原始排名 JSON | 固定特征是可审计教学基线，不是学习得到的生产 embedding |
| ingestion lifecycle | UTF-8 损坏、空白、重复、过期、版本冲突、更新、删除、过期清理 | 内存状态机，不代表外部对象存储和向量库已经完成分布式删除 |
| authorization | server-owned `Principal`、tenant/ACL 检索前过滤、scope-bound cache | 不替代真实 IdP、数据库 RLS 或策略引擎 |
| indirect injection | system/query/context 结构隔离、恶意 corpus、污染/越权计数、脱敏审计、确定性 Mock generation | Mock 不调用模型，不能推出任意真实模型抗注入 |

查询请求只接受 `query`、`collection_id`、`top_k`。`tenant_id`、用户身份和有效 ACL 由服务端
独立传入。导入请求也不能自报 tenant、collection、ACL 或 provenance；这些字段由可信策略赋值。

## 运行

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
python examples\run_evaluation.py --output artifacts\retrieval_comparison.json
```

评估 JSON 不保存 corpus 正文，也不混入不可复算的 wall-clock latency。每条候选保存：

```text
query_id + method + final_rank + chunk_id + document_id
lexical_score + vector_score + lexical_rank + vector_rank + final_score
```

其中 hybrid 使用固定 `rrf_k=60`：

```text
hybrid_score = 1 / (60 + lexical_rank) + 1 / (60 + vector_rank)
```

因此可以只从原始排名重新计算最终排序和 Recall@k/MRR/nDCG。`corpus_fingerprint` 绑定
chunk metadata 和正文哈希，`query_set_fingerprint` 绑定 query、ACL 和 relevance judgement；
报告本身不复制正文或 query。测试 fixture 位于 `tests/fixtures/`。

Q5 是有意保留的释义诊断：lexical 对相关文档的词面信号为 0，固定语义特征 vector 把它排到第一；
等权 RRF 遇到 component 名次互换时可能同分，稳定 `chunk_id` 次级排序仍让 hybrid 排在第二。
这个反例说明 hybrid 不是自动优于每个 component，必须看逐 query 排名。
如果所有 component score 都为 0，即使稳定 `chunk_id` 次级排序碰巧命中黄金文档，诊断仍为
`zero_retrieval_signal`；偶然的 Recall@k 命中不能冒充方法具有检索信号。

## Ingestion failure matrix

`LifecycleIndex` 对预期失败返回稳定状态，而不是把坏输入静默当成成功：

| 输入/操作 | 状态 |
|---|---|
| 非法 UTF-8 | `rejected_corrupt` |
| 解析后空白 | `rejected_blank` |
| 内容哈希重复 | `rejected_duplicate` |
| 导入时已经过期 | `rejected_expired` |
| source version 不单调 | `rejected_version_conflict` |
| 更高版本替换 | `updated` |
| 更高版本删除 | `deleted` |
| 高版本删除先于文档到达 | `delete_not_found`，但仍记录 tombstone |
| retention 到期清理 | `expired` |

每次有效写入、删除或到期清理都会推进 `collection_version` 并清空同 tenant/collection 的检索
缓存。删除即使暂时找不到 active 文档，也会保留版本 tombstone，使随后乱序到达的低版本不能把
文档复活；删除后的第一次查询必须 cache miss，且结果中不能出现已删除文档。查询触发 retention
清理前必须先验证 `rag:query` scope 和 policy tenant，未认证或越界调用不能改变索引与缓存状态。

## 安全对抗 fixture

恶意 corpus 同时包含公开 poison 文档和无权限 private poison 文档。代码先做 tenant/ACL 过滤，
再评分；只有授权内容可以进入 prompt。授权但可疑的文字仍然是 `untrusted_retrieved_data`，并以
`untrusted_context_injection_signal` 计数。若下游被篡改而混入无权限 chunk，prompt builder 记录
`unauthorized_context_blocked` 后 fail closed。

审计记录只保留 subject/query/ACL 指纹、长度、计数和事件码，不保存原始 query、正文、user ID、
credential 或恶意 URL。`deterministic_mock_generate()` 固定返回一个不含 context 指令的结果，
且 `tool_calls=()`；它用于证明“检索文本没有被代码分派成工具命令”的控制流边界。

## 练习与反例

1. 先诊断词面零信号的 Q5，再把 `top_k` 改成 1，找出 `failure_class` 变化并从 `raw_rankings` 复算原因。
2. 把 cache key 中的 `acl_fingerprint` 暂时删除，运行跨 ACL 负例，解释为什么这是数据泄漏。
3. 注释 `invalidate_collection()`，先缓存后删除，观察 stale hit；恢复实现并让测试重新通过。
4. 在恶意 fixture 增加一种间接注入措辞。先写失败测试，再扩展“信号检测”；说明检测信号为何
   不能代替模型输出对抗评测和工具层授权。

## 验收

- `python -m pytest -q` 全部通过。
- 三种检索方法的 query ID 集合完全相同；每个 query/method 都有诊断和全候选原始排名。
- hybrid 分数和三个检索指标可只用 JSON 中的字段复算。
- failure matrix 的每个 case 都得到 fixture 指定的唯一状态。
- 删除后旧缓存条目为 0，第一次查询不是 cache hit，已删除文档不能被检索或低版本复活。
- poison 命中和越权混入都有结构化计数；审计 JSON 不含 fixture 中的秘密、query 或 user ID。
- Mock 没有工具调用，且教材没有把该结果描述成真实模型的普遍抗注入能力。

## 权威依据

- [Elasticsearch similarity / BM25](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-modules-similarity.html)
- [NIST TREC](https://trec.nist.gov/)
- [Stanford IR Book: ranked evaluation](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html)
- [scikit-learn ndcg_score](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.ndcg_score.html)
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
- [OpenTelemetry security guidance](https://opentelemetry.io/docs/security/)
- [OWASP LLM Prompt Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)

本 reference 不调用真实生成模型、不执行工具、不测分布式向量库删除传播，也不声称替代生产身份、
日志、retention 或内容治理系统。
