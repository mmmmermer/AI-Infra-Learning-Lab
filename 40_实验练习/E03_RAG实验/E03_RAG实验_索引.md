# E03 RAG 实验索引

## 当前状态

检索 reference：`内容 content-reviewed / 实现 executable / Reference verified / 教学 partial / 归属 reference / 学习者 not-evaluated`。

生成与完整 RAG 服务：`内容 draft / 实现 partial / Reference unverified / 教学 partial / 归属 reference / 学习者 not-evaluated`。

可执行参考位于 `e03_rag_reference/`，固定使用：

- 自带小型 corpus。
- 独立黄金 query/evidence 集，并由 lexical/vector/hybrid 共用。
- `rank-bm25==0.2.2` lexical、固定语义特征 cosine vector 与 RRF hybrid。
- 固定字符 bigram tokenizer。
- `perf_counter_ns` 实际计时。
- Recall@k、MRR、nDCG、逐 query 失败分类和可复算原始排名 JSON。
- server-owned Principal 与严格业务请求 schema。
- tenant / collection / permission group 检索前过滤。
- tenant、ACL 指纹/版本、collection/version 绑定缓存键。
- 可信 collection policy 负责 tenant、ACL 与来源版本，上传请求不能自报安全 metadata。
- ingestion failure matrix 覆盖损坏、空白、重复、过期、版本、更新和删除状态。
- 写入/retention/删除推进 collection version，并级联清空 collection cache；tombstone 阻止低版本复活。
- 恶意 corpus 只能进入 `untrusted_retrieved_data` context，不能改写 system role。
- 污染和越权混入有结构化计数；越权 context 在 prompt 边界 fail closed。
- 审计记录只保留主体/查询哈希、长度、计数和事件码，不保存原始 query、文档文本或 user ID。
- 确定性 Mock generation 验证控制流不执行 context 指令，但不代表真实模型抗注入。

2026-07-18 在 Python 3.13 下 32 个 E03 测试通过。除原有检索质量检查外，负向测试覆盖
伪造身份字段、缺少认证/scope、无权限 chunk 不进入 BM25 打分、跨 tenant 检索和跨
tenant/ACL/ACL-version 缓存隔离，以及伪造导入 metadata、ingestion failure matrix、删除/retention
缓存失效、间接提示注入角色隔离、越权 prompt 阻断和日志脱敏。

2026-07-11 已将同一权限前置过滤原则接入当前 P03 v0.3.1：server-owned principal、
tenant/user/permission task snapshot、owner-scoped task query、BM25 前 tenant +
permission prefilter、零相关候选拒绝和持久化 source metadata。P03 27 个单元/契约测试及五服务 Compose
通过。该记录仍属于 reference，不是学习者实验完成。

## 实验入口

| 实验 | 当前可验证内容 | 尚未完成 |
|---|---|---|
| [[E03-01 chunk 大小对检索效果的影响]] | chunk 数、同一黄金集三路检索、Recall@k/MRR/nDCG、原始排名 | 真实 embedding 与大语料 |
| [[E03-02 top-k 对回答质量和延迟的影响]] | retrieval top-k、逐 query 失败分类和可复算证据 | 真实 generation、citation precision/recall |
| [[E03-03 metadata 权限过滤实验]] | server principal、严格请求、可信 metadata、tenant/ACL 前置过滤、scope-bound cache、ingestion 生命周期、恶意 corpus、prompt 隔离、Mock 控制流与脱敏审计 | 向量数据库原生过滤、生产 IdP、真实模型/工具对抗评测、分布式删除传播 |

## 运行

```powershell
cd e03_rag_reference
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
python examples\run_evaluation.py --output artifacts\retrieval_comparison.json
```

参考结果不等于学习者完成，也不能证明任意 chunk/top-k 配置对真实 RAG 系统一定更优。
该 reference 不执行真实模型、生产 rerank 或 citation evaluation。35 个测试能证明无权限内容不进入
候选、删除后旧缓存失效、结构化 prompt 包和审计记录，并证明 Mock 控制流不会把恶意 context 当成
工具命令；它不能证明任意模型都会忽略间接指令。真实生成输出、citation、工具副作用与跨存储删除
传播仍须下游验收。字段说明、反例、练习、验收和来源见 `e03_rag_reference/README.md`。
