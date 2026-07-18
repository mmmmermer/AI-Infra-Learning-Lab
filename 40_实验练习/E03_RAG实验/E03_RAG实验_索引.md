# E03 RAG 实验索引

## 当前状态

检索 reference：`内容 content-reviewed / 实现 executable / Reference verified / 教学 partial / 归属 reference / 学习者 not-evaluated`。

生成与完整 RAG 服务：`内容 draft / 实现 partial / Reference unverified / 教学 partial / 归属 reference / 学习者 not-evaluated`。

可执行参考位于 `e03_rag_reference/`，固定使用：

- 自带小型 corpus。
- 独立黄金 query/evidence 集。
- `rank-bm25==0.2.2`。
- 固定字符 bigram tokenizer。
- `perf_counter_ns` 实际计时。
- recall@k 和 reciprocal rank。
- server-owned Principal 与严格业务请求 schema。
- tenant / collection / permission group 检索前过滤。
- tenant、ACL 指纹/版本、collection/version 绑定缓存键。
- 可信 collection policy 负责 tenant、ACL 与来源版本，上传请求不能自报安全 metadata。
- 恶意指令 fixture 只能进入 `untrusted_retrieved_data` context，不能改写 system role。
- 审计记录只保留主体/查询哈希、长度和计数，不保存原始 query、文档文本或 user ID。

2026-07-13 在 Python 3.13 下 21 个 E03 测试通过。除原有检索质量检查外，负向测试覆盖
伪造身份字段、缺少认证/scope、无权限 chunk 不进入 BM25 打分、跨 tenant 检索和跨
tenant/ACL/ACL-version 缓存隔离，以及伪造导入 metadata、间接提示注入角色隔离和日志脱敏。

2026-07-11 已将同一权限前置过滤原则接入当前 P03 v0.3.1：server-owned principal、
tenant/user/permission task snapshot、owner-scoped task query、BM25 前 tenant +
permission prefilter、零相关候选拒绝和持久化 source metadata。P03 27 个单元/契约测试及五服务 Compose
通过。该记录仍属于 reference，不是学习者实验完成。

## 实验入口

| 实验 | 当前可验证内容 | 尚未完成 |
|---|---|---|
| [[E03-01 chunk 大小对检索效果的影响]] | chunk 数、recall@k、MRR、真实 retrieval_ms | 真实 embedding 与大语料 |
| [[E03-02 top-k 对回答质量和延迟的影响]] | retrieval top-k 和检索质量 | 真实 generation、citation precision/recall |
| [[E03-03 metadata 权限过滤实验]] | E03 server principal、严格请求、可信导入 metadata、tenant/ACL 前置过滤、scope-bound cache、prompt 角色隔离与脱敏审计负测；P03 task/worker 权限前置过滤 | 向量数据库原生过滤集成、生产身份提供方、真实生成行为/citation/删除传播验证 |

## 运行

```powershell
cd e03_rag_reference
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
python examples\run_evaluation.py
```

参考结果不等于学习者完成，也不能证明任意 chunk/top-k 配置对真实 RAG 系统一定更优。
该 reference 不执行真实生成、rerank 或 citation evaluation。21 个测试能证明无权限内容不进入
候选、结构化 prompt 包和审计记录，并证明恶意文本不能改写代码中的 system role；它不能证明
任意模型都会忽略间接指令。真实生成输出、citation、工具副作用与删除传播仍须下游验收。
