# 脱敏合规 AI 案例工程参照分析

## 定位

原始项目路径与仓库位置不随本库发布；以下内容仅为经过脱敏的架构摘要。

它是一个脱敏后的外部工程案例参照（非本人成果），用来帮助学习库理解：

- FastAPI 后端如何组织模块。
- RAG 与 evidence 证据链如何设计边界。
- 数据库、仓储、审计、安全摘要如何落地。
- Docker Compose 如何组织基础服务。
- 前后端接口契约如何联动。
- 人工复核和风险提示如何避免“AI 自动下结论”。
- 测试与验收如何覆盖主流程。

它不是 P03 的替代品，也不能直接包装成个人已完成项目成果；原项目不随本仓库发布。

只有后续亲手复现、改造、测试、解释过的部分，才能进入个人项目表达。

## 审计范围

本次审计查看了：

- `README.md`
- `docs/project-baseline/00_项目总览.md`
- `docs/project-baseline/01_工程架构基线.md`
- `docs/project-baseline/03_API与数据契约.md`
- `docs/development/00_代码目录结构.md`
- `docs/development/02_A_AI与RAG开发说明.md`
- `docs/development/04_C_后端数据库与部署开发说明.md`
- `docs/development/09_测试与验收计划.md`
- `backend/app/main.py`
- `backend/app/modules/`
- `backend/tests/`
- `frontend/src/api/`
- `frontend/src/views/`
- `frontend/src/types/`
- `docker-compose.yml`

## 总体观察

脱敏合规 AI 案例采用的是：

```text
Vue/Vite 前端
-> FastAPI 模块化单体后端
-> PostgreSQL / Redis / Qdrant / MinIO
-> 合同上传、解析、画像、规则审查
-> RAG evidence
-> AI Gateway
-> 人工复核
-> 报告草稿和审计摘要
```

它的工程价值不在于“直接复制代码”，而在于展示一个复杂 AI 应用如何把业务流程、接口契约、数据对象、证据链、人工复核和安全边界组织起来。

## 可以学习的内容

### 1. FastAPI 后端结构

可学习：

- `backend/app/main.py` 中的 `create_app()` 工厂函数。
- `app.api.v1.router` 统一挂载路由。
- `app.core.config`、`exceptions`、`request_context` 的基础设施分层。
- `backend/app/modules/` 下按业务能力拆模块：
  - `contracts`
  - `rag`
  - `ai_gateway`
  - `reports`
  - `audit`
  - `auth`
  - `knowledge`
  - `rules`

不能照搬：

- 合同审查业务模块不能直接搬进 P03。
- P03 不需要一开始拥有完整 auth、organization、admin、knowledge governance。

后续亲手复现：

- 在 P03 中复现一个更小的 FastAPI app 工厂。
- 只保留 `tasks`、`rag`、`worker`、`metrics` 等最小模块。

### 2. RAG 与证据链

可学习：

- RAG evidence 字段设计：
  - `evidence_id`
  - `title`
  - `source_type`
  - `source_name`
  - `source_url`
  - `version_date`
  - `excerpt`
  - `summary`
  - `applicability`
  - `limitation`
  - `score`
- mock evidence 和正式 evidence 的边界。
- 无 evidence 时不得编造依据。
- Prompt 注入内容要视为不可信输入。
- RAG retriever 模式区分：
  - `mock`
  - `seed`
  - Qdrant 相关受控入口。

不能照搬：

- 不能把脱敏合规 AI 案例的合规知识、合同字段和风险规则直接当成 P03 的通用 RAG 设计。
- 不能把 mock evidence 写成真实法规依据。
- 不能宣称真实 Qdrant 检索、真实 embedding 或真实 DeepSeek 主链路已经完成，除非亲手验证过。

后续亲手复现：

- 在 P03 中做 `retrieved_sources` 和 `has_citation` 的最小结构。
- 用 E03 的 chunk/top-k/metadata 实验验证字段。

### 3. 数据库与仓储

可学习：

- 仓储协议抽象：内存仓储、JSON 文件仓储、PostgreSQL 仓储并存。
- PostgreSQL 不是一开始就等于生产级数据库平台。
- 审计摘要只保存安全元数据，不保存合同全文、条款原文或敏感内容。
- 状态查询接口要返回当前仓储模式和安全边界。

不能照搬：

- 脱敏合规 AI 案例的合同表、风险表、报告表不能直接变成 P03 的 tasks 表。
- JSON 文件仓储不是生产数据库，不能作为成果夸大。
- 当前最小 JWT/RBAC 不等于企业级权限。

后续亲手复现：

- P03 先做 `tasks` 表或内存替代。
- 再接 E06 的任务状态持久化、失败重试和查询状态。

### 4. Docker Compose

可学习：

脱敏合规 AI 案例的 `docker-compose.yml` 包含：

- `postgres`
- `redis`
- `qdrant`
- `minio`
- named volumes
- postgres/redis healthcheck

这对 M07/E07 很有参考价值。

不能照搬：

- P03 v0.1 不必直接加入 qdrant/minio。
- P03 需要的是 `api + db + redis + worker` 的最小 compose。
- 端口、项目名、初始化脚本和数据目录都应按 P03 自己设计。

后续亲手复现：

- 参考它的 volume 和 healthcheck 写法。
- 在 P03 中完成 E07-01/E07-02/E07-03。

### 5. 前后端联动

可学习：

- `frontend/src/api/` 中使用薄 API client：
  - `http.ts`
  - `auth.ts`
  - `contracts.ts`
  - `findings.ts`
  - `reports.ts`
  - `audit.ts`
  - `governance.ts`
- `frontend/src/types/` 保存接口类型。
- 页面不直接硬编码后端地址。
- 前端 README 明确哪些接口已实现，哪些仍未实现。

不能照搬：

- P03 v0.1 不需要完整前端。
- 脱敏合规 AI 案例的合同工作台 UI 不能直接变成 P03 dashboard。

后续亲手复现：

- P03 后续需要前端时，先做任务列表、任务详情、metrics 面板三个页面。
- API client 参考薄封装方式，不复制业务字段。

### 6. 人工复核和风险提示

可学习：

- 系统定位为辅助审查，不替代律师、法务或合规顾问。
- 高风险输出必须带 evidence、限制条件和人工复核状态。
- 人工复核动作和目标状态分开：
  - `confirm`
  - `reject`
  - `request_more_info`
  - `accept_suggestion`
  - `ignore`
- `need_more_info` 不能被当成已闭环结论。

不能照搬：

- 合规风险规则不能直接作为 P03 的通用 Agent 规则。
- 不能输出最终法律意见或投资/合规结论。

后续亲手复现：

- 在 P03 Agent v1 中复现 `waiting_approval`、`approval_status`、`step_logs`。
- 用 E04 验证人工确认和失败处理。

### 7. 测试与验收

可学习：

后端测试目录覆盖：

- health
- auth flow
- contract flow
- repository
- audit flow
- report flow
- mainline business flow
- sample contracts
- RAG embedding/indexing/mock retriever/Qdrant contract
- knowledge seed
- AI gateway schema

测试计划也明确了：

- 单元测试。
- 接口测试。
- 前端测试。
- AI/RAG 测试。
- 场景测试。
- 安全测试。

不能照搬：

- P03 不需要照搬合同场景测试。
- P03 v0.1 不需要完整前端测试和安全测试矩阵。

后续亲手复现：

- P03 先写：
  - `/health` 测试。
  - `POST /tasks` 的 `task_type=rag_retrieval` 测试。
- `GET /tasks/{task_id}` 测试。
  - worker 状态流转测试。
  - metrics 字段测试。

## 不能包装成个人成果的内容

以下内容不能直接写进个人项目成果：

- 脱敏合规 AI 案例的团队工程实现。
- 脱敏合规 AI 案例的前端页面和业务流程。
- 脱敏合规 AI 案例已有的测试结果、Docker 配置检查、Ruff 结果、前端 build 结果。
- 脱敏合规 AI 案例的合同审查、风险规则、RAG evidence、AI Gateway 实现。
- 任何未亲手复现、未改造、未测试、无法解释的代码和结果。

可以写成学习经历或案例参照：

```text
参考真实合规 AI 工程项目，分析其 FastAPI 模块化单体、RAG evidence、仓储协议、Docker Compose 和人工复核边界，并将其中可复用的工程模式迁移到个人 P03 AI workload 平台设计中。
```

## 与学习模块的关系

| 学习模块 | 脱敏合规 AI 案例可参考点 | 使用方式 |
|---|---|---|
| M02 后端 API 与服务化 | FastAPI app factory、统一路由、响应格式、异常处理 | 学结构，不复制合同接口 |
| M03 RAG 工程 | evidence 字段、mock/seed retriever、no evidence 不编造 | 转化为 P03 `retrieved_sources` |
| M04 Agent 工作流 | 人工复核、状态闭环、风险提示边界 | 转化为 `waiting_approval` 和 `step_logs` |
| M06 数据库缓存与异步任务 | 仓储协议、内存/JSON/Postgres 分层、状态查询 | 转化为 P03 tasks store |
| M07 Docker 与容器化 | postgres/redis/qdrant/minio、volume、healthcheck | P03 先学 api/db/redis/worker compose |
| M08 监控压测与可观测性 | request_id、审计安全摘要、错误码、测试验收 | 转化为 P03 logs/metrics/error_type |
| M12 金融投研 AI 场景 | 风险提示、证据引用、免责声明、人工复核 | 类比金融/合规文档场景，不做投资建议 |
| P03 AI Workload Platform | 真实工程边界、模块分层、API 契约、测试矩阵 | 作为参照，不作为替代 |

## 脱敏合规 AI 案例与 P03 映射表

| 脱敏合规 AI 案例元素 | P03 对应元素 | 可迁移方式 | 注意边界 |
|---|---|---|---|
| `backend/app/main.py` app factory | P03 FastAPI 入口 | 学 `create_app()`、router、middleware | P03 不需要合同业务模块 |
| `backend/app/modules/contracts` | P03 task service | 学服务层和仓储边界 | 合同上传不是 P03 v0.1 主线 |
| `backend/app/modules/rag` | P03 RAG worker / retriever | 学 mock/seed/retriever contract | 不宣称真实 Qdrant 或 embedding 已完成 |
| `backend/app/modules/ai_gateway` | P03 generation adapter | 学模型调用统一入口和 schema 校验 | P03 v0.1 可先 mock |
| `backend/app/modules/reports` | P03 result/report output | 学报告草稿和免责声明 | 不做正式 PDF/DOCX |
| `backend/app/modules/audit` | P03 logs / metrics / event summary | 学安全摘要和 request_id | 不做生产级不可篡改审计 |
| `backend/app/modules/auth` | P03 optional auth | 学最小演示边界 | P03 v0.1 不做生产级权限 |
| `docs/project-baseline/03_API与数据契约.md` | P03 `03_API与数据契约.md` | 学状态、错误码、统一响应 | 字段要按 task workload 重写 |
| `docker-compose.yml` | P03 compose | 学 postgres/redis volume/healthcheck | P03 v0.1 先不强制 qdrant/minio |
| `frontend/src/api` | P03 future frontend API clients | 学薄封装和类型分层 | P03 先做后端和 worker |
| `frontend/src/views/ReviewWorkspaceView.vue` | P03 future task dashboard | 学工作台信息组织 | 不复制 UI 和合同字段 |
| `backend/tests` | P03 tests | 学测试分层和主流程测试 | P03 只写 workload 相关测试 |
| 人工复核状态 | P03 Agent approval | 学 `pending/confirmed/rejected/need_more_info` 思路 | P03 用 `waiting_approval/approved/rejected/cancelled` |

## 后续行动建议

1. 不修改脱敏合规 AI 案例项目代码。
2. 不把脱敏合规 AI 案例写进 P03 README 当作已完成实现。
3. 在 P03 v0.1 开工时，只抽取三个模式：
   - FastAPI app factory。
   - task store / repository 边界。
   - compose 中 db/redis/worker 的可复现启动。
4. 亲手复现后，再把复现记录写入 P03：
   - [[50_项目产出/P03_AI_Workload_Platform/04_实验记录/00_实验索引|P03 实验记录索引]]
   - [[50_项目产出/P03_AI_Workload_Platform/05_问题与失败记录|P03 问题与失败记录]]
5. 简历表达只使用亲手完成、能运行、能测试、能解释的数据和功能。
