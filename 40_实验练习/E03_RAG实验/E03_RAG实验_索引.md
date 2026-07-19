# E03 RAG 实验索引

## 当前状态

检索、多格式摄取、生命周期和离线生成评估 reference：`内容 content-reviewed / 实现 executable / Reference verified / 教学 partial / 归属 reference / 学习者 not-evaluated`。

真实模型生成与完整 RAG 服务：`内容 draft / 实现 partial / Reference unverified / 教学 partial / 归属 reference / 学习者 not-evaluated`。

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
- 多格式 ingestion fixture 覆盖 text/HTML/table/Office/PDF provider/OCR 路由、损坏、空白、资源上限、
  重复、过期、版本、更新和删除；HTML 与 XHTML 分别走受限 tokenizer 和安全 XML，Office 校验包
  关系、根 QName 与安全 XML，PDF 按实际内容流识别 inline image、嵌套 Form XObject 和间接
  `/Subtype`，并生成不含正文的解析质量报告。
- 写入/retention/删除推进 collection version；单调 retention watermark 与提交时 CAS 阻止慢解析复活
  已过期或已删除版本；cache 失效同步清理依赖它的 prompt/output/citation 后代，tombstone-first 删除
  支持中途失败、幂等续删并阻止 pending 期间混入新版本。
- 恶意 corpus 只能进入 `untrusted_retrieved_data` context，不能改写 system role。
- 污染和越权混入有结构化计数；越权 context 在 prompt 边界 fail closed。
- 审计记录只保留主体/查询哈希、长度、计数和事件码，不保存原始 query、文档文本或 user ID。
- 确定性 Mock 验证控制流；离线 generation evaluator 检查 simulated 输出泄密、工具意图、引用与拒答，
  但不调用真实模型，claimed external 输出在 raw/normalized 未绑定时固定为 unverified。

2026-07-19 在 Python 3.13 下 154 个 E03 测试通过。除原有检索质量检查外，负向测试覆盖
伪造身份字段、缺少认证/scope、无权限 chunk 不进入 BM25 打分、跨 tenant 检索和跨
tenant/ACL/ACL-version 缓存隔离，以及伪造导入 metadata、ingestion failure matrix、删除/retention
缓存失效、间接提示注入角色隔离、越权 prompt 阻断和日志脱敏。新增边界还覆盖：状态读取和直接
retention 的鉴权先于副作用、服务端拥有 `observed_at`、同内容高版本更新、慢 adapter 锁外解析与提交
复查；Office DTD/entity/根 QName、负 XLSX shared-string index、HTML/XHTML 隐藏语义与结构边界、
mixed/inline/nested-image PDF、共享 Form 继承资源/循环图、间接 subtype、未使用 XObject 和页数字面量；
以及 cache 后代失效、parent-bound lineage fingerprint、父节点
kind/cardinality/ancestry 约束。

2026-07-11 已将同一权限前置过滤原则接入当前 P03 v0.3.1：server-owned principal、
tenant/user/permission task snapshot、owner-scoped task query、BM25 前 tenant +
permission prefilter、零相关候选拒绝和持久化 source metadata。P03 27 个单元/契约测试及五服务 Compose
通过。该记录仍属于 reference，不是学习者实验完成。

## 实验入口

| 实验 | 当前可验证内容 | 尚未完成 |
|---|---|---|
| [[E03-01 chunk 大小对检索效果的影响]] | chunk 数、同一黄金集三路检索、Recall@k/MRR/nDCG、原始排名 | 真实 embedding 与大语料 |
| [[E03-02 top-k 对回答质量和延迟的影响]] | retrieval top-k、逐 query 失败分类和可复算证据 | 真实 generation、逐引用 entailment 与 citation precision/recall |
| [[E03-03 metadata 权限过滤实验]] | server principal、严格请求、可信 metadata、tenant/ACL 前置过滤、scope-bound cache、多格式 parsing quality、lineage 删除、恶意 corpus、prompt 隔离与 simulated generation evaluator | 生产 IdP/解析沙箱、真实 OCR、可信真实模型 adapter/对抗运行、外部存储删除传播 |

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
该 reference 不执行真实模型、生产 rerank 或逐引用 entailment 评估。154 个测试能验证这个单进程、
确定性实现中：无权限内容不进入候选，授权失败不触发状态副作用，并发 tombstone 不被慢解析提交覆盖，
删除后旧缓存和 lineage copy 不可达，cache 失效不留下悬空 lineage；它也能拒绝 simulated 输出中的泄密、未授权工具、无证回答与
伪造引用。测试不能证明任意真实模型都会忽略间接指令，也不能证明外部存储已经物理删除。可信真实输出
绑定、模型对抗、工具副作用与跨存储删除传播仍须下游验收。字段说明、反例、练习、验收和来源见
`e03_rag_reference/README.md`。
