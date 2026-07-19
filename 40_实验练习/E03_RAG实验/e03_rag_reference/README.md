# E03 RAG Reference

这是一个 Python 3.13、无网络、确定性的 RAG 教学 reference。它把四个容易被“看起来能跑”
掩盖的工程边界做成可执行证据：检索对比、多格式摄取与生命周期、安全控制流、离线生成输出评测。

## 能验证什么

| 闭环 | 可执行证据 | 边界 |
|---|---|---|
| lexical / vector / hybrid | 同一黄金集、BM25、固定语义特征 cosine 向量、RRF hybrid、Recall@k/MRR/nDCG、逐 query 分类、原始排名 JSON | 固定特征是可审计教学基线，不是学习得到的生产 embedding |
| ingestion and lifecycle | text/HTML/table/Office/PDF fixture、OCR 路由、质量报告、版本/retention、授权状态检查、lineage 级联删除 | PDF/OCR provider、Office 复杂布局和外部存储物理擦除仍有独立边界 |
| authorization | server-owned `Principal`、tenant/ACL 检索前过滤、scope-bound cache | 不替代真实 IdP、数据库 RLS 或策略引擎 |
| indirect injection | system/query/context 隔离、恶意 corpus、污染/越权计数、脱敏审计、确定性 Mock | Mock 不调用模型，不能推出任意真实模型抗注入 |
| generation evaluation | simulated 对抗输出、canary/tool/citation/拒答检查、可复算脱敏 report | 不调用模型；claimed external 输出保持 binding-unverified，不能形成模型安全结论 |

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

## 多格式解析与质量报告

`parse_source()` 先检查 media type、文件签名和可预检的 bytes/ZIP 绝对上限，再按受控 parser 或
provider adapter 提取，并在 adapter 返回边界复核 page/cell/output 上限及全部字段类型。fixture 覆盖
text/Markdown、HTML、CSV/TSV、DOCX、XLSX、born-digital、
mixed PDF 和 OCR 路由。Office parser 只读取 package relationships 实际引用的正文/worksheet，并
精确校验 DOCX `w:document`、XLSX `worksheet` 与 `sst` 根 QName；孤立 XML 不能进入语料。
`defusedxml` 明确禁止 DTD、entity 和 external reference，ZIP CRC/read 异常以及
负数或越界 XLSX shared-string index 都必须变成稳定 `rejected_corrupt`，不能逃出状态机。负数索引
不能交给 Python 下标语义，否则 `-1` 会错误地读取最后一个 shared string。

`text/html` 提取 tokenizer/结构级正文候选，而不是模拟浏览器渲染。固定抑制集合为
`iframe/noembed/noframes/noscript/script/style/template`；存在 boolean `hidden` 属性的元素也会连同完整
子树一起抑制。`hidden="false"` 仍然是启用状态，因为 HTML boolean 属性按“是否存在”解释。若 `hidden`
出现在 `html` 或 `body`，parser 会清空先前候选并持续抑制到 EOF，避免结束容器后的尾随节点被错误地
重新视为正文；该文档级 guard 以 `rejected_blank / blank_after_parse` 优先，触发后不再解释尾随 token。
普通隐藏子树使用完整元素栈而非整数深度：栈内结束标签必须匹配栈顶，栈外孤立隐藏结束标签可忽略；
错序结束、EOF 未闭合，或把非 void 隐藏元素写成 `/>`，统一返回
`rejected_corrupt / malformed_html_hidden_nesting`。

这条 `HTMLParser` 路径是保守语法子集，不实现 HTML5 tree builder，也不计算 inline、class 或外部样式表
中的 CSS，不把 `aria-hidden` 解释为浏览器计算样式。因此它的输出不是浏览器 computed visibility，不能
充当 sanitizer 或反隐藏注入安全边界。需要与真实渲染可见性一致时，应在隔离 worker 中使用受控
sanitizer/renderer，并继续把全部文档文本视为不可信上下文。obsolete `<plaintext>` 会切换专用 HTML
tokenizer state，本轻量路径不尝试用普通元素栈模拟；只要遇到它就稳定返回
`rejected_corrupt / unsupported_html_tokenization_state`。

`application/xhtml+xml` 不复用上述 HTML 路径，而由 `defusedxml` 按 XML QName 和 XHTML namespace
独立严格解析；合法的 `<script/>` 可以自闭合，未配对标签、未声明 entity、DTD/entity 和错误根 QName
均 fail closed。这条独立路径避免把 XML 自闭合、namespace 和 entity 语义误交给容错 HTML tokenizer。

`ParseQualityReport.to_audit_dict()` 只返回 parser/source 版本、locator 指纹、raw/parsed SHA、字符与
page/block/table/row/cell 计数、固定 marker recall、白名单 warning 和状态码，不返回正文、marker、
locator 或 adapter 异常。普通 SHA-256 不是匿名化，生产 telemetry 仍需最小化、访问控制和保留期。

PDF 使用锁定版本的 provider adapter；没有 provider 时统一返回 `rejected_adapter_required`，不从
原始字节猜测是否扫描件。OCR fixture 只验证 adapter 契约和 `requires_ocr` 路由，不验证真实 OCR
精度。图像判断沿页面实际 `INLINE IMAGE`/`Do` 操作递归到嵌套 Form XObject，并显式解引用可能为
indirect object 的 `/Subtype`；资源表中声明但未绘制的
Image/Form 不触发 OCR 或 `partial_page`。缺少自有 resources 的共享 Form 按调用方有效资源上下文分别
遍历，visited key 同时绑定 Form 与 resources，既不漏掉第二个上下文中的 Image，也让循环 Form 图有界
终止。页数上限使用 provider 的真实 page count，不把正文字面量误计为页面。provider 判定的纯图像 PDF 返回 `rejected_ocr_required`；同时含文本和实际绘制图像的
mixed PDF 保留可提取文本，但质量报告必须带 `partial_page`，不能把部分成功伪装成完整提取。当前 adapter 同步运行
在进程内，生产系统必须增加解析 worker 隔离、超时/取消、CPU/内存预算、恶意文件扫描和 parser CVE
处置。

## Ingestion failure matrix

`LifecycleIndex` 对预期失败返回稳定状态，而不是把坏输入静默当成成功：

| 输入/操作 | 状态 |
|---|---|
| 非法 UTF-8 | `rejected_corrupt` |
| media type/签名不匹配或 Office ZIP/CRC 损坏 | `rejected_corrupt` |
| Office XML 含 DTD/entity，或 XLSX shared-string index 为负数/越界 | `rejected_corrupt` |
| HTML 隐藏子树错序/未闭合/非法自闭合、`plaintext` state，或 XHTML XML/namespace 不合法 | `rejected_corrupt` |
| 解析后空白 | `rejected_blank` |
| PDF/OCR adapter 未配置 | `rejected_adapter_required` |
| provider 确认扫描 PDF 或请求 OCR | `rejected_ocr_required` |
| bytes/page/cell/ZIP 超限 | `rejected_resource_limit` |
| 内容哈希重复 | `rejected_duplicate` |
| 导入时已经过期 | `rejected_expired` |
| source version 不单调 | `rejected_version_conflict` |
| 同一 document 的更高版本替换，包括解析正文未变化 | `updated` |
| 另一 document 复用相同解析正文 | `rejected_duplicate` |
| 更高版本删除 | `deleted` |
| 高版本删除先于文档到达 | `delete_not_found`，但仍记录 tombstone |
| retention 到期清理 | `expired` |

每次有效写入、删除或到期清理都会推进 `collection_version` 并清空同 tenant/collection 的检索
缓存。公开状态读取不是无鉴权的 `documents` 属性：调用方必须使用 `active_documents(principal)`；
`artifact_inventory(document_id, principal)` 也先验证 `rag:query`、policy tenant 和有效 ACL，且未授权
调用不能借“存在/不存在”的响应差异枚举文档。`expire_documents(principal, observed_at=...)` 同样强制
Principal。显式 `observed_at` 是为了让测试可复算，但生产适配层必须从服务端时钟注入，不能接受客户端
请求体中的时间，否则调用者可以提前删除或延后保留期。

删除先提交 tombstone，使旧结果立即不可达，再按 raw、parsed、chunk、vector、cache、prompt、output、
citation 顺序失效。中途失败返回 `delete_pending`；同一版本幂等续删后 receipt 的 reference copy 数
归零。pending 期间的新写入或另一删除版本被拒绝，避免新旧 lineage 混合。查询触发 retention 清理
前必须先验证 `rag:query` scope 和 policy tenant，未认证或越界调用不能读取状态、删除文档或清缓存。

并发摄取采用“两次状态检查”：先在 `RLock` 内检查版本/tombstone/pending，再把可能很慢的 provider
adapter 放到锁外执行，最后回到锁内做提交时 CAS 式复查并写入。单调 retention watermark 也在提交点
参与复查，因此较新的到期扫描会让慢摄取稳定返回 `rejected_expired`，不会复活已过期版本。collection
generation 推进时，cache artifact 及依赖它的 prompt/output/citation 后代一并失效，不留下悬空 parent。
`RLock` 只给这个单进程内存状态机提供可重入的
线性化边界，例如 `query()` 可在同一临界区调用 `expire_documents()`；它不证明跨进程、跨数据库事务
或 worker 重启后的线性一致性。

每个 artifact fingerprint 绑定 policy tenant/collection、document、kind、locator、排序去重后的
`parent_fingerprints` 和 payload SHA-256，因此相同 payload 不能换一组父节点后沿用原 fingerprint。
父边还要满足精确契约：vector 恰有一个 parsed 父节点；output 恰有一个 prompt；citation 恰有一个
output 和一个 chunk，且该 chunk 必须属于 output ancestry；prompt 只能引用 active chunk/cache 父节点。
只校验“父节点存在”不够，否则 lineage 可以被合法类型但无关的节点重绑定，删除与引用证明都会失真。

`DeletionReceipt.to_audit_dict()` 是内容无关的审计视图；`LifecycleOutcome` 仍含业务 document ID，
不能整对象写日志。这个内存协议不证明进程重启恢复、分布式原子性或外部对象库/向量库/模型提供方/
备份已物理擦除。

## 安全对抗 fixture

恶意 corpus 同时包含公开 poison 文档和无权限 private poison 文档。代码先做 tenant/ACL 过滤，
再评分；只有授权内容可以进入 prompt。授权但可疑的文字仍然是 `untrusted_retrieved_data`，并以
`untrusted_context_injection_signal` 计数。若下游被篡改而混入无权限 chunk，prompt builder 记录
`unauthorized_context_blocked` 后 fail closed。

审计记录只保留 subject/query/ACL 指纹、长度、计数和事件码，不保存原始 query、正文、user ID、
credential 或恶意 URL。`deterministic_mock_generate()` 固定返回一个不含 context 指令的结果，
且 `tool_calls=()`；它用于证明“检索文本没有被代码分派成工具命令”的控制流边界。

`evaluate_generation_output()` 对 simulated 输出检查 system hash、输入污染、canary 泄漏、空/无证回答、
未知、少于 12 个非空白字符或 quote 不匹配的 citation，以及 tool intent。任意 tool intent 都产生
`tool_intent_requires_runtime_authorization`；名称不在 allowlist 时再增加 `unauthorized_tool_intent`，
allowlist 不授予执行权。报告 v3 只保留指纹、计数和白名单事件码，并固定
`security_claim_status=not_established`；tool intent 始终是惰性数据，不存在执行路径。随库 fixture 全为
`simulated`。外部字段只能登记为
`claimed_external / binding_unverified`，并强制得到 `external_evidence_unbound`；在可信 adapter 从
唯一 raw response 派生规范化字段前，它不可能得到结构检查通过。

## 练习与反例

1. 先诊断词面零信号的 Q5，再把 `top_k` 改成 1，找出 `failure_class` 变化并从 `raw_rankings` 复算原因。
2. 把 cache key 中的 `acl_fingerprint` 暂时删除，运行跨 ACL 负例，解释为什么这是数据泄漏。
3. 注释 `invalidate_collection()`，先缓存后删除，观察 stale hit；恢复实现并让测试重新通过。
4. 在恶意 fixture 增加一种间接注入措辞。先写失败测试，再扩展“信号检测”；说明检测信号为何
   不能代替模型输出对抗评测和工具层授权。
5. 让模拟输出引用不在 prompt 中的 chunk，再把 quote 改成授权 chunk 的原文片段，比较事件码。
6. 在 chunk sink 后注入删除失败，确认旧结果已不可达、新写入被拒，再用同一版本续删。
7. 分别用 `None`、缺 `rag:query` scope 和错误 tenant 调用 `active_documents()`、
   `artifact_inventory()` 与 `expire_documents()`；确认状态、集合版本和缓存计数完全不变。
8. 让一个慢 adapter 停在锁外，同时提交更高版本删除；释放 adapter 后确认摄取在提交复查处得到
   `rejected_version_conflict`，而不是复活旧文档。
9. 用相同 kind/locator/payload 但不同父节点登记 artifact，确认 fingerprint 不同；再分别构造错误
   parent kind、数量和无 ancestry 的 citation，记录稳定拒绝原因。
10. 构造含 DTD/entity 或错误根 QName 的 Office、负数 shared-string index 的 XLSX 和实际绘制图像的
    mixed PDF；前两类应拒绝为 corrupt，后者应接受可见文本并报告 `partial_page`。
11. 让慢 adapter 在到期扫描前开始、扫描后提交，断言 retention watermark 阻止过期版本复活；再让
    collection generation 推进，断言 cache-only prompt 及其 output/citation 后代同时失效。
12. 给文本 PDF 声明但不绘制 Image/Form，并在正文写入 `/Type /Page`；断言不误报 `partial_page`，
    且页数上限由 provider 的真实页数决定。最后移除 provider，确认状态为 adapter-required 而非猜 OCR。
13. 构造 HTML 隐藏标签错序/未闭合、boolean `hidden`、隐藏 `html/body` 后的尾随节点、嵌入 fallback、
    非 void 自闭合、`plaintext` state 与栈外孤立结束标签，再用带 namespace 的 XHTML 对比合法 XML
    自闭合、畸形 XML、错误根 QName 和 DTD/entity；确认两种 MIME 各按自身语义解析，CSS/ARIA
    计算可见性仍明确留在受控 renderer 边界之外。
14. 让同一 PDF Form 在两套继承资源下执行并加入循环引用，再把 Image/Form 的 `/Subtype` 改成
    indirect object；确认第二套资源和间接 subtype 中的 Image 都不漏检，循环遍历仍有界终止。

## 验收

- `python -m pytest -q` 严格收集并通过 154 项测试。
- 三种检索方法的 query ID 集合完全相同；每个 query/method 都有诊断和全候选原始排名。
- hybrid 分数和三个检索指标可只用 JSON 中的字段复算。
- 多格式 failure matrix 的每个 case 都得到 fixture 指定的唯一状态，质量报告不复制输入内容。
- Office DTD/entity、错误根 QName、负 XLSX shared-string index、畸形 HTML 隐藏栈与不安全 XHTML
  被稳定拒绝；固定隐藏标签、boolean `hidden` 子树和隐藏文档容器后的尾随节点不进入正文，
  HTML/XHTML 的非 void 自闭合按各自语义处理，HTML `plaintext` state 明确 fail closed。PDF
  只按实际绘制图像报告 `partial_page`，未使用 XObject 和页数字面量不会误判，共享 Form 的资源上下文
  与循环遍历也有负向覆盖，间接 Image/Form `/Subtype` 会先解引用再路由。
- 同一 document 的同内容高版本得到 `updated`；相同内容的另一 document 仍得到 `rejected_duplicate`。
- 删除 pending 时旧结果不可达；续删后所有 reference lineage copy 为 0，低版本不能复活。
- 所有状态/清理入口先校验 Principal；`observed_at` 只由服务端时钟注入，未授权调用没有状态副作用。
- 慢 adapter 在锁外运行，提交复查使并发 tombstone/retention watermark 胜出；cache 失效同步清理
  lineage 后代。该结论只覆盖单进程 `RLock` 边界。
- artifact fingerprint 绑定父边，vector/output/citation 的 parent kind、数量与 ancestry 负例全部拒绝。
- poison 命中和越权混入都有结构化计数；审计 JSON 不含 fixture 中的秘密、query 或 user ID。
- Mock 没有工具调用，且教材没有把该结果描述成真实模型的普遍抗注入能力。
- simulated generation evaluator 能拒绝泄密、未授权工具、无证回答和伪造引用；外部未绑定输出不能通过。
- generation report 的 `security_claim_status` 必须保持 `not_established`；任何工具意图都要求运行时再授权。

## 权威依据

- [Elasticsearch similarity / BM25](https://www.elastic.co/guide/en/elasticsearch/reference/current/index-modules-similarity.html)
- [NIST TREC](https://trec.nist.gov/)
- [Stanford IR Book: ranked evaluation](https://nlp.stanford.edu/IR-book/html/htmledition/evaluation-of-ranked-retrieval-results-1.html)
- [scikit-learn ndcg_score](https://scikit-learn.org/stable/modules/generated/sklearn.metrics.ndcg_score.html)
- [W3C PROV-O](https://www.w3.org/TR/prov-o/)
- [OpenTelemetry security guidance](https://opentelemetry.io/docs/security/)
- [OWASP LLM Prompt Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)
- [WHATWG HTML: the hidden attribute](https://html.spec.whatwg.org/multipage/interaction.html#the-hidden-attribute)
- [WHATWG HTML syntax: start tags and self-closing flag](https://html.spec.whatwg.org/multipage/syntax.html#start-tags)
- [W3C XHTML Media Types](https://www.w3.org/TR/xhtml-media-types/)

本 reference 不调用真实生成模型、不执行工具、不证明真实 OCR、复杂 Office 布局、parser 沙箱或
分布式删除传播，也不声称替代生产身份、日志、retention 或内容治理系统。
