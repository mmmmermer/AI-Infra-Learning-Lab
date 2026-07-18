# M02 后端 API 与服务化资料索引

## 当前策略

M02 的资料只服务一件事：把 P01 的任务模型和后续 RAG / Agent 工作流变成可调用、可验证的 API 服务。

资料使用遵循四条原则：

1. 先读 FastAPI 官方教程里最直接相关的部分。
2. 先让请求模型、响应模型、错误处理和测试跑通，再谈复杂分层。
3. 每条资料都必须能转化成教材章节、实验步骤或项目代码。
4. 不提前把自己拖进数据库、鉴权和部署深坑。

## 核心资料表

| 资料 | 链接 | 类型 | 适合阶段 | 当前用途 | 状态 |
|---|---|---|---|---|---|
| FastAPI Home | https://fastapi.tiangolo.com/ | 官方文档 | 入门 | 理解 FastAPI 的整体风格与类型驱动设计 | 必读 |
| FastAPI Request Body | https://fastapi.tiangolo.com/tutorial/body/ | 官方文档 | 入门 | 请求体、Pydantic 输入模型、POST 接口 | 必读 |
| FastAPI Response Model | https://fastapi.tiangolo.com/tutorial/response-model/ | 官方文档 | 入门 | 响应模型、输出过滤、接口返回约束 | 必读 |
| FastAPI Testing | https://fastapi.tiangolo.com/tutorial/testing/ | 官方文档 | 项目化 | TestClient、pytest、接口测试 | 必读 |
| FastAPI TestClient Reference | https://fastapi.tiangolo.com/reference/testclient/ | 官方文档 | 查阅 | 测试客户端的最小使用方式 | 查阅 |
| Pydantic Docs | https://docs.pydantic.dev/ | 官方文档 | 项目化 | 请求/响应数据模型、校验与序列化 | 必读 |
| OpenAPI / Swagger | https://fastapi.tiangolo.com/ | 官方文档 | 项目化 | 自动文档、接口可视化 | 选读 |

## 资料和教材章节的对应关系

| 教材章节 | 主要资料 | 使用方式 |
|---|---|---|
| 第 1 章：为什么 M02 先学 API | FastAPI Home | 明确 API 是 P01 到 P02/P03 的接口层 |
| 第 2 章：REST 和资源建模 | FastAPI Home、Request Body | 把任务、状态、指标建成资源 |
| 第 3 章：请求体和响应体 | Request Body、Response Model | 设计 `TaskCreate`、`TaskRead`、`MetricsRead` |
| 第 4 章：Pydantic 模型 | Pydantic Docs | 把输入校验和数据结构固定下来 |
| 第 5 章：状态码和错误处理 | FastAPI Home、Testing | 对 404 / 422 / 409 / 500 建立基本直觉 |
| 第 6 章：项目分层 | FastAPI Home | router / service / repository / model |
| 第 7 章：接口测试 | FastAPI Testing、TestClient Reference | 用 pytest 验证 API 行为 |
| 第 8 章：OpenAPI 文档 | FastAPI Home | 让接口自动生成文档和调试入口 |
| 第 9 章：贯通到 P01/P02/P03 | 上述资料综合 | 让任务、状态和 metrics 能跨项目复用 |

## 对应实验

- [[40_实验练习/E02_后端API实验/E02-01 创建任务 API]]
- [[40_实验练习/E02_后端API实验/E02-02 查询任务状态 API]]
- [[40_实验练习/E02_后端API实验/E02-03 metrics API]]

## 资料和实验的对应关系

| 实验 | 必读资料 | 查阅资料 | 转化目标 |
|---|---|---|---|
| E02-01 创建任务 API | FastAPI Request Body、Pydantic Docs | TestClient Reference | 能提交任务并验证请求体 |
| E02-02 查询任务状态 API | FastAPI Response Model、Testing | FastAPI Home | 能按任务 id 查询状态和结果 |
| E02-03 metrics API | Response Model、Testing | OpenAPI / Swagger | 能输出队列长度、延迟、worker 利用率等指标 |
| P02 阶段扩展 | FastAPI Home、Pydantic Docs | TestClient Reference | 能把 RAG / Agent 任务接入服务层 |

## 当前只读哪些部分

| 资料 | 第一轮阅读范围 |
|---|---|
| FastAPI Home | 路由、参数、请求体、响应模型、测试、依赖注入的最小部分 |
| Request Body | POST 请求体、Pydantic 模型、字段默认值 |
| Response Model | 输出模型、返回类型、数据过滤 |
| Testing | TestClient、pytest、最小测试模式 |
| Pydantic Docs | BaseModel、字段类型、校验与序列化 |
| TestClient Reference | 创建 TestClient 的最小方式 |

## 转化要求

- 每读完一个章节，至少要能写出一个接口或测试。
- 不允许只收藏链接，不允许只记概念。
- API 设计必须回到 P01/P02/P03 的实际任务流。

## 建议学习顺序

1. 先读 FastAPI Home，理解路由和类型驱动风格。
2. 再读 Request Body 和 Pydantic Docs，写出 `POST /tasks`。
3. 再读 Response Model，写出 `GET /tasks/{task_id}` 和 `GET /metrics`。
4. 再读 Testing 和 TestClient，补接口测试。
5. 最后补 OpenAPI 文档和最小项目分层。

## 不做

- 不先学复杂微服务。
- 不先学 SpringCloud。
- 不先做完整权限系统。
- 不先引入重型 ORM 和缓存架构。
