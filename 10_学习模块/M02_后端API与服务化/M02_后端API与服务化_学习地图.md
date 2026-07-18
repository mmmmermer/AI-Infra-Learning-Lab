# M02 后端 API 与服务化学习地图

## 怎么读这个模块

把 M02 当成“把脚本变成别人能调用的服务”的训练，不要当成 FastAPI 参数清单。

阅读时始终抓一条线：用户提交任务，API 校验请求，service 创建任务，repository 保存任务，用户再查询状态。只要这条线通了，M02 第一轮就合格。

先把创建、分页、查询、条件更新、metrics 和 health 讲清、写清、测清，再用 request lifecycle、
Problem Details、deadline、幂等和 CAS 约束失败与并发路径。

## 在总路线中的位置

M02 负责把 P01 的调度内核和后续 RAG / Agent 功能变成可调用、可管理、可测试的服务接口。它是从“小脚本工程”走向“后端应用工程”的第一步。

## 要解决的问题

- AI 功能如何变成可调用、可管理、可测试的服务？
- 任务如何通过 API 提交、查询、取消和追踪？
- 如何把请求模型、业务逻辑、持久化和测试分层？

## 学习内容

- FastAPI 基础
- REST API 和资源建模
- 请求 / 响应模型
- Pydantic
- 状态码和错误处理
- 后台任务与异步思维
- OpenAPI 自动文档
- 接口测试
- 项目分层：router / service / repository / model
- 鉴权基础与最小权限边界
- middleware、request ID、依赖注入与日志脱敏
- RFC 9457 Problem Details、owner-scoped cursor pagination
- liveness/readiness、依赖/连接容量和限流恢复
- deadline 无幽灵写、幂等创建、ETag/If-Match CAS

## 学习目标

- 能写出一个最小可运行的 FastAPI 服务。
- 能设计清楚的任务 API，并用 Pydantic 定义请求和响应模型。
- 能解释 API 是系统契约，不只是把函数包装成 HTTP。
- 能区分 `TaskCreate` 和 `TaskRead`，并说明为什么外部不能提交 `task_id/status`。
- 能把接口层和业务层分开，不把全部逻辑堆在路由里。
- 能用 pytest/TestClient 验证接口行为和错误返回。
- 能证明同一 request ID 跨入口、认证、service、repository 和错误响应。
- 能让分页、过载恢复、超时、重复创建与并发更新的结果机器可判定。
- 能解释为什么 API 层是 P01 到 P02/P03 的关键过渡。

## 对应资料

- [[20_资料库/模块资料索引/M02_后端API与服务化_资料索引|M02 后端 API 与服务化资料索引]]
- [[10_学习模块/M02_后端API与服务化/M02_后端API与服务化_适配教材|M02 后端 API 与服务化适配教材]]
- [[50_项目产出/P01_Mini_Scheduler/P01_Mini_Scheduler 项目主页|P01 项目主页]]
- [[50_项目产出/P02_RAG_Agent_Service/P02_RAG_Agent_Service 项目主页|P02 项目主页]]
- [[50_项目产出/P03_AI_Workload_Platform/P03_AI_Workload_Platform 项目主页|P03 项目主页]]
- [FastAPI 官方文档](https://fastapi.tiangolo.com/)
- [FastAPI Request Body](https://fastapi.tiangolo.com/tutorial/body/)
- [FastAPI Response Model](https://fastapi.tiangolo.com/tutorial/response-model/)
- [FastAPI Testing](https://fastapi.tiangolo.com/tutorial/testing/)
- [Pydantic Docs](https://docs.pydantic.dev/)
- [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457)
- [RFC 9110 HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)

## 对应知识卡片

这些卡片后续会在做 API 的过程中逐步沉淀，先按问题建，不先假设它们已经存在。

- REST API
- 请求体与响应体
- 状态码
- Pydantic Model
- 路由分层
- API 测试
- 后台任务
- 错误返回

## 对应实验

- [[E02-01 创建任务 API]]
- [[E02-02 查询任务状态 API]]
- [[E02-03 metrics API]]
- [[E02-04 请求生命周期可靠性与并发契约]]

## 对应项目

- [[P02_RAG_Agent_Service 项目主页]]
- [[P03_AI_Workload_Platform 项目主页]]

## 检查标准

- [ ] 能跑起一个 FastAPI 服务
- [ ] 能写创建、cursor 列表、单项查询、If-Match 更新、metrics、livez 与 readyz
- [ ] 能用 Pydantic 模型验证输入
- [ ] 能返回合适的状态码和错误信息
- [ ] 能解释 `return {}` 为什么会破坏错误契约
- [ ] 能写接口测试并通过
- [ ] 能说明只测成功路径为什么不够
- [ ] 能解释 router / service / repository 的职责边界
- [ ] 能说明内存版 `TASKS` 只是 M06 数据库前的临时 repository
- [ ] 能把一个简单 API 接到 P01/P03 的任务模型上
- [ ] 同一 request ID 跨层且日志不含凭据/身份原值；Problem Details 有稳定 code
- [ ] dependency/pool/429 恢复可测试，readiness 不固定返回 200
- [ ] deadline 超时无写入、幂等 replay 不重复、并发 CAS 恰好一个成功

## 暂时不深入

- 不在 M02 深入复杂认证授权体系。
- 不把数据库 ORM、缓存、消息队列一次全学完。
- 不先学完整微服务治理、Service Mesh、分布式事务。
- 不追求生产级部署细节，先把接口设计和测试做稳。
- 不把内存锁外推成数据库事务，也不声称已完成跨副本幂等/限流或客户端断开取消。
