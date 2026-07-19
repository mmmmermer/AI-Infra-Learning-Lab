# AI Infra Learning Lab

面向自学的 AI Infra、RAG、Agent、云原生资源调度、科研方法与金融工程学习库。仓库把路线、
教材、实验、项目和研究证据放在同一套可追踪结构中，目标是让概念能够落到代码、失败案例和
验收标准，而不是只收集链接。

> 当前状态（2026-07-19）：Wave 0 的 10 项 P0 阻断任务已完成；更广的 14 项 P0 为
> `completed` 13、`in-progress` 1。110 项优化矩阵为 `completed` 28、`in-progress` 5、
> `blocked` 2、`planned` 75。仓库仍是持续建设的结构化教材，
> 不应被描述为所有章节均已教学就绪，也没有获得真实目标学习者的整体试学验证。

## 从这里开始

1. [路线总控主页](00_路线总控/看板与索引/00_主页.md)
2. [学习模块阅读指南](10_学习模块/00_学习模块阅读指南.md)
3. [基础薄弱版 12 周执行路线](00_路线总控/基础薄弱版12周执行路线.md)
4. [学习模块建设状态表](00_路线总控/看板与索引/08_学习模块建设状态表.md)
5. [整改总控](00_路线总控/审计与整改/00_整改总控.md)
6. [110 项优化任务矩阵](00_路线总控/审计与整改/11_教材内容优化任务矩阵.csv)
7. [本轮矩阵状态证据审计](00_路线总控/审计与整改/artifacts/governance/optimization_matrix_status_audit_2026-07-19.md)
8. [2026-07-18 完整性复核与 Wave 0 实施报告](00_路线总控/审计与整改/12_优化方案二次完整性复核与Wave0实施报告_2026-07-18.md)

使用 Obsidian 时可从 [README_打开说明.md](README_打开说明.md) 进入；GitHub 页面优先使用本
README 中的标准 Markdown 链接。

## 学习主线

| 主线 | 范围 | 目标 |
|---|---|---|
| AI Infra 工程 | M00-M10 | Python 工程、API、RAG、Agent、队列、数据库、Docker、可观测性、Kubernetes 与推理 workload |
| 科研方法 | M11、P01、RQ01 | estimand、实验设计、尾延迟统计、稳健性、证据包与结论边界 |
| 金融工程 | F00-F08、GF 实验 | 市场与数据口径、统计、组合风险、衍生品、固定收益、回测和模型风险 |
| 交叉项目 | M12、P03 | 把 RAG、Agent、金融任务建模为可授权、可调度、可观测的 workload |

目录按用途组织：`00` 路线总控、`10` 教材、`20` 资料索引、`30` 知识卡片、`40` 实验、
`50` 项目、`60` 科研训练，之后是导师/就业/复盘与归档。

## 状态含义

本库不会用一个“已完成”同时代表内容、代码和学习者成果：

- `content-reviewed`：作者侧内容审查完成。
- `reference-verified`：仓库提供的参考实现通过指定验证。
- `instructional-ready`：章节具备讲解、示例、反例、练习、反馈与来源闭环。
- `learner-validated`：真实目标学习者完成试学、迁移题或保持度验证。

这四个状态独立。reference 测试通过不能推出学习者已完成，也不能自动证明生产可用。

## 可执行 Reference

统一门禁覆盖十套 Python 3.13 reference，共 399 项测试：

| Reference | 重点 |
|---|---|
| E00 OS/Network | 子进程信号、ready/shutdown deadline、请求路径诊断与有界回收 |
| E01 Concurrency | 线程/协程选择、取消、超时与结构化并发边界 |
| P01 Mini Scheduler | FIFO/Priority/SJF、尾延迟、aging、研究 pilot |
| E02 Task API | FastAPI、server-owned Principal、资源授权与 OpenAPI |
| E03 RAG | ACL 预过滤、检索评估、多格式 ingestion、HTML/PDF 解析边界、lineage 删除与离线 generation 输出评估 |
| E04 Agent Runtime | capability/resource gate、审批 CAS/outbox、claim fencing、versioned reducer/checkpoint、session 隔离 |
| E06 Async/Cache | owner-scoped FastAPI、task/outbox/lease worker、safe cache-aside 与 single-flight |
| E10 Inference | 确定性推理 workload 模拟与延迟统计 |
| Finance Reference | 时间序列、跨资产收益率、久期与凸性边界 |
| P03 Workload Platform | FastAPI/PostgreSQL/Redis Streams、RAG、worker 与恢复契约 |

E09 另有 kind/Kubernetes 功能性 reference，但需要 Docker 与本机集群环境，不属于纯 Python
统一测试计数。

## 本地验证

Windows 主基线为 Python 3.13。首次克隆后创建并同步十套环境：

```powershell
.\00_路线总控\审计与整改\tools\bootstrap_reference_envs.ps1
```

执行完整门禁：

```powershell
.\00_路线总控\审计与整改\tools\run_full_validation.ps1
```

完整门禁会运行 reference pytest、矩阵 DAG、来源/许可台账、版本新鲜度、Markdown/代码块/
WikiLink、编码、内容质量工具、Mermaid、`compileall`，以及工作树、暂存区和临时发布候选索引的
`git diff --check`。只做本地快速冒烟时可
使用 `-SkipContentAudit -SkipMermaid`，但发布前不能用冒烟结果替代完整门禁。

## 诚实边界

- 真实 vLLM benchmark 保持 `blocked/unverified`；NVIDIA Triton 和 Triton language/compiler
  保持 `design-only`，合成 simulator 不能替代 GPU serving 证据。
- E04 是无模型、无网络、单进程内存 reference，不是 P03 生产 Agent Runtime。
- E03 的 simulated generation evaluator 与 claimed-external 拒绝门禁不等于真实模型抗间接注入；
  生产 parser 沙箱、真实 OCR 和外部存储删除传播也未由该内存 reference 证明。
- RQ01 当前证据包含合成 pilot；未覆盖的真实 P03、burst/Pareto 和场景结论不得外推。
- E09 自动扩缩容、生产集群安全和跨节点调度仍需要独立环境复核。
- 金融内容仅用于学习与研究，不构成投资建议。

## 安全与授权

不要提交 `.env`、bearer token、Obsidian Local REST API `data.json*`、kubeconfig、证书私钥或
本机日志。教材中的固定 bearer 值必须明确标为非秘密 fixture；公开发布前使用 Gitleaks 全规则
扫描最终 Git 历史。`.gitleaks.toml` 只对未修改的 MIT 插件 bundle 中三处
`generic-api-key` 误报按“规则 + 路径”定向放行，不放行 private-key 或仓库其他路径。

本仓库目前没有为自有教材选择根级开源许可证。公开可见不等于授予复制、修改或再分发许可，
因此不要将其称为“开源教材”。第三方组件按各自许可证处理；随库保留的 Obsidian Local REST
API bundle 及其 MIT 文本见
[插件目录](.obsidian/plugins/obsidian-local-rest-api/)。来源与再分发复核状态见
[治理台账](00_路线总控/审计与整改/artifacts/governance/provenance_license_ledger.csv)。
